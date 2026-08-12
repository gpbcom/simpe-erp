from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_serializer, field_validator

# First-party imports
from models.organisation.team.exceptions import (
    MTTeamInvalidAgencyId,
    MTTeamInvalidCompanyId,
    MTTeamInvalidDate,
    MTTeamInvalidId,
    MTTeamInvalidManagerUserId,
    MTTeamInvalidName,
)


class Team(BaseModel):
    """A group of people at one site, under one manager, with one planning.

    Attributes:
        MAX_NAME_LENGTH (ClassVar[int]): Longest accepted team name.
        id (Optional[str]): Identifier, populated on read from the store.
        company_id (str): The company the team belongs to.
        agency_id (str): The site the team works from, and the point every
            distance to a customer is measured from.
        name (str): What the team is called.
        manager_user_id (str): The account that runs it. Exactly one.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - **The team is the unit the planner works in.** A run is requested for
          a team, its workforce is that team's field employees, its input is
          that team's accepted quotes, and its output replaces that team's
          visits and nobody else's. Teams share no assistant, so solving them
          apart returns the same plan as solving them together — an exact
          decomposition, exactly like the per-day split, and wrong *quietly*
          rather than loudly if anything ever couples two of them.
        - **The manager is a required field, not a flag on the member list.**
          "Exactly one" is a cardinality no boolean can hold: a flag can be set
          on nobody or on five, and pinning it to one needs a partial unique
          index *plus* something proving at least one exists, which no database
          states without a trigger. A required column is the constraint, and the
          restricting foreign key behind it means an account that still runs a
          team cannot be deleted out from under it.
        - The manager is also a member. That costs one row and buys the literal
          reading of "a team is a list of persons" — so a roster never has to
          explain why the person in charge is missing from it.
    """

    MAX_NAME_LENGTH: ClassVar[int] = 200

    id: Optional[str] = Field(
        default=None, description="Identifier, assigned by the store."
    )
    company_id: str = Field(description="The company the team belongs to.")
    agency_id: str = Field(description="The site the team works from.")
    name: str = Field(description="What the team is called.")
    manager_user_id: str = Field(description="The account that runs the team.")
    created_at: Optional[datetime] = Field(
        default=None, description="Creation timestamp."
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last-update timestamp."
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
            MTTeamInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTTeamInvalidId(f"Invalid id: {value!r}. Must be a non-empty string.")
        return value.strip()

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that the owning company is named.

        Args:
            value (Optional[str]): Raw ``company_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTTeamInvalidCompanyId: If ``value`` is not a non-empty string.

        Notes:
            Carried on the team as well as on its site, and that duplication is
            deliberate: every planning query filters on the company first, and
            reaching it through a join to ``agencies`` would put a second table
            in the most heavily read statement in the application.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamInvalidCompanyId(
                f"Invalid company_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("agency_id", mode="before")
    def validate_agency_id(cls, value: Optional[str]) -> str:
        """Validates that the site the team works from is named.

        Args:
            value (Optional[str]): Raw ``agency_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTTeamInvalidAgencyId: If ``value`` is not a non-empty string.

        Notes:
            Required, because the site is where the team *is*, and a team with
            no location can never be the closest one to a customer. Left
            optional it would be a team that quietly receives no work, which
            reads on screen exactly like a team nobody has given any.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamInvalidAgencyId(
                f"Invalid agency_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a usable team name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTTeamInvalidName: If ``value`` is not a non-empty string within
                :attr:`MAX_NAME_LENGTH`.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > cls.MAX_NAME_LENGTH:
            raise MTTeamInvalidName(
                f"Invalid name: {len(trimmed)} characters. Must be at most "
                f"{cls.MAX_NAME_LENGTH}."
            )
        return trimmed

    @field_validator("manager_user_id", mode="before")
    def validate_manager_user_id(cls, value: Optional[str]) -> str:
        """Validates that the team names exactly one manager.

        Args:
            value (Optional[str]): Raw ``manager_user_id`` value.

        Returns:
            str: The trimmed account identifier.

        Raises:
            MTTeamInvalidManagerUserId: If ``value`` is not a non-empty string.

        Notes:
            Whether that account *may* run a team — that it holds a manager's or
            an administrator's role, and belongs to the same site — is a
            question about other rows, and is checked in
            :class:`~service.organisation.teams.TeamService`. What is checked
            here is only that a team never exists without naming one.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamInvalidManagerUserId(
                f"Invalid manager_user_id: {value!r}. "  # noqa: E501
                "Must be a non-empty string."
            )
        return value.strip()

    @field_validator("created_at", "updated_at", mode="before")
    def validate_timestamps(
        cls, value: Union[datetime, str, None]
    ) -> Optional[datetime]:
        """Validates that a timestamp is a datetime.

        Args:
            value (Union[datetime, str, None]): Raw timestamp value.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTTeamInvalidDate: If ``value`` is neither ``None`` nor a datetime
                or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTTeamInvalidDate(
                    f"Invalid timestamp: {value!r}. "  # noqa: E501
                    "Must be an ISO-8601 datetime."
                ) from None
        raise MTTeamInvalidDate(
            f"Invalid timestamp: {value!r}. "  # noqa: E501
            "Must be a datetime."
        )

    @field_serializer("created_at", "updated_at")
    def serialize_timestamps(self, value: Optional[datetime]) -> Optional[str]:
        """Serialise a timestamp as an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialise.

        Returns:
            Optional[str]: The ISO-8601 form, or ``None``.
        """
        return value.isoformat() if value else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_managed_by(self, user_id: Optional[str]) -> bool:
        """Return whether an account runs this team.

        Args:
            user_id (Optional[str]): The account to test, or ``None``.

        Returns:
            bool: ``True`` when the account is this team's manager.

        Notes:
            ``None`` answers ``False`` rather than raising. The caller is an
            account read from a credential and its identifier is typed
            optional, so a guard written the obvious way would either need a
            narrowing every caller repeats or would hand a manager every team
            the moment one account arrived without one.
        """
        return user_id is not None and user_id == self.manager_user_id
