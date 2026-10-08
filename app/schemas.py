"""
Pydantic schemas for request validation and response serialization.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import BatchStatus, CertificateStatus


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RecipientSchema(BaseModel):
    """Schema for a single recipient in a batch request."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Recipient's full name",
        examples=["Jane Doe"],
    )
    email: EmailStr = Field(
        ...,
        description="Recipient's email address",
        examples=["jane.doe@example.com"],
    )


class BatchRequestCreate(BaseModel):
    """Payload to create a new batch certificate-generation request."""
    course_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the course or event",
        examples=["Advanced Python Programming"],
    )
    issue_date: str = Field(
        ...,
        description="Date of issue in YYYY-MM-DD format",
        examples=["2026-10-08"],
    )
    recipients: List[RecipientSchema] = Field(
        ...,
        min_length=1,
        description="List of recipients (at least one required)",
    )

    @field_validator("issue_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("issue_date must be in YYYY-MM-DD format")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CertificateResponse(BaseModel):
    """Response schema for a single certificate."""
    id: UUID
    batch_request_id: UUID
    recipient_name: str
    recipient_email: str
    course_name: str
    issue_date: str
    status: CertificateStatus
    error_message: Optional[str] = None
    file_path: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BatchRequestResponse(BaseModel):
    """Response schema for a batch request (summary, without certificates)."""
    id: UUID
    status: BatchStatus
    total_recipients: int
    successful_count: int
    failed_count: int
    course_name: str
    issue_date: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BatchRequestDetailResponse(BatchRequestResponse):
    """Response schema for a batch request including its certificates."""
    certificates: List[CertificateResponse] = []


class BatchRequestListResponse(BaseModel):
    """Paginated list of batch requests."""
    batch_requests: List[BatchRequestResponse]
    total: int
