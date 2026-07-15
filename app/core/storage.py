from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from minio import Minio

from app.core.config import settings


@dataclass(frozen=True)
class UploadResult:
    bucket: str
    object_name: str
    etag: str
    version_id: str | None


def get_minio_client() -> Minio:
    """Create a MinIO client using the current application settings."""
    if not settings.minio_access_key or not settings.minio_secret_key:
        raise RuntimeError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be configured")

    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket(client: Minio, bucket: str) -> None:
    """Create the configured bucket when it does not exist."""
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def build_object_name(filename: str, directory: str | None = None) -> str:
    """Build a safe, unique object name while preserving the file extension."""
    suffix = Path(filename).suffix.lower()
    generated_name = f"{uuid4().hex}{suffix}"
    if not directory:
        return generated_name
    return f"{directory.strip('/')}/{generated_name}"


def upload_file(
    file: BinaryIO,
    *,
    object_name: str,
    length: int = -1,
    content_type: str = "application/octet-stream",
    bucket: str | None = None,
    create_bucket: bool = True,
    client: Minio | None = None,
) -> UploadResult:
    """Upload a binary stream, including ``fastapi.UploadFile.file``, to MinIO.

    Use ``length=-1`` when the stream length is unknown. MinIO then performs a
    multipart upload using the configured part size.
    """
    minio_client = client or get_minio_client()
    target_bucket = bucket or settings.minio_bucket

    if create_bucket:
        ensure_bucket(minio_client, target_bucket)

    response = minio_client.put_object(
        bucket_name=target_bucket,
        object_name=object_name,
        data=file,
        length=length,
        part_size=10 * 1024 * 1024 if length < 0 else 0,
        content_type=content_type,
    )
    return UploadResult(
        bucket=response.bucket_name,
        object_name=response.object_name,
        etag=response.etag,
        version_id=response.version_id,
    )


def upload_path(
    path: str | Path,
    *,
    object_name: str | None = None,
    content_type: str = "application/octet-stream",
    bucket: str | None = None,
    create_bucket: bool = True,
    client: Minio | None = None,
) -> UploadResult:
    """Upload a file from a local filesystem path."""
    source = Path(path)
    target_name = object_name or build_object_name(source.name)

    with source.open("rb") as file:
        return upload_file(
            file,
            object_name=target_name,
            length=source.stat().st_size,
            content_type=content_type,
            bucket=bucket,
            create_bucket=create_bucket,
            client=client,
        )
