from __future__ import annotations

# Standard library imports
import asyncio
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

# Third-party imports
import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

# First-party imports
from models.configuration.s3_config import S3Config
from storage.s3.exceptions import (
    MTS3BucketUnavailable,
    MTS3DeleteFailed,
    MTS3EmptyPayload,
    MTS3PayloadTooLarge,
    MTS3UnsupportedContentType,
    MTS3UploadFailed,
)


class S3Storage:
    """Stores and removes assistant photographs in an S3 bucket.

    Attributes:
        CONTENT_TYPE_EXTENSIONS (ClassVar[Dict[str, str]]): File extension per
            accepted content type.
        MAGIC_SIGNATURES (ClassVar[Tuple[Tuple[bytes, str], ...]]): Leading
            bytes identifying each accepted image format.
        CACHE_CONTROL (ClassVar[str]): Cache header written with every object.
        config (S3Config): Bucket and credential settings.
        logger (Logger): Logger for object-store operations.

    Notes:
        - ``boto3`` is synchronous, so every call is pushed onto a worker thread
          with :func:`asyncio.to_thread`. Calling it directly would block the
          event loop for the whole duration of the transfer, stalling every other
          request in the process.
        - The content type is decided from the file's own leading bytes, not from
          the ``Content-Type`` header the client sent. A client controls that
          header completely, and a bucket serving attacker-chosen content types
          is how a stored file becomes a stored cross-site-scripting payload.
        - The object key is generated, never taken from the upload's filename. A
          filename can carry ``../`` or a leading slash, and using it would let a
          caller write outside the photo prefix.
    """

    CONTENT_TYPE_EXTENSIONS: ClassVar[Dict[str, str]] = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    MAGIC_SIGNATURES: ClassVar[Tuple[Tuple[bytes, str], ...]] = (
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"RIFF", "image/webp"),
    )
    CACHE_CONTROL: ClassVar[str] = "public, max-age=31536000, immutable"

    def __init__(self, config: S3Config, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the storage without opening a connection.

        Args:
            config (S3Config): Bucket and credential settings.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            No client is built here. Constructing one resolves credentials,
            which would make importing this class fail on a machine that has
            none — including during a test collection that never uploads
            anything.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.client: Optional[BaseClient] = None
        self.logger.debug(
            "S3Storage created for bucket %s in %s.",
            self.config.bucket,
            self.config.region,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def get_client(self) -> BaseClient:
        """Return the boto3 S3 client, building it on first use.

        Returns:
            BaseClient: The configured client.

        Raises:
            MTS3BucketUnavailable: If credentials are missing or the client
                cannot be constructed.
        """
        if self.client is not None:
            return self.client
        try:
            self.client = boto3.client(
                "s3",
                region_name=self.config.region,
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=self.config.get_access_key(),
                aws_secret_access_key=self.config.get_secret_key(),
                config=BotoConfig(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        except Exception as exc:  # noqa: BLE001 - reported as unavailable
            self.logger.error(
                "Could not build the S3 client for bucket %s: %s.",
                self.config.bucket,
                exc,
            )
            raise MTS3BucketUnavailable(
                f"The object store for bucket {self.config.bucket!r} is not "
                f"available: {exc}."
            ) from exc
        self.logger.info("Built the S3 client for bucket %s.", self.config.bucket)
        return self.client

    def detect_content_type(self, payload: bytes) -> str:
        """Return the image type a payload actually is.

        Args:
            payload (bytes): The uploaded bytes.

        Returns:
            str: The detected content type.

        Raises:
            MTS3EmptyPayload: If ``payload`` carries no bytes.
            MTS3UnsupportedContentType: If the leading bytes match no accepted
                image format.

        Notes:
            WebP is checked with both its ``RIFF`` container marker and the
            ``WEBP`` tag at offset 8: ``RIFF`` alone also introduces WAV and
            AVI files, which would otherwise be accepted as images.
        """
        if not payload:
            self.logger.warning("Refused an empty upload.")
            raise MTS3EmptyPayload("The uploaded file is empty.")
        for signature, content_type in self.MAGIC_SIGNATURES:
            if not payload.startswith(signature):
                continue
            if content_type == "image/webp" and payload[8:12] != b"WEBP":
                continue
            self.logger.debug("Detected an upload of type %s.", content_type)
            return content_type
        self.logger.warning(
            "Refused an upload whose leading bytes match no accepted image type."
        )
        raise MTS3UnsupportedContentType(
            f"The uploaded file is not an accepted image. Must be one of: "
            f"{', '.join(sorted(self.CONTENT_TYPE_EXTENSIONS))}."
        )

    def build_photo_key(self, hca_id: str, content_type: str) -> str:
        """Return the object key a photograph is written under.

        Args:
            hca_id (str): The assistant the photograph belongs to.
            content_type (str): The detected image type.

        Returns:
            str: The key, under the configured photo prefix.

        Notes:
            A random component is appended so replacing a photograph writes a
            new key rather than overwriting the old one. Overwriting would
            leave every cached copy — browser, CDN — showing the previous
            image behind an unchanged URL.
        """
        extension = self.CONTENT_TYPE_EXTENSIONS[content_type]
        return f"{self.config.photo_key_prefix}{hca_id}/{uuid4().hex}.{extension}"

    async def upload_photo(self, hca_id: str, payload: bytes) -> str:
        """Store an assistant's photograph and return its URL.

        Args:
            hca_id (str): The assistant the photograph belongs to.
            payload (bytes): The image bytes.

        Returns:
            str: The URL the stored object is reachable at.

        Raises:
            MTS3EmptyPayload: If the upload carries no bytes.
            MTS3UnsupportedContentType: If the upload is not an accepted image.
            MTS3PayloadTooLarge: If the upload exceeds the configured size.
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3UploadFailed: If the object could not be written.
        """
        if len(payload) > self.config.max_upload_bytes:
            self.logger.warning(
                "Refused a %d-byte upload for hca %s; the limit is %d.",
                len(payload),
                hca_id,
                self.config.max_upload_bytes,
            )
            raise MTS3PayloadTooLarge(
                f"The uploaded file is {len(payload)} bytes; the limit is "
                f"{self.config.max_upload_bytes}."
            )
        content_type = self.detect_content_type(payload)
        key = self.build_photo_key(hca_id, content_type)
        client = self.get_client()
        self.logger.info(
            "Uploading a %d-byte %s photograph for hca %s to %s.",
            len(payload),
            content_type,
            hca_id,
            key,
        )
        try:
            await asyncio.to_thread(
                client.put_object,
                Bucket=self.config.bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
                CacheControl=self.CACHE_CONTROL,
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error(
                "Failed to upload the photograph for hca %s: %s.", hca_id, exc
            )
            raise MTS3UploadFailed(f"Could not store the photograph: {exc}.") from exc
        url = self.config.build_public_url(key)
        self.logger.info("Stored the photograph for hca %s at %s.", hca_id, url)
        return url

    async def delete_photo(self, photo_url: str) -> bool:
        """Remove a stored photograph.

        Args:
            photo_url (str): The URL the photograph is reachable at.

        Returns:
            bool: ``True`` when the object was removed, ``False`` when the URL
            does not belong to this bucket.

        Raises:
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3DeleteFailed: If the object could not be removed.

        Notes:
            A URL that does not resolve to a key under the configured photo
            prefix is refused rather than deleted. Without that check, passing
            an arbitrary URL would let a caller delete any object in the
            bucket.
        """
        key = self.key_for_url(photo_url)
        if key is None:
            self.logger.warning(
                "Refused to delete %s: it is not a photograph in this bucket.",
                photo_url,
            )
            return False
        client = self.get_client()
        self.logger.info("Deleting the photograph at %s.", key)
        try:
            await asyncio.to_thread(
                client.delete_object, Bucket=self.config.bucket, Key=key
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error("Failed to delete the photograph %s: %s.", key, exc)
            raise MTS3DeleteFailed(f"Could not remove the photograph: {exc}.") from exc
        self.logger.debug("Deleted the photograph at %s.", key)
        return True

    def key_for_url(self, photo_url: str) -> Optional[str]:
        """Return the object key a photograph URL points at.

        Args:
            photo_url (str): The URL to resolve.

        Returns:
            Optional[str]: The key, or ``None`` when the URL is not a
            photograph stored by this configuration.

        Notes:
            The path is matched against the configured photo prefix after the
            bucket segment is stripped, so both the virtual-host and path-style
            URL forms resolve to the same key.
        """
        if not isinstance(photo_url, str) or not photo_url.strip():
            return None
        path = urlparse(photo_url.strip()).path.lstrip("/")
        if not path:
            return None
        bucket_segment = f"{self.config.bucket}/"
        path = path.removeprefix(bucket_segment)
        if not path.startswith(self.config.photo_key_prefix):
            return None
        return path

    async def ensure_bucket(self) -> bool:
        """Verify the configured bucket is reachable.

        Returns:
            bool: ``True`` when the bucket answered.

        Notes:
            Reports rather than raises, so a start-up check can log a warning
            and carry on. Photographs are optional, and refusing to serve the
            whole API because the object store is down would take the planning
            with it.
        """
        try:
            client = self.get_client()
            await asyncio.to_thread(client.head_bucket, Bucket=self.config.bucket)
        except (BotoCoreError, ClientError, MTS3BucketUnavailable) as exc:
            self.logger.warning(
                "Bucket %s is not reachable: %s.", self.config.bucket, exc
            )
            return False
        self.logger.info("Bucket %s is reachable.", self.config.bucket)
        return True
