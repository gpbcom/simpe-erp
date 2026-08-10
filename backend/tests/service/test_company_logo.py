from __future__ import annotations

# Standard library imports
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.companies.company import Company
from service.companies.companies import CompanyService
from service.companies.exceptions import (
    MTCompanyLogoStorageUnavailable,
    MTCompanyNotFound,
)
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.people.hca import HcaRepository
from storage.repositories.auth.user import UserRepository
from storage.s3.exceptions import MTS3DeleteFailed
from storage.s3.s3_storage import S3Storage

COMPANY_ID = "company-1"
OLD_LOGO = "https://minio.internal/simple-erp/company-logos/company-1/old.png"
NEW_LOGO = "https://minio.internal/simple-erp/company-logos/company-1/new.png"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _agency(logo_url: Optional[str] = None) -> Company:
    """Build an agency, optionally already carrying a logo.

    Args:
        logo_url (Optional[str]): The logo it starts with.

    Returns:
        Company: The agency.
    """
    return Company(id=COMPANY_ID, name="Aide et Soins", logo_url=logo_url)


@pytest.fixture
def companies() -> MagicMock:
    """Return a company repository double holding one agency.

    Returns:
        MagicMock: The double.
    """
    repository = MagicMock(spec=CompanyRepository)
    repository.get = AsyncMock(return_value=_agency(OLD_LOGO))
    repository.set_logo_url = AsyncMock(
        side_effect=lambda company_id, logo_url: _agency(logo_url)
    )
    repository.delete = AsyncMock(return_value=True)
    return repository


@pytest.fixture
def logos() -> MagicMock:
    """Return an object-store double that accepts every write.

    Returns:
        MagicMock: The double.
    """
    store = MagicMock(spec=S3Storage)
    store.upload_logo = AsyncMock(return_value=NEW_LOGO)
    store.delete_logo = AsyncMock(return_value=True)
    return store


@pytest.fixture
def service(companies: MagicMock, logos: MagicMock) -> CompanyService:
    """Return the service under test.

    Args:
        companies (MagicMock): The company store double.
        logos (MagicMock): The object store double.

    Returns:
        CompanyService: The service.
    """
    users = MagicMock(spec=UserRepository)
    users.count_for_company = AsyncMock(return_value=0)
    hcas = MagicMock(spec=HcaRepository)
    hcas.count_for_company = AsyncMock(return_value=0)
    return CompanyService(companies=companies, users=users, hcas=hcas, logos=logos)


class TestSettingALogo:
    """Tests for attaching an uploaded image to an agency."""

    async def test_the_object_is_written_before_the_record(
        self, service: CompanyService, companies: MagicMock, logos: MagicMock
    ) -> None:
        """**Ordering, and it is the whole point of the method.**

        Args:
            service (CompanyService): The service under test.
            companies (MagicMock): The company store double.
            logos (MagicMock): The object store double.

        Notes:
            The reverse order would leave a record pointing at an object that
            does not exist yet, so a failure between the two steps would show a
            broken image rather than the previous one.
        """
        order: List[str] = []
        logos.upload_logo = AsyncMock(
            side_effect=lambda *_: order.append("upload") or NEW_LOGO
        )
        companies.set_logo_url = AsyncMock(
            side_effect=lambda *_: order.append("record") or _agency(NEW_LOGO)
        )

        await service.set_logo(COMPANY_ID, PNG)

        assert order == ["upload", "record"]

    async def test_the_record_points_at_the_new_object(
        self, service: CompanyService
    ) -> None:
        """What comes back is what the screen will render."""
        updated = await service.set_logo(COMPANY_ID, PNG)

        assert updated.logo_url == NEW_LOGO

    async def test_the_superseded_object_is_removed(
        self, service: CompanyService, logos: MagicMock
    ) -> None:
        """Replacing a logo must not accumulate images nothing names."""
        await service.set_logo(COMPANY_ID, PNG)

        logos.delete_logo.assert_awaited_once_with(OLD_LOGO)

    async def test_an_agency_that_had_no_logo_deletes_nothing(
        self, service: CompanyService, companies: MagicMock, logos: MagicMock
    ) -> None:
        """There is no previous object to remove on a first upload."""
        companies.get = AsyncMock(return_value=_agency(None))

        await service.set_logo(COMPANY_ID, PNG)

        logos.delete_logo.assert_not_awaited()

    async def test_a_failed_cleanup_does_not_fail_the_upload(
        self, service: CompanyService, logos: MagicMock
    ) -> None:
        """**The record is already correct by the time cleanup runs.**

        Args:
            service (CompanyService): The service under test.
            logos (MagicMock): The object store double.

        Notes:
            Raising here would report a failure for an operation that
            succeeded. The cost of swallowing it is an orphaned object, which
            is a housekeeping problem rather than a correctness one.
        """
        logos.delete_logo = AsyncMock(side_effect=MTS3DeleteFailed("bucket said no"))

        updated = await service.set_logo(COMPANY_ID, PNG)

        assert updated.logo_url == NEW_LOGO

    async def test_an_agency_that_vanished_mid_upload_is_reported(
        self, service: CompanyService, companies: MagicMock
    ) -> None:
        """A written object with nothing to attach it to is an error."""
        companies.set_logo_url = AsyncMock(return_value=None)

        with pytest.raises(MTCompanyNotFound):
            await service.set_logo(COMPANY_ID, PNG)

    async def test_an_absent_agency_is_refused_before_anything_is_written(
        self, service: CompanyService, companies: MagicMock, logos: MagicMock
    ) -> None:
        """No object is uploaded for an agency that does not exist."""
        companies.get = AsyncMock(return_value=None)

        with pytest.raises(MTCompanyNotFound):
            await service.set_logo(COMPANY_ID, PNG)

        logos.upload_logo.assert_not_awaited()


