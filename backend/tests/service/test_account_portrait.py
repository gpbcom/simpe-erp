from __future__ import annotations

# Standard library imports
from typing import Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.auth_config import AuthConfig
from models.enums import UserRole
from service.auth.auth import AuthService
from service.auth.exceptions import MTAuthUnknownAccount
from storage.s3.exceptions import MTS3DeleteFailed

STORED_URL = "https://cdn.example.com/hca-photos/user-1/new.jpg"
PREVIOUS_URL = "https://cdn.example.com/hca-photos/user-1/old.jpg"


def _account(
    role: UserRole = UserRole.MANAGER,
    hca_id: Optional[str] = None,
    photo_url: Optional[str] = None,
    user_id: Optional[str] = "user-1",
) -> User:
    """Build a signed-in account.

    Args:
        role (UserRole): The role to grant.
        hca_id (Optional[str]): The assistant record it is bound to.
        photo_url (Optional[str]): The portrait already stored, if any.
        user_id (Optional[str]): The account identifier.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=user_id,
        email="claire.bernard@example.com",
        full_name="Claire Bernard",
        role=role,
        hca_id=hca_id,
        photo_url=photo_url,
    )


@pytest.fixture
def users() -> AsyncMock:
    """Return a stand-in account repository.

    Returns:
        AsyncMock: The repository double, echoing the portrait it is given.
    """
    repository = AsyncMock()
    repository.set_photo_url.side_effect = lambda user_id, url: _account(
        photo_url=url, user_id=user_id
    )
    return repository


@pytest.fixture
def hcas() -> AsyncMock:
    """Return a stand-in assistant repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.set_photo_url.return_value = object()
    return repository


@pytest.fixture
def photos() -> AsyncMock:
    """Return a stand-in object store.

    Returns:
        AsyncMock: The store double, handing back a URL under the photo prefix.
    """
    store = AsyncMock()
    store.upload_photo.return_value = STORED_URL
    return store


@pytest.fixture
def service(users: AsyncMock, hcas: AsyncMock, photos: AsyncMock) -> AuthService:
    """Return an authentication service over stand-in stores.

    Args:
        users (AsyncMock): The account repository double.
        hcas (AsyncMock): The assistant repository double.
        photos (AsyncMock): The object store double.

    Returns:
        AuthService: The service under test.
    """
    return AuthService(users=users, hcas=hcas, config=AuthConfig(), photos=photos)


class TestSetPhoto:
    """Tests for storing the caller's own portrait."""

    async def test_the_object_is_written_before_the_account(
        self, service: AuthService, users: AsyncMock, photos: AsyncMock
    ) -> None:
        """A row must never point at an object that does not exist yet.

        Notes:
            The reverse order would show a broken image after a failure between
            the two steps, rather than the previous photograph.
        """
        updated = await service.set_photo(_account(), b"\xff\xd8\xffbytes")

        photos.upload_photo.assert_awaited_once_with("user-1", b"\xff\xd8\xffbytes")
        users.set_photo_url.assert_awaited_once_with("user-1", STORED_URL)
        assert str(updated.photo_url) == STORED_URL

    async def test_a_managers_portrait_is_not_mirrored_anywhere(
        self, service: AuthService, hcas: AsyncMock
    ) -> None:
        """An account bound to no assistant record has nothing to mirror to."""
        await service.set_photo(_account(), b"bytes")

        hcas.set_photo_url.assert_not_awaited()

    async def test_an_assistants_portrait_follows_onto_their_record(
        self, service: AuthService, users: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The map pin is the same photograph of the same person.

        Notes:
            Writing only the account would leave somebody who has just uploaded
            a face still showing as initials on the manager's map, which reads
            as the upload not having worked.

            The binding is read from the account the store handed *back*, not
            from the one the credential carried, so the repository double has
            to echo it.
        """
        users.set_photo_url.side_effect = lambda user_id, url: _account(
            role=UserRole.HCA, hca_id="hca-1", photo_url=url, user_id=user_id
        )

        await service.set_photo(_account(role=UserRole.HCA, hca_id="hca-1"), b"bytes")

        hcas.set_photo_url.assert_awaited_once_with("hca-1", STORED_URL)

    async def test_the_superseded_object_is_removed(
        self, service: AuthService, photos: AsyncMock
    ) -> None:
        """Replacing a portrait leaves no orphan behind."""
        await service.set_photo(_account(photo_url=PREVIOUS_URL), b"bytes")

        photos.delete_photo.assert_awaited_once_with(PREVIOUS_URL)

    async def test_a_failed_cleanup_does_not_fail_the_upload(
        self, service: AuthService, photos: AsyncMock
    ) -> None:
        """The account is already correct by the time the old object is dropped.

        Notes:
            Raising here would report a failure for an operation that
            succeeded. The cost is an orphaned object, which is housekeeping
            rather than correctness.
        """
        photos.delete_photo.side_effect = MTS3DeleteFailed("bucket is grumpy")

        updated = await service.set_photo(_account(photo_url=PREVIOUS_URL), b"bytes")

        assert str(updated.photo_url) == STORED_URL

    async def test_an_account_that_vanished_mid_upload_is_reported(
        self, service: AuthService, users: AsyncMock
    ) -> None:
        """A stored object with no account to attach it to is an error."""
        users.set_photo_url.side_effect = None
        users.set_photo_url.return_value = None

        with pytest.raises(MTAuthUnknownAccount):
            await service.set_photo(_account(), b"bytes")

    async def test_an_unstored_account_cannot_own_a_portrait(
        self, service: AuthService, photos: AsyncMock
    ) -> None:
        """Nothing is uploaded for an account with no identifier.

        Notes:
            A ``None`` reaching the object key would write every such portrait
            under the same prefix.
        """
        with pytest.raises(MTAuthUnknownAccount):
            await service.set_photo(_account(user_id=None), b"bytes")

        photos.upload_photo.assert_not_awaited()


class TestClearPhoto:
    """Tests for removing the caller's own portrait."""

    async def test_the_link_goes_before_the_object(
        self, service: AuthService, users: AsyncMock, photos: AsyncMock
    ) -> None:
        """On removal the row must stop pointing before the object goes."""
        cleared = await service.clear_photo(_account(photo_url=PREVIOUS_URL))

        users.set_photo_url.assert_awaited_once_with("user-1", None)
        photos.delete_photo.assert_awaited_once_with(PREVIOUS_URL)
        assert cleared.photo_url is None

    async def test_the_assistant_record_is_cleared_too(
        self, service: AuthService, users: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A removed portrait must not survive as a map pin."""
        users.set_photo_url.side_effect = lambda user_id, url: _account(
            role=UserRole.HCA, hca_id="hca-1", photo_url=url, user_id=user_id
        )

        await service.clear_photo(
            _account(role=UserRole.HCA, hca_id="hca-1", photo_url=PREVIOUS_URL)
        )

        hcas.set_photo_url.assert_awaited_once_with("hca-1", None)

    async def test_clearing_an_account_with_no_portrait_deletes_nothing(
        self, service: AuthService, photos: AsyncMock
    ) -> None:
        """There is no object to remove, so the store is left alone."""
        await service.clear_photo(_account())

        photos.delete_photo.assert_not_awaited()
