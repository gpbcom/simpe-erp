from __future__ import annotations

# Standard library imports
from typing import Iterable, List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTPhotoConstraintsResponseInvalidContentTypes,
    MTPhotoConstraintsResponseInvalidMaxUploadBytes,
)


class PhotoConstraintsResponse(BaseModel):
    """What the photograph upload endpoint accepts.

    Attributes:
        max_upload_bytes (int): Largest photograph the endpoint stores.
        accepted_content_types (List[str]): Image types the store recognises.

    Notes:
        - Published so a client can refuse an oversized or unsupported file
          before uploading it rather than after — a rejection that arrives once
          the whole file has crossed the network is a rejection the user waited
          for.
        - The limits are read from the running configuration rather than
          restated here, so a deployment that raises the cap does not have to
          remember to change a second number.
    """

    max_upload_bytes: int = Field(
        description="Largest photograph the endpoint stores, in bytes.",
    )
    accepted_content_types: List[str] = Field(
        description="Image content types the store recognises.",
    )

    @field_validator("max_upload_bytes", mode="before")
    def validate_max_upload_bytes(cls, value: Union[int, float, None]) -> int:
        """Validates that ``max_upload_bytes`` is a positive integer.

        Args:
            value (Union[int, float, None]): Raw ``max_upload_bytes`` value.

        Returns:
            int: The validated limit.

        Raises:
            MTPhotoConstraintsResponseInvalidMaxUploadBytes: If ``value`` is
                not a strictly positive integer.

        Notes:
            Booleans are rejected explicitly: ``True`` is an ``int`` in Python,
            and a limit of one byte would reject every photograph while looking
            like a configured value.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTPhotoConstraintsResponseInvalidMaxUploadBytes(
                f"Invalid max_upload_bytes: {value!r}. Must be an integer."
            )
        if value <= 0:
            raise MTPhotoConstraintsResponseInvalidMaxUploadBytes(
                f"Invalid max_upload_bytes: {value!r}. Must be strictly positive."
            )
        return value

    @field_validator("accepted_content_types", mode="before")
    def validate_accepted_content_types(
        cls, value: Optional[Iterable[str]]
    ) -> List[str]:
        """Validates that ``accepted_content_types`` lists non-empty strings.

        Args:
            value (Optional[Iterable[str]]): Raw content types.

        Returns:
            List[str]: The stripped, lower-cased content types.

        Raises:
            MTPhotoConstraintsResponseInvalidContentTypes: If ``value`` is not
                a non-empty sequence of non-empty strings.

        Notes:
            An empty list is refused. It would tell a client that nothing can
            be uploaded, which is never what the endpoint means — it means the
            configuration was not read.
        """
        if isinstance(value, str) or not isinstance(value, (list, tuple)):
            raise MTPhotoConstraintsResponseInvalidContentTypes(
                f"Invalid accepted_content_types: {value!r}. Must be a list of "
                f"content types."
            )
        if not value:
            raise MTPhotoConstraintsResponseInvalidContentTypes(
                "Invalid accepted_content_types: the list must not be empty."
            )
        validated: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTPhotoConstraintsResponseInvalidContentTypes(
                    f"Invalid content type: {entry!r}. Must be a non-empty string."
                )
            validated.append(entry.strip().lower())
        return validated
