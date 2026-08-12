from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_serializer, field_validator

# First-party imports
from models.organisation.team.exceptions import (
    MTTeamDocumentInvalidCompanyId,
    MTTeamDocumentInvalidContentType,
    MTTeamDocumentInvalidDate,
    MTTeamDocumentInvalidDocumentKey,
    MTTeamDocumentInvalidFileName,
    MTTeamDocumentInvalidId,
    MTTeamDocumentInvalidSizeBytes,
    MTTeamDocumentInvalidTeamId,
    MTTeamDocumentInvalidUploadedBy,
)


class TeamDocument(BaseModel):
    """One file in a team's shared space.

    Attributes:
        KEY_PREFIX (ClassVar[str]): Object-store prefix every team document
            lives under.
        MAX_FILE_NAME_LENGTH (ClassVar[int]): Longest accepted file name.
        MAX_CONTENT_TYPE_LENGTH (ClassVar[int]): Longest accepted media type.
        PATH_SEPARATORS (ClassVar[str]): Characters a file name may not carry.
        id (Optional[str]): Identifier, populated on read from the store.
        team_id (str): The team whose space this file sits in.
        company_id (str): The company that team belongs to.
        file_name (str): What the uploader called it, shown and downloaded as.
        content_type (str): The media type the object store *sniffed*.
        size_bytes (int): How large the stored object is.
        document_key (str): Where the object lives, under :attr:`KEY_PREFIX`.
        uploaded_by (str): The account that added it.
        uploaded_by_name (str): That account's name at the time.
        created_at (Optional[datetime]): When it was added.

    Notes:
        - **The key is stored, never a URL**, which is the invoice's shape and
          not the portrait's. A team's documents are the agency's private
          paperwork; a public URL would make them readable by anybody who is
          sent one, forever, whatever the application later decided about
          permissions. Downloads go through an authenticated endpoint that
          resolves the key.
        - **The uploader's name is copied, not joined.** A file added by
          somebody who has since left still has to say who added it, and a join
          through a deleted account would print nothing — the same reasoning
          that copies the assistant's name onto an
          :class:`~models.planning.intervention.intervention.Intervention`.
        - `uploaded_by` carries no foreign key for the same reason: an audit
          trail must outlive the thing it names.
        - The content type is the **sniffed** one rather than the declared one.
          A browser's ``Content-Type`` is a claim by the uploader, and this
          value is echoed back on download.
    """

    KEY_PREFIX: ClassVar[str] = "team-documents/"
    MAX_FILE_NAME_LENGTH: ClassVar[int] = 255
    MAX_CONTENT_TYPE_LENGTH: ClassVar[int] = 128
    PATH_SEPARATORS: ClassVar[str] = "/\\"

    id: Optional[str] = Field(
        default=None, description="Identifier, assigned by the store."
    )
    team_id: str = Field(description="The team whose space this file sits in.")
    company_id: str = Field(description="The company that team belongs to.")
    file_name: str = Field(description="What the uploader called it.")
    content_type: str = Field(description="The media type that was detected.")
    size_bytes: int = Field(description="How large the stored object is.")
    document_key: str = Field(description="Where the object lives in the store.")
    uploaded_by: str = Field(description="The account that added it.")
    uploaded_by_name: str = Field(description="That account's name at the time.")
    created_at: Optional[datetime] = Field(
        default=None, description="When it was added."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id``, when given, is a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is stored.

        Raises:
            MTTeamDocumentInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTTeamDocumentInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("team_id", mode="before")
    def validate_team_id(cls, value: Optional[str]) -> str:
        """Validates that the owning team is named.

        Args:
            value (Optional[str]): Raw ``team_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTTeamDocumentInvalidTeamId: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamDocumentInvalidTeamId(
                f"Invalid team_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that the owning company is named.

        Args:
            value (Optional[str]): Raw ``company_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTTeamDocumentInvalidCompanyId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamDocumentInvalidCompanyId(
                f"Invalid company_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("file_name", mode="before")
    def validate_file_name(cls, value: Optional[str]) -> str:
        """Validates that the file name is usable and is not a path.

        Args:
            value (Optional[str]): Raw ``file_name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTTeamDocumentInvalidFileName: If ``value`` is not a non-empty
                string within :attr:`MAX_FILE_NAME_LENGTH`, or carries a path
                separator.

        Notes:
            A name with a separator is **refused rather than sanitised**. It is
            echoed into a ``Content-Disposition`` header and rendered as a link,
            and a value quietly stripped of its ``../`` is a value somebody
            meant to be dangerous — which is worth a refusal somebody sees
            rather than a repair nobody does.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamDocumentInvalidFileName(
                f"Invalid file_name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > cls.MAX_FILE_NAME_LENGTH:
            raise MTTeamDocumentInvalidFileName(
                f"Invalid file_name: {len(trimmed)} characters. Must be at most "
                f"{cls.MAX_FILE_NAME_LENGTH}."
            )
        if any(separator in trimmed for separator in cls.PATH_SEPARATORS):
            raise MTTeamDocumentInvalidFileName(
                f"Invalid file_name: {trimmed!r}. Must not contain a path separator."
            )
        return trimmed

    @field_validator("content_type", mode="before")
    def validate_content_type(cls, value: Optional[str]) -> str:
        """Validates that the content type looks like a media type.

        Args:
            value (Optional[str]): Raw ``content_type`` value.

        Returns:
            str: The lower-cased media type.

        Raises:
            MTTeamDocumentInvalidContentType: If ``value`` is not a non-empty
                ``type/subtype`` string within
                :attr:`MAX_CONTENT_TYPE_LENGTH`.

        Notes:
            Which types are *accepted* is the object store's decision, not this
            model's — it refuses a payload whose magic bytes it does not
            recognise. What is checked here is only that a stored record carries
            something a browser can be handed back.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamDocumentInvalidContentType(
                f"Invalid content_type: {value!r}. Must be a non-empty string."
            )
        cleaned = value.strip().lower()
        if len(cleaned) > cls.MAX_CONTENT_TYPE_LENGTH:
            raise MTTeamDocumentInvalidContentType(
                f"Invalid content_type: {len(cleaned)} characters. Must be at "
                f"most {cls.MAX_CONTENT_TYPE_LENGTH}."
            )
        if cleaned.count("/") != 1 or cleaned.startswith("/") or cleaned.endswith("/"):
            raise MTTeamDocumentInvalidContentType(
                f"Invalid content_type: {value!r}. Must be a media type such as "
                f"'application/pdf'."
            )
        return cleaned

    @field_validator("size_bytes", mode="before")
    def validate_size_bytes(cls, value: Union[int, str, None]) -> int:
        """Validates that the recorded size is a positive whole number.

        Args:
            value (Union[int, str, None]): Raw ``size_bytes`` value.

        Returns:
            int: The size in bytes.

        Raises:
            MTTeamDocumentInvalidSizeBytes: If ``value`` is not an integer
                greater than zero.

        Notes:
            Zero is refused. An empty object is not a document somebody meant to
            share, and the object store refuses an empty payload one layer down
            — a record claiming zero bytes could only come from a write that
            went wrong.
        """
        if isinstance(value, bool) or value is None:
            raise MTTeamDocumentInvalidSizeBytes(
                f"Invalid size_bytes: {value!r}. Must be a positive integer."
            )
        try:
            size = int(value)
        except (TypeError, ValueError):
            raise MTTeamDocumentInvalidSizeBytes(
                f"Invalid size_bytes: {value!r}. Must be a positive integer."
            ) from None
        if size <= 0:
            raise MTTeamDocumentInvalidSizeBytes(
                f"Invalid size_bytes: {size!r}. Must be greater than zero."
            )
        return size

    @field_validator("document_key", mode="before")
    def validate_document_key(cls, value: Optional[str]) -> str:
        """Validates that the object key lies under the team-document prefix.

        Args:
            value (Optional[str]): Raw ``document_key`` value.

        Returns:
            str: The trimmed key.

        Raises:
            MTTeamDocumentInvalidDocumentKey: If ``value`` is not a non-empty
                string under :attr:`KEY_PREFIX`.

        Notes:
            The key is what an authenticated download resolves, so one pointing
            outside this prefix would let a stored record address any object in
            the bucket — the invoices among them. Which *bucket* it belongs to
            cannot be checked here, because a model has no access to
            configuration; the object store re-checks that before deleting,
            where getting it wrong would remove somebody else's object.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamDocumentInvalidDocumentKey(
                f"Invalid document_key: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if not trimmed.startswith(cls.KEY_PREFIX):
            raise MTTeamDocumentInvalidDocumentKey(
                f"Invalid document_key: {trimmed!r}. Must lie under the "
                f"{cls.KEY_PREFIX!r} prefix."
            )
        return trimmed

    @field_validator("uploaded_by", "uploaded_by_name", mode="before")
    def validate_uploader(cls, value: Optional[str]) -> str:
        """Validates that the uploading account is named.

        Args:
            value (Optional[str]): Raw ``uploaded_by`` or ``uploaded_by_name``
                value.

        Returns:
            str: The trimmed value.

        Raises:
            MTTeamDocumentInvalidUploadedBy: If ``value`` is not a non-empty
                string.

        Notes:
            One rule for both halves, because both answer the same question and
            a file whose uploader is half-recorded is a file nobody can ask
            about. The deletion rule reads ``uploaded_by``, so an empty one
            would leave a document only a manager could remove.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamDocumentInvalidUploadedBy(
                f"Invalid uploader: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("created_at", mode="before")
    def validate_created_at(
        cls, value: Union[datetime, str, None]
    ) -> Optional[datetime]:
        """Validates that the timestamp is a datetime.

        Args:
            value (Union[datetime, str, None]): Raw ``created_at`` value.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTTeamDocumentInvalidDate: If ``value`` is neither ``None`` nor a
                datetime or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTTeamDocumentInvalidDate(
                    f"Invalid timestamp: {value!r}. Must be an ISO-8601 datetime."
                ) from None
        raise MTTeamDocumentInvalidDate(
            f"Invalid timestamp: {value!r}. Must be a datetime."
        )

    @field_serializer("created_at")
    def serialize_created_at(self, value: Optional[datetime]) -> Optional[str]:
        """Serialise the timestamp as an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialise.

        Returns:
            Optional[str]: The ISO-8601 form, or ``None``.
        """
        return value.isoformat() if value else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def was_uploaded_by(self, user_id: Optional[str]) -> bool:
        """Return whether an account added this document.

        Args:
            user_id (Optional[str]): The account to test, or ``None``.

        Returns:
            bool: ``True`` when the account is the uploader.

        Notes:
            ``None`` answers ``False``. The caller's identifier is typed
            optional, and a check that treated a missing one as a match would
            hand every document's delete control to any account that arrived
            without an identifier.
        """
        return user_id is not None and user_id == self.uploaded_by
