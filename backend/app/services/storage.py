import logging
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_r2_client():
    """Create and return a boto3 S3 client configured for Cloudflare R2."""
    settings = get_settings()

    if not settings.R2_ENDPOINT_URL or "your-account-id" in settings.R2_ENDPOINT_URL:
        raise ValueError("R2_ENDPOINT_URL is not configured. Set it in .env file.")

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
        region_name="auto",
    )


def _generate_key(original_filename: str) -> str:
    """Generate a unique object key for R2 storage.

    Format: invoices/YYYY/MM/uuid-originalname
    """
    now = datetime.now(timezone.utc)
    unique_id = uuid.uuid4().hex[:12]
    # Sanitize filename: only keep alphanumeric, dots, dashes, underscores
    safe_name = "".join(
        c if c.isalnum() or c in (".", "-", "_") else "_"
        for c in original_filename
    )
    return f"invoices/{now.year}/{now.month:02d}/{unique_id}-{safe_name}"


async def upload_file(
    file_bytes: bytes, filename: str, content_type: str
) -> str:
    """Upload a file to Cloudflare R2 and return the object key.

    Args:
        file_bytes: The raw file content.
        filename: Original filename.
        content_type: MIME type (e.g. 'image/jpeg', 'application/pdf').

    Returns:
        The R2 object key (path) of the uploaded file.
    """
    settings = get_settings()
    client = _get_r2_client()
    key = _generate_key(filename)

    try:
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
        logger.info("Uploaded file to R2: %s", key)
        return key
    except ClientError as e:
        logger.error("Failed to upload to R2: %s", e)
        raise


async def download_file(key: str) -> bytes:
    """Download a file from R2 by its object key.

    Args:
        key: The R2 object key.

    Returns:
        The file content as bytes.
    """
    settings = get_settings()
    client = _get_r2_client()

    try:
        response = client.get_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
        )
        return response["Body"].read()
    except ClientError as e:
        logger.error("Failed to download from R2: %s", e)
        raise


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for viewing a file from R2.

    Args:
        key: The R2 object key.
        expires_in: URL expiration time in seconds (default 1 hour).

    Returns:
        Presigned URL string.
    """
    settings = get_settings()
    client = _get_r2_client()

    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
        return url
    except ClientError as e:
        logger.error("Failed to generate presigned URL: %s", e)
        raise


async def delete_file(key: str) -> None:
    """Delete a file from R2.

    Args:
        key: The R2 object key to delete.
    """
    settings = get_settings()
    client = _get_r2_client()

    try:
        client.delete_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
        )
        logger.info("Deleted file from R2: %s", key)
    except ClientError as e:
        logger.error("Failed to delete from R2: %s", e)
        raise
