from __future__ import annotations

# Third-party imports
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import EInvoicingProvider
from storage.orm.integrations.einvoicing_integration_row import (
    EInvoicingIntegrationRow,
)
from storage.repositories.integrations.einvoicing_integration import (
    EInvoicingIntegrationRepository,
)

COMPANY = "company-1"
OTHER_COMPANY = "company-2"
ACTOR = "nathalie@simple-erp.fr"


@pytest.fixture
def repository(session: AsyncSession) -> EInvoicingIntegrationRepository:
    """Build the repository on the in-memory schema.

    Args:
        session (AsyncSession): The test session.

    Returns:
        EInvoicingIntegrationRepository: The repository.
    """
    return EInvoicingIntegrationRepository(session=session)


class TestConnectingAPlatform:
    """Tests for storing credentials and switching a platform on."""

    async def test_enabling_stores_the_sealed_credentials(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Args:
        repository (EInvoicingIntegrationRepository): The repository.
        """
        integration = await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…cdef", ACTOR
        )

        assert integration.enabled is True
        assert integration.credential_ciphertext == "sealed-1"
        assert integration.credential_hint == "…cdef"
        assert integration.updated_by == ACTOR

    async def test_enabling_twice_replaces_the_credentials(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Re-entering a rotated key must not create a second row.

        Args:
            repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        again = await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-2", "…2222", ACTOR
        )

        assert again.credential_ciphertext == "sealed-2"
        assert len(await repository.list_for_company(COMPANY)) == 1

    async def test_a_new_key_clears_the_previous_check_result(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """**A freshly connected platform must not look broken.**

        Args:
            repository (EInvoicingIntegrationRepository): The repository.

        Notes:
            Yesterday's 401 says nothing about the key entered a moment ago,
            and leaving it attached would make ``is_usable`` refuse a platform
            that has just been fixed.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        await repository.record_check(COMPANY, EInvoicingProvider.B2BROUTER, "401")

        again = await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-2", "…2222", ACTOR
        )

        assert again.last_check_error is None
        assert again.last_checked_at is None
        assert again.is_usable() is True


