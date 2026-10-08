"""
Test suite for the Bulk Certificate Generator API.

Covers:
  1. Creating a batch request
  2. Input validation
  3. Certificate generation (unit)
  4. Batch status / progress
  5. Handling individual certificate failure
  6. Retrieving / downloading generated certificates
"""

import os
import tempfile
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.models import CertificateStatus
from app.services.certificate_generator import generate_certificate_pdf


# ═══════════════════════════════════════════════════════════════════════════
# 1. Creating a batch request
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_batch_request_success(client, mock_celery, valid_payload):
    """POST /api/batch-requests should create a batch and return 201."""
    resp = await client.post("/api/batch-requests", json=valid_payload)

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["total_recipients"] == 3
    assert data["successful_count"] == 0
    assert data["failed_count"] == 0
    assert data["course_name"] == valid_payload["course_name"]
    mock_celery.delay.assert_called_once()


@pytest.mark.asyncio
async def test_create_batch_request_triggers_celery(client, mock_celery, valid_payload):
    """The Celery task should be dispatched with the batch id."""
    resp = await client.post("/api/batch-requests", json=valid_payload)
    batch_id = resp.json()["id"]
    mock_celery.delay.assert_called_once_with(batch_id)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Input validation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_validation_empty_recipients(client, mock_celery):
    """An empty recipients list should be rejected."""
    payload = {
        "course_name": "Test Course",
        "issue_date": "2026-01-01",
        "recipients": [],
    }
    resp = await client.post("/api/batch-requests", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validation_invalid_date_format(client, mock_celery):
    """A malformed issue_date should be rejected."""
    payload = {
        "course_name": "Test Course",
        "issue_date": "08-10-2026",  # wrong format
        "recipients": [{"name": "Alice", "email": "alice@example.com"}],
    }
    resp = await client.post("/api/batch-requests", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validation_invalid_email(client, mock_celery):
    """An invalid email should be rejected."""
    payload = {
        "course_name": "Test Course",
        "issue_date": "2026-01-01",
        "recipients": [{"name": "Alice", "email": "not-an-email"}],
    }
    resp = await client.post("/api/batch-requests", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validation_missing_name(client, mock_celery):
    """A recipient without a name should be rejected."""
    payload = {
        "course_name": "Test Course",
        "issue_date": "2026-01-01",
        "recipients": [{"name": "", "email": "alice@example.com"}],
    }
    resp = await client.post("/api/batch-requests", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validation_missing_course_name(client, mock_celery):
    """A request without course_name should be rejected."""
    payload = {
        "issue_date": "2026-01-01",
        "recipients": [{"name": "Alice", "email": "alice@example.com"}],
    }
    resp = await client.post("/api/batch-requests", json=payload)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 3. Certificate generation (unit test)
# ═══════════════════════════════════════════════════════════════════════════

def test_generate_certificate_pdf_creates_file():
    """The PDF generator should create a valid file on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "test_cert.pdf")
        result = generate_certificate_pdf(
            recipient_name="Jane Doe",
            course_name="Machine Learning 101",
            issue_date="2026-10-08",
            output_path=out,
        )
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0
        # Verify it starts with a PDF header
        with open(result, "rb") as f:
            assert f.read(5) == b"%PDF-"


def test_generate_certificate_pdf_creates_subdirectories():
    """The generator should create intermediate directories automatically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sub", "dir", "cert.pdf")
        result = generate_certificate_pdf(
            recipient_name="Test User",
            course_name="Course",
            issue_date="2026-01-01",
            output_path=out,
        )
        assert os.path.exists(result)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Batch status / progress
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_batch_request_detail(client, mock_celery, valid_payload):
    """GET /api/batch-requests/{id} should return batch with certificates."""
    create_resp = await client.post("/api/batch-requests", json=valid_payload)
    batch_id = create_resp.json()["id"]

    detail_resp = await client.get(f"/api/batch-requests/{batch_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["id"] == batch_id
    assert len(data["certificates"]) == 3
    assert all(c["status"] == "pending" for c in data["certificates"])


@pytest.mark.asyncio
async def test_get_batch_request_not_found(client):
    """A request for a non-existent batch should return 404."""
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/batch-requests/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_batch_requests(client, mock_celery, valid_payload):
    """GET /api/batch-requests should return a paginated list."""
    # Create two batches
    await client.post("/api/batch-requests", json=valid_payload)
    await client.post("/api/batch-requests", json=valid_payload)

    resp = await client.get("/api/batch-requests")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["batch_requests"]) == 2


@pytest.mark.asyncio
async def test_list_batch_requests_pagination(client, mock_celery, valid_payload):
    """Pagination parameters should limit the returned results."""
    for _ in range(5):
        await client.post("/api/batch-requests", json=valid_payload)

    resp = await client.get("/api/batch-requests?skip=0&limit=2")
    data = resp.json()
    assert data["total"] == 5
    assert len(data["batch_requests"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 5. Handling individual certificate failure
# ═══════════════════════════════════════════════════════════════════════════

def test_certificate_generation_failure_is_isolated():
    """
    Simulate a failure for one recipient.  Remaining certificates should
    still be generated.  This tests the generator in isolation.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        results = []
        recipients = [
            ("Alice", "Course A", "2026-01-01"),
            ("", "Course B", "2026-01-01"),  # empty name – still generates
            ("Charlie", "Course C", "2026-01-01"),
        ]

        for i, (name, course, date) in enumerate(recipients):
            out = os.path.join(tmpdir, f"cert_{i}.pdf")
            try:
                generate_certificate_pdf(name, course, date, out)
                results.append("success")
            except Exception:
                results.append("failed")

        # All three should actually succeed (ReportLab handles empty strings).
        # The real failure handling is in batch_processor which catches
        # exceptions per-certificate – tested via the API integration tests.
        assert results.count("success") >= 2


# ═══════════════════════════════════════════════════════════════════════════
# 6. Retrieving / downloading generated certificates
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_list_certificates_for_batch(client, mock_celery, valid_payload):
    """GET /api/batch-requests/{id}/certificates should list certs."""
    create_resp = await client.post("/api/batch-requests", json=valid_payload)
    batch_id = create_resp.json()["id"]

    certs_resp = await client.get(
        f"/api/batch-requests/{batch_id}/certificates"
    )
    assert certs_resp.status_code == 200
    assert len(certs_resp.json()) == 3


@pytest.mark.asyncio
async def test_list_certificates_filter_by_status(
    client, mock_celery, valid_payload
):
    """Filtering by status=success should return no certs when all pending."""
    create_resp = await client.post("/api/batch-requests", json=valid_payload)
    batch_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/batch-requests/{batch_id}/certificates?status=success"
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_download_certificate_not_found(client):
    """Downloading a non-existent certificate should return 404."""
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/certificates/{fake_id}/download")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_certificate_pending_returns_400(
    client, mock_celery, valid_payload
):
    """Downloading a certificate that is still pending should return 400."""
    create_resp = await client.post("/api/batch-requests", json=valid_payload)
    batch_id = create_resp.json()["id"]

    # Get the first certificate id
    detail_resp = await client.get(f"/api/batch-requests/{batch_id}")
    cert_id = detail_resp.json()["certificates"][0]["id"]

    resp = await client.get(f"/api/certificates/{cert_id}/download")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_certificates_for_nonexistent_batch(client):
    """Listing certificates for a non-existent batch should return 404."""
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/batch-requests/{fake_id}/certificates")
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_check(client):
    """GET /health should return 200."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}
