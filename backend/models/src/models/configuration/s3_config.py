from __future__ import annotations

# Standard library imports
import os
from typing import ClassVar, Optional, Tuple, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTS3ConfigInvalidBucket,
    MTS3ConfigInvalidCredentialEnv,
    MTS3ConfigInvalidEndpointUrl,
    MTS3ConfigInvalidMaxUploadBytes,
    MTS3ConfigInvalidPhotoPrefix,
    MTS3ConfigInvalidPublicBaseUrl,
    MTS3ConfigInvalidRegion,
    MTS3ConfigMissingCredentials,
)


class S3Config(BaseModel):
    """Settings for the object store holding assistant photographs.

    Attributes:
        DEFAULT_PHOTO_KEY_PREFIX (ClassVar[str]): Key prefix every photo is
            written under.
        ALLOWED_PHOTO_CONTENT_TYPES (ClassVar[Tuple[str, ...]]): Image types
            accepted for upload.
        MAX_ALLOWED_UPLOAD_BYTES (ClassVar[int]): Hard ceiling on the
            configurable upload limit.
        bucket (str): Bucket holding the photographs.
        region (str): Region the bucket lives in.
        endpoint_url (Optional[str]): Explicit endpoint, for a MinIO or
            Scaleway deployment. ``None`` uses the AWS default for the region.
        public_base_url (Optional[str]): Base the stored photo URL is built
            from. ``None`` derives it from the endpoint and bucket.
        access_key_env (str): Name of the environment variable holding the
            access key.
        secret_key_env (str): Name of the environment variable holding the
            secret key.
        photo_key_prefix (str): Key prefix every photo is written under.
        max_upload_bytes (int): Largest photograph accepted.

    Notes:
        - Credentials are named by environment variable, never carried here, so
          the configuration file stays safe to commit.
        - ``public_base_url`` exists because the URL a browser fetches is not
          always the endpoint the backend writes through: behind a CDN, or a
          MinIO instance reachable at one address inside the cluster and another
          outside it, the two differ. Deriving one from the other would produce
          links that work only from inside.
    """

    DEFAULT_PHOTO_KEY_PREFIX: ClassVar[str] = "hca-photos/"
    ALLOWED_PHOTO_CONTENT_TYPES: ClassVar[Tuple[str, ...]] = (
        "image/jpeg",
        "image/png",
        "image/webp",
    )
    MAX_ALLOWED_UPLOAD_BYTES: ClassVar[int] = 25 * 1024 * 1024

    bucket: str = Field(default="simple-erp", description="Bucket holding photographs.")
    region: str = Field(default="fr-par", description="Region the bucket lives in.")
    endpoint_url: Optional[str] = Field(
        default=None,
        description="Explicit S3 endpoint, or None for the AWS default.",
    )
    public_base_url: Optional[str] = Field(
        default=None,
        description="Base the stored photo URL is built from, or None.",
    )
    access_key_env: str = Field(
        default="S3_ACCESS_KEY",
        description="Environment variable holding the access key.",
    )
    secret_key_env: str = Field(
        default="S3_SECRET_KEY",
        description="Environment variable holding the secret key.",
    )
    photo_key_prefix: str = Field(
        default=DEFAULT_PHOTO_KEY_PREFIX,
        description="Key prefix every photograph is written under.",
    )
    max_upload_bytes: int = Field(
        default=5 * 1024 * 1024,
        description="Largest photograph accepted, in bytes.",
    )

    @field_validator("bucket", mode="before")
    def validate_bucket(cls, value: Optional[str]) -> str:
        """Validates that ``bucket`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``bucket`` value.

        Returns:
            str: The stripped bucket name.

        Raises:
            MTS3ConfigInvalidBucket: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTS3ConfigInvalidBucket(
                f"Invalid bucket: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("region", mode="before")
    def validate_region(cls, value: Optional[str]) -> str:
        """Validates that ``region`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``region`` value.

        Returns:
            str: The stripped region name.

        Raises:
            MTS3ConfigInvalidRegion: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTS3ConfigInvalidRegion(
                f"Invalid region: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("endpoint_url", mode="before")
    def validate_endpoint_url(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``endpoint_url`` is ``None`` or an absolute URL.

        Args:
            value (Optional[str]): Raw ``endpoint_url`` value.

        Returns:
            Optional[str]: The URL without a trailing slash, or ``None``.

        Raises:
            MTS3ConfigInvalidEndpointUrl: If ``value`` is neither ``None`` nor
                an ``http``/``https`` URL.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip().startswith(
            ("http://", "https://")
        ):
            raise MTS3ConfigInvalidEndpointUrl(
                f"Invalid endpoint_url: {value!r}. "
                f"Must be an http or https URL, or None."
            )
        return value.strip().rstrip("/")

    @field_validator("public_base_url", mode="before")
    def validate_public_base_url(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``public_base_url`` is ``None`` or an absolute URL.

        Args:
            value (Optional[str]): Raw ``public_base_url`` value.

        Returns:
            Optional[str]: The URL without a trailing slash, or ``None``.

        Raises:
            MTS3ConfigInvalidPublicBaseUrl: If ``value`` is neither ``None``
                nor an ``http``/``https`` URL.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip().startswith(
            ("http://", "https://")
        ):
            raise MTS3ConfigInvalidPublicBaseUrl(
                f"Invalid public_base_url: {value!r}. "
                f"Must be an http or https URL, or None."
            )
        return value.strip().rstrip("/")

    @field_validator("access_key_env", "secret_key_env", mode="before")
    def validate_credential_env(cls, value: Optional[str]) -> str:
        """Validates that a credential environment-variable name is given.

        Args:
            value (Optional[str]): Raw environment-variable name.

        Returns:
            str: The stripped name.

        Raises:
            MTS3ConfigInvalidCredentialEnv: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTS3ConfigInvalidCredentialEnv(
                f"Invalid credential env name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("photo_key_prefix", mode="before")
    def validate_photo_key_prefix(cls, value: Optional[str]) -> str:
        """Validates that ``photo_key_prefix`` is a slash-terminated prefix.

        Args:
            value (Optional[str]): Raw ``photo_key_prefix`` value. ``None``
                falls back to :attr:`DEFAULT_PHOTO_KEY_PREFIX`.

        Returns:
            str: The prefix, guaranteed to end in a slash.

        Raises:
            MTS3ConfigInvalidPhotoPrefix: If ``value`` is neither ``None`` nor
                a non-empty string, or if it starts with a slash.

        Notes:
            A leading slash is rejected because S3 would treat it as an empty
            first path segment, producing keys like ``//hca-photos/x.jpg``
            that are awkward to list and impossible to delete by prefix.

            The trailing slash is added rather than demanded, so a prefix
            configured without one still groups its objects into a folder.
        """
        if value is None:
            return cls.DEFAULT_PHOTO_KEY_PREFIX
        if not isinstance(value, str) or not value.strip():
            raise MTS3ConfigInvalidPhotoPrefix(
                f"Invalid photo_key_prefix: {value!r}. Must be a non-empty string."
            )
        stripped = value.strip()
        if stripped.startswith("/"):
            raise MTS3ConfigInvalidPhotoPrefix(
                f"Invalid photo_key_prefix: {value!r}. Must not start with a slash."
            )
        return stripped if stripped.endswith("/") else f"{stripped}/"

    @field_validator("max_upload_bytes", mode="before")
    def validate_max_upload_bytes(cls, value: Union[int, str, None]) -> int:
        """Validates that ``max_upload_bytes`` is a sane positive size.

        Args:
            value (Union[int, str, None]): Raw ``max_upload_bytes`` value.

        Returns:
            int: The validated size.

        Raises:
            MTS3ConfigInvalidMaxUploadBytes: If ``value`` is not a positive
                integer, or exceeds :attr:`MAX_ALLOWED_UPLOAD_BYTES`.

        Notes:
            The ceiling exists because the upload is buffered in memory to be
            size-checked and content-sniffed before it reaches the bucket; a
            mistyped limit would otherwise let one request exhaust the
            process's memory.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTS3ConfigInvalidMaxUploadBytes(
                f"Invalid max_upload_bytes: {value!r}. "
                f"Must be a strictly positive integer."
            )
        if value <= 0:
            raise MTS3ConfigInvalidMaxUploadBytes(
                f"Invalid max_upload_bytes: {value!r}. Must be strictly positive."
            )
        if value > cls.MAX_ALLOWED_UPLOAD_BYTES:
            raise MTS3ConfigInvalidMaxUploadBytes(
                f"Invalid max_upload_bytes: {value!r}. "
                f"Must be at most {cls.MAX_ALLOWED_UPLOAD_BYTES}."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def get_access_key(self) -> str:
        """Return the access key from the environment.

        Returns:
            str: The resolved access key.

        Raises:
            MTS3ConfigMissingCredentials: If the variable is unset or empty.
        """
        key = os.environ.get(self.access_key_env, "")
        if not key:
            raise MTS3ConfigMissingCredentials(
                f"Environment variable {self.access_key_env!r} is not set. "
                f"It must hold the S3 access key."
            )
        return key

    def get_secret_key(self) -> str:
        """Return the secret key from the environment.

        Returns:
            str: The resolved secret key.

        Raises:
            MTS3ConfigMissingCredentials: If the variable is unset or empty.
        """
        secret = os.environ.get(self.secret_key_env, "")
        if not secret:
            raise MTS3ConfigMissingCredentials(
                f"Environment variable {self.secret_key_env!r} is not set. "
                f"It must hold the S3 secret key."
            )
        return secret

    def build_public_url(self, key: str) -> str:
        """Return the URL a stored object is reachable at.

        Args:
            key (str): The object key.

        Returns:
            str: The absolute URL.

        Notes:
            Prefers ``public_base_url`` when configured, then the endpoint in
            path style, and finally the AWS virtual-host form. Path style is
            used for a custom endpoint because MinIO and most S3-compatible
            services serve that shape without per-bucket DNS.
        """
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