class TestOnlyOnePlatformIsActive:
    """Tests for the invariant the whole feature rests on.

    Notes:
        An invoice has exactly one destination. Two enabled platforms would
        leave "which one did this bill go to?" unanswerable after the fact,
        which is precisely the question an audit asks.
    """

    async def test_enabling_a_second_platform_disables_the_first(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Switching platform is one action, not two.

        Args:
            repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        await repository.enable(
            COMPANY, EInvoicingProvider.STORECOVE, "sealed-2", "…2222", ACTOR
        )

        enabled = await repository.get_enabled(COMPANY)

        assert enabled is not None
        assert enabled.provider is EInvoicingProvider.STORECOVE

    async def test_the_displaced_platform_keeps_its_credentials(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Switching back must not mean finding the old API key again.

        Args:
            repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        await repository.enable(
            COMPANY, EInvoicingProvider.STORECOVE, "sealed-2", "…2222", ACTOR
        )

        displaced = await repository.get_for_provider(
            COMPANY, EInvoicingProvider.B2BROUTER
        )

        assert displaced is not None
        assert displaced.enabled is False
        assert displaced.credential_ciphertext == "sealed-1"

    async def test_the_database_refuses_two_enabled_rows(
        self, session: AsyncSession, repository: EInvoicingIntegrationRepository
    ) -> None:
        """**The constraint, tested against the database rather than the code.**

        Args:
            session (AsyncSession): The test session.
            repository (EInvoicingIntegrationRepository): The repository.

        Notes:
            The repository disables the others before enabling one, so this can
            never happen through it. That is exactly why the index is worth
            asserting separately: it is what protects the invariant from the
            *second* write path — a fixture, a support script, a future
            endpoint — that does not know the rule.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )

        session.add(
            EInvoicingIntegrationRow(
                id="smuggled",
                company_id=COMPANY,
                provider=EInvoicingProvider.IOPOLE.value,
                enabled=True,
                credential_ciphertext="sealed-3",
                credential_hint="…3333",
                created_at=(await repository.get_enabled(COMPANY)).created_at,
                updated_at=(await repository.get_enabled(COMPANY)).updated_at,
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_many_disabled_platforms_are_allowed(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """**Why the index is partial rather than a unique constraint.**

        Args:
            repository (EInvoicingIntegrationRepository): The repository.

        Notes:
            An agency that has tried three platforms and settled on one holds
            three rows. A plain unique constraint over (company_id, enabled)
            would forbid the two it is no longer using.
        """
        for provider in (
            EInvoicingProvider.B2BROUTER,
            EInvoicingProvider.STORECOVE,
            EInvoicingProvider.INVOPOP,
        ):
            await repository.enable(COMPANY, provider, "sealed", "…aaaa", ACTOR)

        stored = await repository.list_for_company(COMPANY)

        assert len(stored) == 3
        assert len([entry for entry in stored if entry.enabled]) == 1

    async def test_one_agency_s_platform_is_not_another_s(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """The invariant is per agency, not global.

        Args:
            repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        await repository.enable(
            OTHER_COMPANY, EInvoicingProvider.STORECOVE, "sealed-2", "…2222", ACTOR
        )

        mine = await repository.get_enabled(COMPANY)
        theirs = await repository.get_enabled(OTHER_COMPANY)

        assert mine is not None and mine.provider is EInvoicingProvider.B2BROUTER
        assert theirs is not None and theirs.provider is EInvoicingProvider.STORECOVE


class TestDisconnectingAPlatform:
    """Tests for switching a platform off."""

    async def test_disabling_stops_transmission(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Args:
        repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )

        await repository.disable(COMPANY, EInvoicingProvider.B2BROUTER, ACTOR)

        assert await repository.get_enabled(COMPANY) is None

    async def test_disabling_keeps_the_credentials(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Pausing a platform for a month is not forgetting its key.

        Args:
            repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        await repository.disable(COMPANY, EInvoicingProvider.B2BROUTER, ACTOR)

        kept = await repository.get_for_provider(COMPANY, EInvoicingProvider.B2BROUTER)

        assert kept is not None
        assert kept.credential_ciphertext == "sealed-1"

    async def test_disabling_what_was_never_configured_returns_nothing(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """A caller that skipped a step, not a crash.

        Args:
            repository (EInvoicingIntegrationRepository): The repository.
        """
        assert (
            await repository.disable(COMPANY, EInvoicingProvider.IOPOLE, ACTOR) is None
        )


class TestReadingWhatIsConfigured:
    """Tests for the queries the gallery and the transmission service make."""

    async def test_an_agency_with_nothing_has_no_enabled_platform(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """**The legally significant answer, and not an error.**

        Args:
            repository (EInvoicingIntegrationRepository): The repository.

        Notes:
            This is the state the warning banner exists to report. Returning
            ``None`` rather than raising is what makes every caller handle it.
        """
        assert await repository.get_enabled(COMPANY) is None
        assert await repository.list_for_company(COMPANY) == []

    async def test_disabled_platforms_are_still_listed(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """The gallery shows a card for a platform switched off.

        Args:
            repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        await repository.disable(COMPANY, EInvoicingProvider.B2BROUTER, ACTOR)

        assert len(await repository.list_for_company(COMPANY)) == 1


class TestRecordingACheck:
    """Tests for what is remembered about proving the credentials."""

    async def test_a_success_clears_the_previous_failure(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Args:
        repository (EInvoicingIntegrationRepository): The repository.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )
        await repository.record_check(COMPANY, EInvoicingProvider.B2BROUTER, "401")

        healed = await repository.record_check(
            COMPANY, EInvoicingProvider.B2BROUTER, None
        )

        assert healed is not None
        assert healed.last_check_error is None
        assert healed.is_usable() is True

    async def test_a_failure_does_not_disable_the_platform(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """**The distinction between "switched off" and "not working".**

        Args:
            repository (EInvoicingIntegrationRepository): The repository.

        Notes:
            A key rotated at the far end must not silently un-choose a platform
            a manager deliberately selected — otherwise the fix would be to
            re-enable something nobody disabled.
        """
        await repository.enable(
            COMPANY, EInvoicingProvider.B2BROUTER, "sealed-1", "…1111", ACTOR
        )

        failed = await repository.record_check(
            COMPANY, EInvoicingProvider.B2BROUTER, "401 Unauthorized"
        )

        assert failed is not None
        assert failed.enabled is True
        assert failed.is_usable() is False

    async def test_recording_against_nothing_returns_nothing(
        self, repository: EInvoicingIntegrationRepository
    ) -> None:
        """Args:
        repository (EInvoicingIntegrationRepository): The repository.
        """
        assert (
            await repository.record_check(COMPANY, EInvoicingProvider.IOPOLE, None)
            is None
        )
