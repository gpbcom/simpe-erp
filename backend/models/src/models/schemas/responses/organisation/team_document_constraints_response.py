from __future__ import annotations

# Standard library imports
from typing import Iterable, List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTTeamDocumentConstraintsResponseInvalidContentTypes,
    MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes,
)


class TeamDocumentConstraintsResponse(BaseModel):
    """What a team's shared space accepts.

    Attributes:
        max_upload_bytes (int): Largest file the endpoint stores.
        accepted_content_types (List[str]): Media types the store recognises.

    Notes:
        - Published for the same reason the photograph limits are: a rejection
          that arrives after the whole file has crossed the network is a
          rejection somebody waited for.
        - The accepted types are the ones the store can **recognise from the
          file's own leading bytes**, not the ones a client may claim. That is
          why the list is short and why ``.docx`` and ``.xlsx`` appear as
          ``application/zip`` — they are Zip containers, and no signature tells
          them apart.
    """

    max_upload_bytes: int = Field(
        description="Largest file the endpoint stores, in bytes.",
    )
    accepted_content_types: List[str] = Field(
        description="Media types the store recognises.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("max_upload_bytes", mode="before")
    def validate_max_upload_bytes(cls, value: Union[int, float, None]) -> int:
        """Validates that ``max_upload_bytes`` is a positive integer.

        Args:
            value (Union[int, float, None]): Raw ``max_upload_bytes`` value.

        Returns:
            int: The validated limit.

        Raises:
            MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes: If ``value``
                is not a strictly positive integer.

        Notes:
            Booleans are rejected explicitly: ``True`` is an ``int`` in Python,
            and a limit of one byte would refuse every document while looking
            like a configured value.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes(
                f"Invalid max_upload_bytes: {value!r}. Must be an integer."
            )
        if value <= 0:
            raise MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes(
                f"Invalid max_upload_bytes: {value!r}. Must be strictly positive."
            )
        return value

    @field_validator("accepted_content_types", mode="before")
    def validate_accepted_content_types(
        cls, value: Optional[Iterable[str]]
    ) -> List[str]:
        """Validates that ``accepted_content_types`` lists non-empty strings.

        Args:
            value (Optional[Iterable[str]]): Raw media types.

        Returns:
            List[str]: The stripped, lower-cased media types.

        Raises:
            MTTeamDocumentConstraintsResponseInvalidContentTypes: If ``value``
                is not a non-empty sequence of non-empty strings.

        Notes:
            An empty list is refused. It would tell a client that nothing may be
            shared, which is never what the endpoint means — it means the
            store's signature table was not read.
        """
        if isinstance(value, str) or not isinstance(value, (list, tuple)):
            raise MTTeamDocumentConstraintsResponseInvalidContentTypes(
                f"Invalid accepted_content_types: {value!r}. "  # noqa: E501
                "Must be a list of "
                f"media types."
            )
        if not value:
            raise MTTeamDocumentConstraintsResponseInvalidContentTypes(
                "Invalid accepted_content_types: the list must not be empty."
            )
        validated: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTTeamDocumentConstraintsResponseInvalidContentTypes(
                    f"Invalid media type: {entry!r}. "  # noqa: E501
                    "Must be a non-empty string."
                )
            validated.append(entry.strip().lower())
        return validated
