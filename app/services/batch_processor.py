"""
Celery task that processes a BatchRequest in the background.

Uses a **synchronous** SQLAlchemy session (psycopg2) because Celery
workers are sync processes – separate from the async FastAPI event loop.
"""

import os
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import BatchRequest, BatchStatus, Certificate, CertificateStatus
from app.services.certificate_generator import generate_certificate_pdf
from app.worker import celery_app

# Sync engine for the Celery worker process
_sync_engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
SyncSessionFactory = sessionmaker(bind=_sync_engine)


@celery_app.task(name="process_batch_request", bind=True, max_retries=0)
def process_batch_request(self, batch_request_id: str) -> dict:
    """
    Process every pending certificate in the given batch.

    Design: each certificate is generated independently inside its own
    try/except so that a failure in one certificate does **not** prevent
    the remaining certificates from being generated.
    """
    session = SyncSessionFactory()
    try:
        batch = (
            session.query(BatchRequest)
            .filter(BatchRequest.id == uuid.UUID(batch_request_id))
            .first()
        )
        if not batch:
            return {"error": f"BatchRequest {batch_request_id} not found"}

        # Mark as processing
        batch.status = BatchStatus.PROCESSING
        session.commit()

        # Fetch all pending certificates for this batch
        certificates = (
            session.query(Certificate)
            .filter(
                Certificate.batch_request_id == batch.id,
                Certificate.status == CertificateStatus.PENDING,
            )
            .all()
        )

        successful = 0
        failed = 0

        for cert in certificates:
            try:
                file_name = f"{cert.id}.pdf"
                output_path = os.path.join(
                    settings.CERTIFICATES_DIR, str(batch.id), file_name
                )

                generate_certificate_pdf(
                    recipient_name=cert.recipient_name,
                    course_name=cert.course_name,
                    issue_date=cert.issue_date,
                    output_path=output_path,
                )

                cert.status = CertificateStatus.SUCCESS
                cert.file_path = output_path
                successful += 1

            except Exception as exc:
                cert.status = CertificateStatus.FAILED
                cert.error_message = str(exc)
                failed += 1

            # Commit after each certificate so progress is visible
            session.commit()

        # Finalize batch
        batch.successful_count = successful
        batch.failed_count = failed
        batch.status = (
            BatchStatus.COMPLETED
            if successful > 0
            else BatchStatus.FAILED
        )
        session.commit()

        return {
            "batch_request_id": batch_request_id,
            "successful": successful,
            "failed": failed,
        }

    except Exception:
        session.rollback()
        # Attempt to mark the batch as failed
        try:
            batch = (
                session.query(BatchRequest)
                .filter(BatchRequest.id == uuid.UUID(batch_request_id))
                .first()
            )
            if batch:
                batch.status = BatchStatus.FAILED
                session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()
