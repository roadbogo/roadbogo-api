from datetime import timedelta
from io import BytesIO
from minio import Minio
from app.core.config import settings
from app.core.exceptions import AppException


class FileStorage:
    def __init__(self, client=None, bucket=None):
        if client is None:
            if not settings.minio_access_key or not settings.minio_secret_key:
                raise AppException(
                    503, "FILE_STORAGE_NOT_CONFIGURED", "파일 저장소가 설정되지 않았습니다."
                )
            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        self.client = client
        self.bucket = bucket or settings.minio_bucket

    def put_object(self, key, data, mime):
        try:
            self.client.put_object(self.bucket, key, BytesIO(data), len(data), content_type=mime)
        except Exception as exc:
            raise AppException(
                503, "FILE_STORAGE_UNAVAILABLE", "파일 저장소를 사용할 수 없습니다."
            ) from exc

    def remove_object(self, key):
        self.client.remove_object(self.bucket, key)

    def presigned_get_url(self, key):
        try:
            return self.client.presigned_get_object(self.bucket, key, expires=timedelta(minutes=15))
        except Exception as exc:
            raise AppException(
                503, "FILE_STORAGE_UNAVAILABLE", "파일 저장소를 사용할 수 없습니다."
            ) from exc


def get_file_storage():
    return FileStorage()
