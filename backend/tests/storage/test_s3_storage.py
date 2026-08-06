from __future__ import annotations

# Standard library imports
from typing import Any, Dict, List, Optional

# Third-party imports
from botocore.exceptions import ClientError
import pytest

# First-party imports
from models.configuration.s3_config import S3Config
from storage.s3.exceptions import (
    MTS3DeleteFailed,
    MTS3EmptyPayload,
    MTS3PayloadTooLarge,
    MTS3UnsupportedContentType,
    MTS3UploadFailed,
)
from storage.s3.s3_storage import S3Storage

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64
WAV = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 64


class _FakeS3Client:
    """Records the calls a test makes instead of reaching a bucket."""

    def __init__(self, failure: Optional[Exception] = None) -> None:
        """Store the failure to raise, if any.

        Args:
            failure (Optional[Exception]): Raised by every operation when set.
        """
        self.failure = failure
        self.puts: List[Dict[str, Any]] = []
        self.deletes: List[Dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> Dict[str, Any]:
        """Record an upload.

        Args:
            **kwargs (Any): The call's keyword arguments.

        Returns:
            Dict[str, Any]: An empty result.

        Raises:
            Exception: The configured failure, when one is set.
        """
        if self.failure is not None:
            raise self.failure
        self.puts.append(kwargs)
        return {}

    def delete_object(self, **kwargs: Any) -> Dict[str, Any]:
        """Record a deletion.

        Args:
            **kwargs (Any): The call's keyword arguments.

        Returns:
            Dict[str, Any]: An empty result.

        Raises:
            Exception: The configured failure, when one is set.
        """
        if self.failure is not None:
            raise self.failure
        self.deletes.append(kwargs)
        return {}


@pytest.fixture
def config() -> S3Config:
    """Return an object-store configuration for a MinIO-style deployment.

    Returns:
        S3Config: The configuration.
    """
    return S3Config(
        bucket="simple-erp",
        region="fr-par",
        endpoint_url="https://minio.internal",
        max_upload_bytes=1024,
    )


@pytest.fixture
def storage(config: S3Config) -> S3Storage:
    """Return a storage whose client is a recording fake.

    Args:
        config (S3Config): The object-store configuration.

    Returns:
        S3Storage: The storage, with the fake client already attached.
    """
    store = S3Storage(config=config)
    store.client = _FakeS3Client()
    return store


class TestContentTypeDetection:
    """Tests for deciding an upload's type from its own bytes."""

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            pytest.param(JPEG, "image/jpeg", id="jpeg"),
            pytest.param(PNG, "image/png", id="png"),
            pytest.param(WEBP, "image/webp", id="webp"),
        ],
    )
    def test_accepted_formats_are_detected(
        self, storage: S3Storage, payload: bytes, expected: str
    ) -> None:
        """Each accepted image format is recognised by its signature."""
        assert storage.detect_content_type(payload) == expected

    def test_an_empty_upload_is_rejected(self, storage: S3Storage) -> None:
        """A zero-byte file is not an image."""
        with pytest.raises(MTS3EmptyPayload):
            storage.detect_content_type(b"")

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(b"<svg xmlns='...'></svg>", id="Invalid - svg"),
            pytest.param(b"GIF89a" + b"\x00" * 32, id="Invalid - gif"),
            pytest.param(b"%PDF-1.7" + b"\x00" * 32, id="Invalid - pdf"),
            pytest.param(b"\x00" * 32, id="Invalid - no signature"),
        ],
    )
    def test_other_formats_are_rejected(
        self, storage: S3Storage, payload: bytes
    ) -> None:
        """Anything that is not an accepted image is refused.

        Notes:
            SVG matters most here: it is an image to a browser and a script
            host to an attacker.
        """
        with pytest.raises(MTS3UnsupportedContentType):
            storage.detect_content_type(payload)

    def test_a_riff_container_that_is_not_webp_is_rejected(
        self, storage: S3Storage
    ) -> None:
        """``RIFF`` also introduces WAV and AVI, so the tag is checked too."""
        with pytest.raises(MTS3UnsupportedContentType):
            storage.detect_content_type(WAV)

    async def test_the_declared_content_type_is_ignored(
        self, storage: S3Storage
    ) -> None:
        """The stored type comes from the bytes, never from the client.

        Notes:
            A client controls its own Content-Type header completely. A bucket
            serving attacker-chosen types is how a stored file becomes a stored
            cross-site-scripting payload.
        """
        await storage.upload_photo("hca-1", PNG)
        assert storage.client.puts[0]["ContentType"] == "image/png"


