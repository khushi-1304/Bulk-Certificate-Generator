"""
API router for batch certificate generation.

Endpoints
---------
POST   /api/batch-requests                          – Create a new batch
GET    /api/batch-requests                          – List all batches
GET    /api/batch-requests/{batch_id}               – Batch detail + certificates
GET    /api/batch-requests/{batch_id}/certificates  – Certificates for a batch
GET    /api/certificates/{certificate_id}/download  – Download a certificate PDF
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import BatchRequest, BatchStatus, Certificate, CertificateStatus
from app.schemas import (
    BatchRequestCreate,
    BatchRequestDetailResponse,
    BatchRequestListResponse,
    BatchRequestResponse,
    CertificateResponse,
)
from app.services.batch_processor import process_batch_request

router = APIRouter(prefix="/api", tags=["Batch Requests & Certificates"])


# ── POST /api/batch-requests ────────────────────────────────────────────────

@router.post(
    "/batch-requests",
    response_model=BatchRequestResponse,
    status_code=201,
    summary="Submit a bulk certificate generation request",
)
async def create_batch_request(
    payload: BatchRequestCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a list of recipients and queue certificate generation for each.

    The endpoint returns immediately with a ``pending`` batch; actual PDF
    generation happens asynchronously via Celery.
    """
    # Create the batch row
    batch = BatchRequest(
        status=BatchStatus.PENDING,
        total_recipients=len(payload.recipients),
        successful_count=0,
        failed_count=0,
        course_name=payload.course_name,
        issue_date=payload.issue_date,
    )
    db.add(batch)
    await db.flush()  # get batch.id before creating children

    # Create individual certificate rows
    certificates = [
        Certificate(
            batch_request_id=batch.id,
            recipient_name=recipient.name,
            recipient_email=recipient.email,
            course_name=payload.course_name,
            issue_date=payload.issue_date,
            status=CertificateStatus.PENDING,
        )
        for recipient in payload.recipients
    ]
    db.add_all(certificates)
    await db.commit()
    await db.refresh(batch)

    # Dispatch background processing
    process_batch_request.delay(str(batch.id))

    return batch


# ── GET /api/batch-requests ─────────────────────────────────────────────────

@router.get(
    "/batch-requests",
    response_model=BatchRequestListResponse,
    summary="List all batch requests",
)
async def list_batch_requests(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of batch requests, newest first."""
    total_q = await db.execute(select(func.count(BatchRequest.id)))
    total = total_q.scalar()

    rows_q = await db.execute(
        select(BatchRequest)
        .order_by(BatchRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return BatchRequestListResponse(
        batch_requests=rows_q.scalars().all(),
        total=total,
    )


# ── GET /api/batch-requests/{batch_id} ──────────────────────────────────────

@router.get(
    "/batch-requests/{batch_id}",
    response_model=BatchRequestDetailResponse,
    summary="Get batch request status and certificates",
)
async def get_batch_request(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return batch details including every certificate's status."""
    result = await db.execute(
        select(BatchRequest)
        .options(selectinload(BatchRequest.certificates))
        .where(BatchRequest.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch request not found")
    return batch


# ── GET /api/batch-requests/{batch_id}/certificates ─────────────────────────

@router.get(
    "/batch-requests/{batch_id}/certificates",
    response_model=list[CertificateResponse],
    summary="List certificates for a batch",
)
async def list_certificates(
    batch_id: uuid.UUID,
    status: Optional[CertificateStatus] = Query(
        None, description="Filter by certificate status"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Return certificates belonging to the batch, optionally filtered."""
    # Verify batch exists
    batch_q = await db.execute(
        select(BatchRequest).where(BatchRequest.id == batch_id)
    )
    if not batch_q.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Batch request not found")

    query = select(Certificate).where(Certificate.batch_request_id == batch_id)
    if status is not None:
        query = query.where(Certificate.status == status)
    query = query.order_by(Certificate.created_at)

    result = await db.execute(query)
    return result.scalars().all()


# ── GET /api/certificates/{certificate_id}/download ─────────────────────────

@router.get(
    "/certificates/{certificate_id}/download",
    summary="Download a generated certificate PDF",
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {"description": "Certificate not yet generated or failed"},
        404: {"description": "Certificate not found"},
    },
)
async def download_certificate(
    certificate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Stream the generated PDF back to the client."""
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id)
    )
    cert = result.scalar_one_or_none()

    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    if cert.status != CertificateStatus.SUCCESS:
        raise HTTPException(
            status_code=400,
            detail=f"Certificate generation {cert.status.value}. Cannot download.",
        )

    if not cert.file_path or not os.path.exists(cert.file_path):
        raise HTTPException(
            status_code=404, detail="Certificate file not found on disk"
        )

    safe_name = cert.recipient_name.replace(" ", "_")
    return FileResponse(
        path=cert.file_path,
        media_type="application/pdf",
        filename=f"certificate_{safe_name}.pdf",
    )
