from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# First-party imports
from models.auth.user import User
from models.enums import MemberKind
from models.organisation.team.team import Team
from models.organisation.team.team_document import TeamDocument
from service.organisation.exceptions import (
    MTTeamDocumentForbidden,
    MTTeamDocumentNotFound,
    MTTeamDocumentStorageUnavailable,
    MTTeamNotFound,
)
from service.organisation.teams import TeamService
from storage.repositories.organisation.team_document import TeamDocumentRepository
from storage.s3.s3_storage import S3Storage


class TeamDocumentService:
    """The files a team shares, and who may add or remove one.

    Attributes:
        documents (TeamDocumentRepository): Indexes the stored objects.
        teams (TeamService): Resolves the team and the caller's membership.
        storage (Optional[S3Storage]): Where the bytes live.
        logger (Logger): Logger for the operations here.

    Notes:
        - **Everybody on the team may add a document, and everybody on it may
          read one.** That is the requirement, and it is unusual on this
          surface: almost every other write here is a manager's. A shared space
          only one person can fill is a shared space nobody uses.
        - **A non-member is answered 404, not 403.** A team's space is private,
          and a 403 would confirm that a document exists to somebody with no
          business knowing it does. Deleting a *colleague's* file is the one
          refusal answered 403, because everybody on the team can plainly see
          the file — telling them it does not exist would read as a bug.
        - The **row is written after the object and removed before it**. An
          orphaned object costs storage; an orphaned row costs a download that
          answers 503 to somebody who can see the file on their screen.
    """

    def __init__(
        self,
        documents: TeamDocumentRepository,
        teams: TeamService,
        storage: Optional[S3Storage] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            documents (TeamDocumentRepository): Indexes the stored objects.
            teams (TeamService): Resolves the team and the caller's membership.
            storage (Optional[S3Storage]): Where the bytes live. ``None`` in a
                deployment with no object store configured.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.documents = documents
        self.teams = teams
        self.storage = storage
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("TeamDocumentService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _store(self) -> S3Storage:
        """Return the object store, refusing when none is configured.

        Returns:
            S3Storage: The configured object store.

        Raises:
            MTTeamDocumentStorageUnavailable: If no object store is configured.

        Notes:
            Answered as a 503, because it describes the deployment rather than
            the request: the same call will work once an object store is
            configured, and nothing the caller can change about the payload will
            help.
        """
        if self.storage is None:
            self.logger.error(
                "A team document was requested with no object store configured."
            )
            raise MTTeamDocumentStorageUnavailable(
                "This deployment has no object store, so team documents cannot "
                "be shared."
            )
        return self.storage

    async def _readable_team(self, team_id: str, caller: User) -> Team:
        """Return a team whose shared space the caller may open.

        Args:
            team_id (str): The team whose space is being reached.
            caller (User): The authenticated caller.

        Returns:
            Team: The team.

        Raises:
            MTTeamNotFound: If no such team exists, or the caller is not on it
                and is not an administrator.

        Notes:
            An administrator reaches any team's space, and everybody else
            reaches only their own — a manager included, because a manager who
            runs no team has no more business in one than an assistant who is
            not on it. Both refusals are the **same 404**: a space somebody
            cannot open must not be distinguishable from one that does not
            exist.
        """
        team = await self.teams.teams.get(team_id)
        if team is None or team.company_id != caller.company_id:
            self.logger.warning(
                "Account %s cannot reach the space of team %s.", caller.id, team_id
            )
            raise MTTeamNotFound(f"No team {team_id!r} exists.")
        if caller.is_admin():
            self.logger.debug(
                "Administrator %s opens the space of team %s.", caller.id, team_id
            )
            return team
        if not await self._is_member(team_id, caller):
            self.logger.warning(
                "Account %s is not on team %s and may not open its space.",
                caller.id,
                team_id,
            )
            raise MTTeamNotFound(f"No team {team_id!r} exists.")
        return team

    async def _is_member(self, team_id: str, caller: User) -> bool:
        """Return whether an account is on a team.

        Args:
            team_id (str): The team to test.
            caller (User): The authenticated caller.

        Returns:
            bool: ``True`` when the caller's account or assistant record is on
            the team.

        Notes:
            **Both halves are tested, and both are needed.** A manager and an
            administrator are on a team as an *account*; an assistant may be on
            it as an account too, but the record is what the planner schedules
            and the one an assistant without a sign-in would be listed under.
            Testing only one would shut out whichever group holds the other.
        """
        by_account = await self.teams.teams.team_for_member(
            MemberKind.USER, str(caller.id)
        )
        if by_account is not None and by_account.id == team_id:
            return True
        if not caller.hca_id:
            return False
        by_record = await self.teams.teams.team_for_member(
            MemberKind.HCA, caller.hca_id
        )
        return by_record is not None and by_record.id == team_id

    ############################
    # Publicly Exposed Methods #
    ############################

    async def list(self, team_id: str, caller: User) -> List[TeamDocument]:
        """Return the files a team shares.

        Args:
            team_id (str): The team whose space is being read.
            caller (User): The authenticated caller.

        Returns:
            List[TeamDocument]: The records, newest first.

        Raises:
            MTTeamNotFound: If no such team exists, or the caller is not on it.
        """
        await self._readable_team(team_id, caller)
        return await self.documents.list_for_team(team_id)

    async def upload(
        self, team_id: str, caller: User, file_name: str, payload: bytes
    ) -> TeamDocument:
        """Add a file to a team's shared space.

        Args:
            team_id (str): The team whose space it joins.
            caller (User): The member adding it.
            file_name (str): What they called it.
            payload (bytes): The uploaded bytes.

        Returns:
            TeamDocument: The stored record.

        Raises:
            MTTeamNotFound: If no such team exists, or the caller is not on it.
            MTTeamDocumentStorageUnavailable: If no object store is configured.
            MTS3EmptyPayload: If the file carries no bytes.
            MTS3UnsupportedContentType: If the file is not a shareable type.
            MTS3PayloadTooLarge: If the file exceeds the configured size.

        Notes:
            - **The object is written first and the row second.** A row written
              first would describe an object that may never arrive, and the
              screen would offer a download that answers 503 for ever. The
              reverse failure — an object with no row — costs storage and
              nothing else.
            - The uploader's **name is copied** onto the record rather than
              joined at read time, so a file added by somebody who has since
              left still says who added it.
        """
        team = await self._readable_team(team_id, caller)
        key, content_type = await self._store().upload_team_document(team_id, payload)
        self.logger.info(
            "Account %s added %s to the space of team %s.",
            caller.id,
            file_name,
            team_id,
        )
        return await self.documents.create(
            TeamDocument(
                team_id=team_id,
                company_id=team.company_id,
                file_name=file_name,
                content_type=content_type,
                size_bytes=len(payload),
                document_key=key,
                uploaded_by=str(caller.id),
                uploaded_by_name=caller.full_name(),
            )
        )

    async def download(
        self, team_id: str, document_id: str, caller: User
    ) -> Tuple[bytes, str, str]:
        """Read one of a team's shared files back.

        Args:
            team_id (str): The team whose space it sits in.
            document_id (str): The record to read.
            caller (User): The authenticated caller.

        Returns:
            Tuple[bytes, str, str]: The bytes, the media type and the file name.

        Raises:
            MTTeamNotFound: If no such team exists, or the caller is not on it.
            MTTeamDocumentNotFound: If no such document exists, or the object
                behind it could not be read.
            MTTeamDocumentStorageUnavailable: If no object store is configured.

        Notes:
            The team is taken from the **route** and checked against the record,
            rather than resolved from the record alone. A document identifier is
            all a caller would otherwise need, and the membership check would
            then be running against whichever team the record happened to name.
        """
        await self._readable_team(team_id, caller)
        document = await self.documents.get(document_id)
        if document is None or document.team_id != team_id:
            self.logger.warning(
                "Team document %s is not in the space of team %s.",
                document_id,
                team_id,
            )
            raise MTTeamDocumentNotFound(f"No document {document_id!r} exists.")
        payload = await self._store().fetch_team_document(document.document_key)
        if payload is None:
            self.logger.error(
                "The object behind team document %s could not be read.", document_id
            )
            raise MTTeamDocumentNotFound(
                f"The file behind {document.file_name!r} could not be read."
            )
        self.logger.info(
            "Account %s downloaded %s from team %s.",
            caller.id,
            document.file_name,
            team_id,
        )
        return payload, document.content_type, document.file_name

    async def delete(self, team_id: str, document_id: str, caller: User) -> None:
        """Remove one of a team's shared files.

        Args:
            team_id (str): The team whose space it sits in.
            document_id (str): The record to remove.
            caller (User): The member removing it.

        Raises:
            MTTeamNotFound: If no such team exists, or the caller is not on it.
            MTTeamDocumentNotFound: If no such document exists.
            MTTeamDocumentForbidden: If the caller neither uploaded it, runs the
                team, nor is an administrator.
            MTTeamDocumentStorageUnavailable: If no object store is configured.

        Notes:
            - Three people may remove a file: whoever added it, the team's
              manager, and an administrator. Anybody may *add* one, so anybody
              being able to remove one would make the space a place where work
              disappears without a name attached.
            - **Answered 403 rather than 404**, unlike every other refusal here.
              Every member can see the file on their screen, so its existence is
              not a secret from them — telling them it does not exist would read
              as a bug rather than as a rule.
            - The **row goes first and the object second**. Losing the object
              after the row is gone costs storage; losing the row after the
              object would leave a download offering bytes that are no longer
              there.
        """
        team = await self._readable_team(team_id, caller)
        document = await self.documents.get(document_id)
        if document is None or document.team_id != team_id:
            self.logger.warning(
                "Team document %s is not in the space of team %s.",
                document_id,
                team_id,
            )
            raise MTTeamDocumentNotFound(f"No document {document_id!r} exists.")
        may_remove = (
            document.was_uploaded_by(caller.id)
            or team.is_managed_by(caller.id)
            or caller.is_admin()
        )
        if not may_remove:
            self.logger.warning(
                "Account %s may not remove %s, which %s added.",
                caller.id,
                document.file_name,
                document.uploaded_by_name,
            )
            raise MTTeamDocumentForbidden(
                f"{document.file_name!r} was added by {document.uploaded_by_name}. "
                f"Only they, the team's manager or an administrator may remove it."
            )
        await self.documents.delete(document_id)
        removed = await self._store().delete_team_document(document.document_key)
        if not removed:
            self.logger.error(
                "The record for team document %s is gone but its object at %s "
                "remains; it is now unreachable and costs storage.",
                document_id,
                document.document_key,
            )
        self.logger.info(
            "Account %s removed %s from team %s.",
            caller.id,
            document.file_name,
            team_id,
        )

    async def purge_team(self, team_id: str) -> int:
        """Remove every object a team's space holds.

        Args:
            team_id (str): The team being disbanded.

        Returns:
            int: How many objects were removed.

        Notes:
            Called **before** the team is deleted. Its rows cascade away with
            it, so asking afterwards would find nothing and leave every object
            behind in the bucket with nothing pointing at it — the same reason
            the replan period is measured before a person is removed.
        """
        if self.storage is None:
            self.logger.warning(
                "Team %s is being emptied with no object store configured; its "
                "records go, and there are no objects to remove.",
                team_id,
            )
            return 0
        keys = await self.documents.list_keys_for_team(team_id)
        removed = 0
        for key in keys:
            if await self.storage.delete_team_document(key):
                removed += 1
        if removed != len(keys):
            self.logger.error(
                "Emptied team %s: %d of %d object(s) removed; the rest remain "
                "in the bucket with nothing pointing at them.",
                team_id,
                removed,
                len(keys),
            )
        else:
            self.logger.info(
                "Emptied the space of team %s: %d object(s) removed.", team_id, removed
            )
        return removed
