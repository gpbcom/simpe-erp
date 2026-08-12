from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import List, Optional
from uuid import uuid4

# Third-party imports
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import EInvoicingProvider
from models.integrations.einvoicing_integration import EInvoicingIntegration
from storage.mappers.integrations.einvoicing_integration_mapper import (
    EInvoicingIntegrationMapper,
)
from storage.orm.integrations.einvoicing_integration_row import (
    EInvoicingIntegrationRow,
)
from storage.repositories.base import BaseRepository


class EInvoicingIntegrationRepository(BaseRepository[EInvoicingIntegrationRow]):
    """Reads and writes an agency's certified-platform integrations.

    Attributes:
        mapper (EInvoicingIntegrationMapper): Converts between row and model.

    Notes:
        - **The one-active invariant lives here, not in the service.** Enabling
          a platform disables every other one for the agency in the *same*
          transaction, so two managers enabling different platforms at the same
          moment cannot both succeed. A service doing this would read, decide
          and write across three round trips with nothing holding the gap.
        - The database carries a partial unique index saying the same thing.
          Belt and braces, and deliberately so: this method is the one that
          keeps the invariant *readable*, and the index is the one that keeps it
          *true* when somebody writes a second path to the table.
        - Nothing here decrypts. Credentials arrive sealed and leave sealed.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session,
            row_class=EInvoicingIntegrationRow,
        )
        self.mapper = EInvoicingIntegrationMapper()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def list_for_company(self, company_id: str) -> List[EInvoicingIntegration]:
        """Return every integration an agency has configured.

        Args:
            company_id (str): The agency.

        Returns:
            List[EInvoicingIntegration]: The integrations, enabled or not, in
            provider order.

        Notes:
            Disabled rows are returned too. The gallery shows a card for a
            platform whose key is still stored but switched off, and losing that
            would make "we tried Storecove last year" invisible.
        """
        self.logger.debug("Listing e-invoicing integrations for agency %s.", company_id)
        statement = (
            select(EInvoicingIntegrationRow)
            .where(EInvoicingIntegrationRow.company_id == company_id)
            .order_by(EInvoicingIntegrationRow.provider)
        )
        rows = (await self.session.execute(statement)).scalars().all()
        self.logger.debug(
            "Agency %s has %d configured integration(s).", company_id, len(rows)
        )
        return [self.mapper.to_model(row) for row in rows]

    async def get_enabled(self, company_id: str) -> Optional[EInvoicingIntegration]:
        """Return the agency's active integration, if it has one.

        Args:
            company_id (str): The agency.

        Returns:
            Optional[EInvoicingIntegration]: The enabled integration, or
            ``None`` when the agency has connected nothing.

        Notes:
            ``None`` is a legitimate and legally significant answer, not an
            error: it is what the warning banner exists to report. Every caller
            has to handle it, which is why this returns rather than raises.
        """
        self.logger.debug("Fetching the enabled integration for agency %s.", company_id)
        statement = select(EInvoicingIntegrationRow).where(
            EInvoicingIntegrationRow.company_id == company_id,
            EInvoicingIntegrationRow.enabled.is_(True),
        )
        row = (await self.session.execute(statement)).scalars().first()
        if row is None:
            self.logger.warning(
                "Agency %s has no enabled e-invoicing platform; invoices cannot "
                "be transmitted.",
                company_id,
            )
            return None
        return self.mapper.to_model(row)

    async def get_for_provider(
        self, company_id: str, provider: EInvoicingProvider
    ) -> Optional[EInvoicingIntegration]:
        """Return an agency's integration with one platform.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform.

        Returns:
            Optional[EInvoicingIntegration]: The integration, or ``None``.
        """
        self.logger.debug(
            "Fetching agency %s's %s integration.", company_id, provider.value
        )
        statement = select(EInvoicingIntegrationRow).where(
            EInvoicingIntegrationRow.company_id == company_id,
            EInvoicingIntegrationRow.provider == provider.value,
        )
        row = (await self.session.execute(statement)).scalars().first()
        return self.mapper.to_model(row) if row is not None else None

    async def enable(
        self,
        company_id: str,
        provider: EInvoicingProvider,
        ciphertext: str,
        hint: str,
        actor: str,
    ) -> EInvoicingIntegration:
        """Store credentials for a platform and make it the active one.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform to enable.
            ciphertext (str): The sealed credentials.
            hint (str): The masked tail of the key.
            actor (str): The account making the change.

        Returns:
            EInvoicingIntegration: The now-active integration.

        Notes:
            **Disables the others first, in the same transaction.** Doing it the
            other way round would trip the partial unique index for as long as
            two rows claimed to be enabled — briefly, but inside a transaction
            that would then have to be retried.

            The previous check result is cleared. A key just entered has not
            been proven yet, and leaving yesterday's failure attached would make
            a freshly connected platform look broken.
        """
        moment = datetime.now(UTC)
        self.logger.info(
            "%s is enabling %s for agency %s.", actor, provider.value, company_id
        )
        await self.session.execute(
            update(EInvoicingIntegrationRow)
            .where(
                EInvoicingIntegrationRow.company_id == company_id,
                EInvoicingIntegrationRow.provider != provider.value,
                EInvoicingIntegrationRow.enabled.is_(True),
            )
            .values(enabled=False, updated_at=moment, updated_by=actor)
        )
        statement = select(EInvoicingIntegrationRow).where(
            EInvoicingIntegrationRow.company_id == company_id,
            EInvoicingIntegrationRow.provider == provider.value,
        )
        row = (await self.session.execute(statement)).scalars().first()
        if row is None:
            self.logger.debug(
                "Agency %s had no %s row; creating one.", company_id, provider.value
            )
            row = EInvoicingIntegrationRow(
                id=str(uuid4()),
                company_id=company_id,
                provider=provider.value,
                created_at=moment,
            )
            self.session.add(row)
        row.enabled = True
        row.credential_ciphertext = ciphertext
        row.credential_hint = hint
        row.updated_by = actor
        row.updated_at = moment
        row.last_checked_at = None
        row.last_check_error = None
        await self.session.flush()
        self.logger.info(
            "Agency %s now transmits through %s.", company_id, provider.value
        )
        return self.mapper.to_model(row)

    async def disable(
        self, company_id: str, provider: EInvoicingProvider, actor: str
    ) -> Optional[EInvoicingIntegration]:
        """Stop transmitting through a platform, keeping its credentials.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform to switch off.
            actor (str): The account making the change.

        Returns:
            Optional[EInvoicingIntegration]: The disabled integration, or
            ``None`` when the agency never configured it.

        Notes:
            The credentials stay. Disabling is reversible by design — an agency
            pausing a platform for a month should not have to find its API key
            again — and the row is also the record of what was once connected.
        """
        statement = select(EInvoicingIntegrationRow).where(
            EInvoicingIntegrationRow.company_id == company_id,
            EInvoicingIntegrationRow.provider == provider.value,
        )
        row = (await self.session.execute(statement)).scalars().first()
        if row is None:
            self.logger.warning(
                "%s tried to disable %s for agency %s, which never configured it.",
                actor,
                provider.value,
                company_id,
            )
            return None
        self.logger.info(
            "%s is disabling %s for agency %s.", actor, provider.value, company_id
        )
        row.enabled = False
        row.updated_by = actor
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def record_check(
        self,
        company_id: str,
        provider: EInvoicingProvider,
        error: Optional[str],
    ) -> Optional[EInvoicingIntegration]:
        """Record what happened the last time the credentials were proven.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform checked.
            error (Optional[str]): The failure, or ``None`` when it worked.

        Returns:
            Optional[EInvoicingIntegration]: The updated integration, or
            ``None`` when the agency never configured it.

        Notes:
            **A failure never disables the platform.** The agency still has a
            contract, and a key rotated at the far end must not silently
            un-choose a platform a manager deliberately selected. What it does
            is make :meth:`~models.integrations.einvoicing_integration.EInvoicingIntegration.is_usable`
            answer ``False`` until a later check clears it.
        """
        statement = select(EInvoicingIntegrationRow).where(
            EInvoicingIntegrationRow.company_id == company_id,
            EInvoicingIntegrationRow.provider == provider.value,
        )
        row = (await self.session.execute(statement)).scalars().first()
        if row is None:
            self.logger.warning(
                "Cannot record a check for %s: agency %s never configured it.",
                provider.value,
                company_id,
            )
            return None
        row.last_checked_at = datetime.now(UTC)
        row.last_check_error = error
        await self.session.flush()
        if error:
            self.logger.error(
                "Agency %s's %s credentials failed their check: %s",
                company_id,
                provider.value,
                error,
            )
        else:
            self.logger.info(
                "Agency %s's %s credentials are working.", company_id, provider.value
            )
        return self.mapper.to_model(row)
