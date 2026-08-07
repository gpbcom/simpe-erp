from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Type

# Third-party imports
from pydantic import (  # noqa: E501
    BaseModel,
    Field,
    HttpUrl,
    field_serializer,
    field_validator,
)

# First-party imports
from models.base.exceptions import (
    MTInvalidPersonException,
    MTPersonInvalidPhotoUrl,
)


class PortraitHolder(BaseModel):
    """A record that can carry a photograph of the person it describes.

    Attributes:
        PHOTO_KEY_PREFIX (ClassVar[str]): Object-store key prefix every
            photograph is written under. Mirrors
            :attr:`~models.configuration.s3_config.S3Config.DEFAULT_PHOTO_KEY_PREFIX`.
        INVALID_PHOTO_URL (ClassVar[Type[MTInvalidPersonException]]): Exception
            the holder raises for a URL it did not issue.
        photo_url (Optional[HttpUrl]): URL of the portrait in the object store,
            when one has been uploaded.

    Notes:
        - **A mixin, not a base.** It is inherited alongside
          :class:`~models.base.person.Person` by the two records that hold a
          photograph — :class:`~models.people.hca.Hca` and
          :class:`~models.auth.user.User` — rather than being folded into
          ``Person`` itself. Folding it in would put a ``photo_url`` on every
          customer and every job application, which is a field the API would
          then publish, the front-end would then render, and nobody would ever
          fill in.
        - The rule it carries is a **security** rule, which is why it is worth
          having in one place. A portrait is uploaded through the API and
          written under a fixed key prefix; requiring that prefix is what stops
          an arbitrary third-party URL being stored. Both holders render the
          image wherever the person appears, so a remote one would report every
          viewer to whoever hosts it — and two copies of that check are two
          chances for one of them to be relaxed.
        - Which *bucket* the URL belongs to cannot be checked here, since the
          model has no access to configuration. The object store re-checks that
          before deleting, where getting it wrong would remove somebody else's
          object.
    """

    PHOTO_KEY_PREFIX: ClassVar[str] = "hca-photos/"
    INVALID_PHOTO_URL: ClassVar[Type[MTInvalidPersonException]] = (
        MTPersonInvalidPhotoUrl
    )

    photo_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL of the portrait in the object store.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("photo_url", mode="before")
    def validate_photo_url(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``photo_url`` points at a stored photograph.

        Args:
            value (Optional[str]): Raw ``photo_url`` value.

        Returns:
            Optional[str]: The stripped URL, or ``None``.

        Raises:
            MTInvalidPersonException: The holder's :attr:`INVALID_PHOTO_URL`,
                if ``value`` is neither ``None`` nor an ``http``/``https`` URL
                whose path lies under :attr:`PHOTO_KEY_PREFIX`.

        Notes:
            The portrait is optional, so a blank string reads as "no photo"
            rather than being rejected — an empty form field must not block
            saving the record it sits on.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise cls.INVALID_PHOTO_URL(
                f"Invalid photo_url: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.startswith(("http://", "https://")):
            raise cls.INVALID_PHOTO_URL(
                f"Invalid photo_url: {stripped!r}. Must be an http or https URL."
            )
        if f"/{cls.PHOTO_KEY_PREFIX}" not in stripped:
            raise cls.INVALID_PHOTO_URL(
                f"Invalid photo_url: {stripped!r}. Must point at a photograph "
                f"stored by this application, under the "
                f"{cls.PHOTO_KEY_PREFIX!r} prefix."
            )
        return stripped

    ###############################
    # Fields Serialization Method #
    ###############################

    @field_serializer("photo_url")
    def serialize_photo_url(self, value: Optional[HttpUrl]) -> Optional[str]:
        """Serialize the portrait URL as plain text.

        Args:
            value (Optional[HttpUrl]): The URL to serialize.

        Returns:
            Optional[str]: The URL as a string, or ``None``.

        Notes:
            Written explicitly so a dump in ``python`` mode hands back a string
            rather than an ``HttpUrl``. The store column is text, and a URL
            object reaching it would be written as its ``repr``.
        """
        return str(value) if value is not None else None
