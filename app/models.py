"""
SQLAlchemy ORM models for BatchRequest and Certificate.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BatchStatus(str, enum.Enum):
    """Lifecycle status of a batch request."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CertificateStatus(str, enum.Enum):
    """Generation status of an individual certificate."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class BatchRequest(Base):
    """
    Represents a single bulk certificate-generation request.
    Contains one or more Certificate rows.
    """
    __tablename__ = "batch_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(
        SAEnum(BatchStatus, name="batch_status"),
        default=BatchStatus.PENDING,
        nullable=False,
    )
    total_recipients = Column(Integer, default=0, nullable=False)
    successful_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    course_name = Column(String(255), nullable=False)
    issue_date = Column(String(50), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # One-to-many relationship
    certificates = relationship(
        "Certificate",
        back_populates="batch_request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<BatchRequest {self.id} status={self.status}>"


class Certificate(Base):
    """
    Represents a single certificate within a BatchRequest.
    Tracks its own generation status independently.
    """
    __tablename__ = "certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("batch_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_name = Column(String(255), nullable=False)
    recipient_email = Column(String(255), nullable=False)
    course_name = Column(String(255), nullable=False)
    issue_date = Column(String(50), nullable=False)
    status = Column(
        SAEnum(CertificateStatus, name="certificate_status"),
        default=CertificateStatus.PENDING,
        nullable=False,
    )
    error_message = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Back-reference
    batch_request = relationship("BatchRequest", back_populates="certificates")

    def __repr__(self):
        return f"<Certificate {self.id} recipient={self.recipient_name}>"
