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


class _FakeBody:
    """The streaming body boto3 returns from ``get_object``."""

    def __init__(self, payload: bytes) -> None:
        """Store the bytes this body yields.

        Args:
            payload (bytes): What :meth:`read` returns.
        """
        self.payload = payload

    def read(self) -> bytes:
        """Return the whole body.

        Returns:
            bytes: The stored payload.
        """
        return self.payload


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
        self.gets: List[Dict[str, Any]] = []
        self.stored: bytes = PNG

    def get_object(self, **kwargs: Any) -> Dict[str, Any]:
        """Record a read and hand back the stored bytes.

        Args:
            **kwargs (Any): The call's keyword arguments.

        Returns:
            Dict[str, Any]: A result shaped like boto3's, whose ``Body`` reads.

        Raises:
            Exception: The configured failure, when one is set.
        """
        if self.failure is not None:
            raise self.failure
        self.gets.append(kwargs)
        return {"Body": _FakeBody(self.stored)}

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


class TestTheShippedConfigurationsServeTheirPhotos:
    """Tests that the URL each shipped configuration builds is fetchable.

    Notes:
        **These are tests of the configuration, not of the code**, and they
        exist because the code was right and the configuration was not.
        ``build_public_url`` appends the key straight onto ``public_base_url``
        — the CDN case it was written for is a host mapped at the bucket's
        root — while ``app.dev.yaml`` and ``app.docker.yaml`` both named the
        MinIO host alone. MinIO serves buckets path-style, so it read the key's
        first segment as the bucket and answered ``403 AccessDenied`` for a
        bucket called ``hca-photos``.

        Nothing caught it: the unit tests above assert the builder's three
        branches and pass, the upload succeeds, the row stores a URL, and the
        API returns 200. The only symptom is an avatar that renders as
        initials, which is also exactly what an account with no photograph
        looks like.
    """

    @pytest.mark.parametrize("path", ["conf/app.dev.yaml", "conf/app.docker.yaml"])
    def test_a_compose_configuration_names_the_bucket(self, path: str) -> None:
        """The browser-facing URL must address the bucket MinIO serves.

        Args:
            path (str): The shipped configuration to read.
        """
        # First-party imports
        from models.configuration.app_config import AppConfig

        config = AppConfig.load(path).s3
        built = config.build_public_url(f"{config.photo_key_prefix}person/x.jpg")

        assert f"/{config.bucket}/" in built, (
            f"{path} builds {built!r}, which names no bucket. MinIO will read "
            f"the key's first segment as one and refuse the object."
        )

    @pytest.mark.parametrize("path", ["conf/app.dev.yaml", "conf/app.docker.yaml"])
    def test_a_compose_configuration_is_reachable_from_a_browser(
        self, path: str
    ) -> None:
        """The host must be one a browser can resolve, not a compose alias.

        Args:
            path (str): The shipped configuration to read.

        Notes:
            The write endpoint is ``http://minio:9000``, which resolves only on
            the compose network. A stored URL naming it is a broken image on
            every screen that shows a face.
        """
        # First-party imports
        from models.configuration.app_config import AppConfig

        config = AppConfig.load(path).s3
        built = config.build_public_url("hca-photos/person/x.jpg")

        assert "//minio:" not in built, (
            f"{path} builds {built!r}, naming the in-network endpoint. A "
            f"browser cannot resolve 'minio'."
        )


