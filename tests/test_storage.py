from io import BytesIO
from types import SimpleNamespace

from app.core.storage import upload_file


class FakeMinio:
    def __init__(self) -> None:
        self.created_buckets: list[str] = []
        self.uploaded: dict[str, object] | None = None

    def bucket_exists(self, bucket: str) -> bool:
        return False

    def make_bucket(self, bucket: str) -> None:
        self.created_buckets.append(bucket)

    def put_object(self, **kwargs: object) -> SimpleNamespace:
        self.uploaded = kwargs
        return SimpleNamespace(
            bucket_name=kwargs["bucket_name"],
            object_name=kwargs["object_name"],
            etag="test-etag",
            version_id=None,
        )


def test_upload_file_creates_bucket_and_uploads_stream() -> None:
    client = FakeMinio()
    data = BytesIO(b"roadbogo")

    result = upload_file(
        data,
        object_name="routes/test.txt",
        length=8,
        content_type="text/plain",
        bucket="test-bucket",
        client=client,  # type: ignore[arg-type]
    )

    assert client.created_buckets == ["test-bucket"]
    assert client.uploaded is not None
    assert client.uploaded["data"] is data
    assert result.object_name == "routes/test.txt"
    assert result.etag == "test-etag"