class TestUpload:
    """Tests for storing a photograph."""

    async def test_upload_returns_the_public_url(self, storage: S3Storage) -> None:
        """The stored object's URL is what the record will hold."""
        url = await storage.upload_photo("hca-1", JPEG)
        assert url.startswith("https://minio.internal/simple-erp/hca-photos/hca-1/")
        assert url.endswith(".jpg")

    async def test_the_key_lives_under_the_photo_prefix(
        self, storage: S3Storage
    ) -> None:
        """Every photograph is written under the configured prefix."""
        await storage.upload_photo("hca-1", JPEG)
        assert storage.client.puts[0]["Key"].startswith("hca-photos/hca-1/")

    async def test_the_key_is_generated_not_taken_from_the_upload(
        self, storage: S3Storage
    ) -> None:
        """Two uploads for one assistant never collide.

        Notes:
            A generated key is also what stops a crafted filename containing
            ``../`` from writing outside the photo prefix.
        """
        first = await storage.upload_photo("hca-1", JPEG)
        second = await storage.upload_photo("hca-1", JPEG)
        assert first != second

    async def test_an_oversized_upload_is_rejected(self, storage: S3Storage) -> None:
        """The configured size limit is enforced before anything is written."""
        with pytest.raises(MTS3PayloadTooLarge):
            await storage.upload_photo("hca-1", JPEG + b"\x00" * 2048)
        assert storage.client.puts == []

    async def test_a_failed_write_raises(self, config: S3Config) -> None:
        """A bucket error surfaces as an upload failure."""
        store = S3Storage(config=config)
        store.client = _FakeS3Client(
            failure=ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
        )
        with pytest.raises(MTS3UploadFailed):
            await store.upload_photo("hca-1", JPEG)

    async def test_the_object_is_marked_immutable(self, storage: S3Storage) -> None:
        """A generated key never changes content, so it can cache forever."""
        await storage.upload_photo("hca-1", JPEG)
        assert "immutable" in storage.client.puts[0]["CacheControl"]


class TestDelete:
    """Tests for removing a photograph."""

    async def test_delete_removes_the_object(self, storage: S3Storage) -> None:
        """A stored photograph is deleted by its URL."""
        url = await storage.upload_photo("hca-1", JPEG)
        assert await storage.delete_photo(url) is True
        assert storage.client.deletes[0]["Bucket"] == "simple-erp"

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param(
                "https://minio.internal/simple-erp/secrets/database-dump.sql",
                id="Invalid - outside the photo prefix",
            ),
            pytest.param(
                "https://minio.internal/simple-erp/", id="Invalid - bucket root"
            ),
            pytest.param("", id="Invalid - empty"),
            pytest.param("not-a-url", id="Invalid - not a url"),
        ],
    )
    async def test_a_url_outside_the_photo_prefix_is_refused(
        self, storage: S3Storage, url: str
    ) -> None:
        """Only objects under the photo prefix may be deleted.

        Notes:
            Without this, passing an arbitrary URL would let a caller delete
            any object in the bucket.
        """
        assert await storage.delete_photo(url) is False
        assert storage.client.deletes == []

    async def test_a_failed_delete_raises(self, config: S3Config) -> None:
        """A bucket error surfaces as a delete failure."""
        store = S3Storage(config=config)
        store.client = _FakeS3Client(
            failure=ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")
        )
        with pytest.raises(MTS3DeleteFailed):
            await store.delete_photo(
                "https://minio.internal/simple-erp/hca-photos/hca-1/abc.jpg"
            )


class TestKeyResolution:
    """Tests for turning a stored URL back into an object key."""

    def test_a_path_style_url_resolves(self, storage: S3Storage) -> None:
        """The bucket segment is stripped from a path-style URL."""
        key = storage.key_for_url(
            "https://minio.internal/simple-erp/hca-photos/hca-1/abc.jpg"
        )
        assert key == "hca-photos/hca-1/abc.jpg"

    def test_a_virtual_host_url_resolves(self, storage: S3Storage) -> None:
        """A virtual-host URL carries no bucket segment in its path."""
        key = storage.key_for_url(
            "https://simple-erp.s3.fr-par.amazonaws.com/hca-photos/hca-1/abc.jpg"
        )
        assert key == "hca-photos/hca-1/abc.jpg"

    def test_a_foreign_url_does_not_resolve(self, storage: S3Storage) -> None:
        """A URL that is not a stored photograph resolves to nothing."""
        assert storage.key_for_url("https://evil.example.com/pic.jpg") is None


class TestPublicUrlConstruction:
    """Tests for building the URL a stored object is served at."""

    def test_a_public_base_url_wins(self) -> None:
        """A CDN in front of the bucket is what browsers should fetch.

        Notes:
            Deriving the URL from the write endpoint instead would produce
            links that only work from inside the cluster.
        """
        config = S3Config(
            bucket="simple-erp",
            endpoint_url="https://minio.internal",
            public_base_url="https://cdn.example.com",
        )
        assert config.build_public_url("hca-photos/x.jpg") == (
            "https://cdn.example.com/hca-photos/x.jpg"
        )

    def test_a_custom_endpoint_uses_path_style(self) -> None:
        """MinIO and most compatible services serve path style."""
        config = S3Config(bucket="simple-erp", endpoint_url="https://minio.internal")
        assert config.build_public_url("hca-photos/x.jpg") == (
            "https://minio.internal/simple-erp/hca-photos/x.jpg"
        )

    def test_aws_uses_the_virtual_host_form(self) -> None:
        """With no endpoint configured the AWS default applies."""
        config = S3Config(bucket="simple-erp", region="eu-west-3")
        assert config.build_public_url("hca-photos/x.jpg") == (
            "https://simple-erp.s3.eu-west-3.amazonaws.com/hca-photos/x.jpg"
        )