class TestCompanyLogos:
    """Tests for the second prefix this store serves."""

    def test_a_logo_key_lands_under_its_own_prefix(self, storage: S3Storage) -> None:
        """Logos and photographs must not share a folder.

        Notes:
            They are removed by different rules — a logo outlives every
            assistant who ever worked for the agency — so a bulk cleanup of one
            prefix must not be able to reach the other.
        """
        key = storage.build_logo_key("company-1", "image/png")

        assert key.startswith("company-logos/company-1/")
        assert key.endswith(".png")
        assert not key.startswith(storage.config.photo_key_prefix)

    def test_two_uploads_never_reuse_a_key(self, storage: S3Storage) -> None:
        """Replacing a logo writes a new object rather than overwriting one.

        Notes:
            Overwriting would leave every cached copy — browser, CDN — showing
            the previous image behind an unchanged URL.
        """
        first = storage.build_logo_key("company-1", "image/png")
        second = storage.build_logo_key("company-1", "image/png")

        assert first != second

    async def test_uploading_a_logo_stores_it_and_returns_its_url(
        self, storage: S3Storage
    ) -> None:
        """The URL that comes back is what the record will point at."""
        url = await storage.upload_logo("company-1", PNG)

        client = storage.client
        assert isinstance(client, _FakeS3Client)
        assert len(client.puts) == 1
        assert client.puts[0]["ContentType"] == "image/png"
        assert client.puts[0]["Key"].startswith("company-logos/company-1/")
        assert "company-logos/company-1/" in url

    async def test_a_logo_is_typed_from_its_bytes_not_its_header(
        self, storage: S3Storage
    ) -> None:
        """A file that is not an image is refused, whatever it claims to be.

        Notes:
            A WAV file opens with ``RIFF`` exactly as a WebP does. Accepting it
            because of that marker is how a bucket ends up serving
            attacker-chosen content types.
        """
        with pytest.raises(MTS3UnsupportedContentType):
            await storage.upload_logo("company-1", WAV)

    async def test_an_oversized_logo_is_refused_before_it_is_written(
        self, storage: S3Storage
    ) -> None:
        """The size limit is the bucket's, not the photograph's."""
        with pytest.raises(MTS3PayloadTooLarge):
            await storage.upload_logo("company-1", PNG + b"\x00" * 2048)

        client = storage.client
        assert isinstance(client, _FakeS3Client)
        assert client.puts == []

    async def test_deleting_a_logo_removes_the_object(self, storage: S3Storage) -> None:
        """A URL under the logo prefix resolves to a key this store owns."""
        url = await storage.upload_logo("company-1", PNG)

        assert await storage.delete_logo(url) is True

        client = storage.client
        assert isinstance(client, _FakeS3Client)
        assert client.deletes[0]["Key"].startswith("company-logos/")

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param(
                "https://minio.internal/simple-erp/hca-photos/h-1/a.jpg",
                id="Invalid - a photograph, not a logo",
            ),
            pytest.param(
                "https://evil.example/anything.png", id="Invalid - another host"
            ),
            pytest.param("   ", id="Invalid - blank"),
        ],
    )
    async def test_deleting_something_that_is_not_a_logo_is_refused(
        self, storage: S3Storage, url: str
    ) -> None:
        """**The prefix check is what stops an arbitrary delete.**

        Args:
            storage (S3Storage): The store under test.
            url (str): The URL that must not resolve to a key.

        Notes:
            Without it, passing any URL would let a caller remove any object in
            the bucket — including every assistant's photograph.
        """
        assert await storage.delete_logo(url) is False

        client = storage.client
        assert isinstance(client, _FakeS3Client)
        assert client.deletes == []

    async def test_a_failed_delete_is_reported(self, storage: S3Storage) -> None:
        """A refusal from the bucket is not silently swallowed here."""
        url = await storage.upload_logo("company-1", PNG)
        storage.client = _FakeS3Client(
            failure=ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")
        )

        with pytest.raises(MTS3DeleteFailed):
            await storage.delete_logo(url)

    async def test_fetching_a_logo_returns_its_bytes(self, storage: S3Storage) -> None:
        """The quote renderer needs the image itself, not a link."""
        url = await storage.upload_logo("company-1", PNG)

        assert await storage.fetch_logo(url) == PNG

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param(
                "https://minio.internal/simple-erp/hca-photos/h-1/a.jpg",
                id="Not a logo",
            ),
            pytest.param("https://evil.example/anything.png", id="Another host"),
        ],
    )
    async def test_fetching_something_that_is_not_a_logo_yields_nothing(
        self, storage: S3Storage, url: str
    ) -> None:
        """The same prefix guard applies to reads.

        Args:
            storage (S3Storage): The store under test.
            url (str): The URL that must not resolve to a key.
        """
        assert await storage.fetch_logo(url) is None

    async def test_a_failed_fetch_reports_rather_than_raises(
        self, storage: S3Storage
    ) -> None:
        """**A quote must go out even when its letterhead cannot be read.**

        Notes:
            The only caller is the quote renderer. Raising would turn a
            cosmetic problem into a commercial one: the customer waiting for a
            priced offer would get nothing because a decoration was missing.
        """
        url = await storage.upload_logo("company-1", PNG)
        storage.client = _FakeS3Client(
            failure=ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        )

        assert await storage.fetch_logo(url) is None

    async def test_an_upload_failure_is_reported(self, storage: S3Storage) -> None:
        """A write that does not land must not look like one that did."""
        storage.client = _FakeS3Client(
            failure=ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
        )

        with pytest.raises(MTS3UploadFailed):
            await storage.upload_logo("company-1", PNG)

    def test_key_resolution_still_defaults_to_photographs(
        self, storage: S3Storage
    ) -> None:
        """The shared resolver must not have changed under its old callers.

        Notes:
            ``key_for_url`` grew a prefix argument so both kinds of image could
            share one path-resolution rule. Its default has to stay the photo
            prefix, or every existing caller would start refusing the URLs it
            wrote itself.
        """
        photo = "https://minio.internal/simple-erp/hca-photos/h-1/a.jpg"

        assert storage.key_for_url(photo) == "hca-photos/h-1/a.jpg"
        assert storage.key_for_url(photo, prefix="company-logos/") is None
