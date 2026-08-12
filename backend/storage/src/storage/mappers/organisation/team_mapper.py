from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import List, Optional, Sequence
from uuid import uuid4

# First-party imports
from models.organisation.team.team import Team
from models.organisation.team.team_member import TeamMember
from storage.mappers.base_mapper import BaseMapper
from storage.orm.organisation.team_member_row import TeamMemberRow
from storage.orm.organisation.team_row import TeamRow


class TeamMapper(BaseMapper[Team, TeamRow]):
    """Converts between :class:`Team` and :class:`TeamRow`.

    Notes:
        The membership rows are converted here rather than by a mapper of their
        own, for the reason
        :class:`~storage.mappers.organisation.agency_mapper.AgencyMapper` gives:
        a membership carries no identifier, so it cannot satisfy the contract
        :class:`BaseMapper` rests on.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=Team, row_class=TeamRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: TeamRow) -> Team:
        """Build a team from a row's columns.

        Args:
            row (TeamRow): The row to read.

        Returns:
            Team: The domain model.

        Raises:
            MTInvalidTeamException: If a stored value no longer satisfies the
                model's validators.
        """
        self.logger.debug("Building team %s from its row.", row.id)
        return Team(
            id=row.id,
            company_id=row.company_id,
            agency_id=row.agency_id,
            name=row.name,
            manager_user_id=row.manager_user_id,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: TeamRow, model: Team) -> None:
        """Write a team's fields onto a row's columns.

        Args:
            row (TeamRow): The row to write to.
            model (Team): The model carrying the values.
        """
        self.logger.debug("Applying team %s to its row.", model.name)
        row.company_id = model.company_id
        row.agency_id = model.agency_id
        row.name = model.name
        row.manager_user_id = model.manager_user_id

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_member(self, row: TeamMemberRow) -> TeamMember:
        """Convert a membership row into its model.

        Args:
            row (TeamMemberRow): The row to read.

        Returns:
            TeamMember: The membership.

        Raises:
            MTInvalidTeamMemberException: If the stored kind is not a known one.
        """
        self.logger.debug("Building team membership %s from its row.", row.id)
        return TeamMember(member_kind=row.member_kind, member_id=row.member_id)

    def to_members(self, rows: Sequence[TeamMemberRow]) -> List[TeamMember]:
        """Convert several membership rows into their models.

        Args:
            rows (Sequence[TeamMemberRow]): The rows to read.

        Returns:
            List[TeamMember]: The memberships, in the order given.
        """
        self.logger.debug("Building %d team membership(s) from rows.", len(rows))  # noqa: E501
        return [self.to_member(row) for row in rows]

    def to_member_row(self, team_id: str, member: TeamMember) -> TeamMemberRow:
        """Build a fresh membership row.

        Args:
            team_id (str): The team the person joins.
            member (TeamMember): Which person, and which kind of record.

        Returns:
            TeamMemberRow: A row ready to be added to a session.

        Notes:
            The team is a **parameter**, not something read off the membership,
            for the reason the model carries no ``team_id``: the owning team can
            only come from the route the caller reached.
        """
        self.logger.debug(
            "Building a team membership row for %s %s on team %s.",
            member.member_kind.value,
            member.member_id,
            team_id,
        )
        return TeamMemberRow(
            id=str(uuid4()),
            team_id=team_id,
            member_kind=member.member_kind.value,
            member_id=member.member_id,
            created_at=self._utc_now(),
        )