class TestClearingALogo:
    """Tests for removing an agency's logo."""

    async def test_the_record_is_cleared_before_the_object(
        self, service: CompanyService, companies: MagicMock, logos: MagicMock
    ) -> None:
        """The opposite order to the upload, for the same reason.

        Args:
            service (CompanyService): The service under test.
            companies (MagicMock): The company store double.
            logos (MagicMock): The object store double.

        Notes:
            What matters in both cases is that the record never points at a
            missing object: on upload the object must exist first, on removal
            the link must go first.
        """
        order: List[str] = []
        companies.set_logo_url = AsyncMock(
            side_effect=lambda *_: order.append("record") or _agency(None)
        )
        logos.delete_logo = AsyncMock(
            side_effect=lambda *_: order.append("object") or True
        )

        await service.clear_logo(COMPANY_ID)

        assert order == ["record", "object"]

    async def test_the_agency_comes_back_without_a_logo(
        self, service: CompanyService
    ) -> None:
        """The caller's screen is redrawn from what is returned."""
        updated = await service.clear_logo(COMPANY_ID)

        assert updated.logo_url is None

    async def test_the_stored_object_is_removed(
        self, service: CompanyService, logos: MagicMock
    ) -> None:
        """Clearing the link must not leave the image in the bucket."""
        await service.clear_logo(COMPANY_ID)

        logos.delete_logo.assert_awaited_once_with(OLD_LOGO)


class TestDeletingAnAgencyRemovesItsLogo:
    """Tests that an agency's image does not outlive its row."""

    async def test_the_logo_goes_with_the_agency(
        self, service: CompanyService, logos: MagicMock
    ) -> None:
        """Nothing references the object once the row is gone."""
        await service.delete(COMPANY_ID)

        logos.delete_logo.assert_awaited_once_with(OLD_LOGO)


class TestADeploymentWithoutAnObjectStore:
    """Tests for the refusal when no bucket is configured."""

    @pytest.fixture
    def storeless(self, companies: MagicMock) -> CompanyService:
        """Return a service built without an object store.

        Args:
            companies (MagicMock): The company store double.

        Returns:
            CompanyService: The service.
        """
        return CompanyService(
            companies=companies,
            users=MagicMock(spec=UserRepository),
            hcas=MagicMock(spec=HcaRepository),
        )

    async def test_uploading_is_refused(self, storeless: CompanyService) -> None:
        """**Refused, not silently skipped.**

        Args:
            storeless (CompanyService): The service with no object store.

        Notes:
            Somebody who uploaded an image and got a 2xx back would reasonably
            believe it was kept. A record that quietly declines to hold one is
            worse than a route that says the deployment cannot.
        """
        with pytest.raises(MTCompanyLogoStorageUnavailable):
            await storeless.set_logo(COMPANY_ID, PNG)

    async def test_clearing_is_refused(self, storeless: CompanyService) -> None:
        """Reporting the same way in both directions.

        Args:
            storeless (CompanyService): The service with no object store.
        """
        with pytest.raises(MTCompanyLogoStorageUnavailable):
            await storeless.clear_logo(COMPANY_ID)

    async def test_the_rest_of_the_service_still_works(
        self, storeless: CompanyService
    ) -> None:
        """The store is optional because only two methods need it.

        Args:
            storeless (CompanyService): The service with no object store.

        Notes:
            A test exercising agency deletion should not have to stand up an
            object store to do so, which is why the collaborator defaults to
            ``None`` rather than being required.
        """
        assert (await storeless.get(COMPANY_ID)).name == "Aide et Soins"
