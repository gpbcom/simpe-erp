from __future__ import annotations

# Standard library imports
from typing import Any, Dict

# Third-party imports
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import RegistrationStatus
from models.people.customer import Customer
from storage.repositories.customer import CustomerRepository


class TestCustomerRepository:
    """Tests for the CustomerRepository."""

    # ------------------------------------------------------------------ #
    #  Create and read
    # ------------------------------------------------------------------ #

    async def test_create_assigns_an_identifier(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A stored customer comes back with a generated identifier."""
        stored = await CustomerRepository(session).create(customer)
        assert stored.id is not None
        assert len(stored.id) == 36

    async def test_create_stamps_timestamps(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Creation and update timestamps are set by the store, not the model."""
        assert customer.created_at is None
        stored = await CustomerRepository(session).create(customer)
        assert stored.created_at is not None
        assert stored.updated_at is not None

    async def test_round_trip_preserves_every_field(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A customer read back matches what was written.

        Notes:
            This is the contract of the mapper: the flattened address columns
            must rebuild into an equivalent PostalAddress.
        """
        repository = CustomerRepository(session)
        stored = await repository.create(customer)
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.first_name == "Marie"
        assert loaded.last_name == "Durand"
        assert loaded.email == "marie.durand@example.com"
        assert loaded.address.street == "12 rue de Rivoli"
        assert loaded.address.postal_code == "75004"
        assert loaded.address.city == "Paris"
        assert loaded.address.country == "France"

    async def test_the_coordinate_survives_the_round_trip(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The geocoded coordinate is what the planner routes on."""
        repository = CustomerRepository(session)
        stored = await repository.create(customer)
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.address.is_geocoded() is True
        assert loaded.address.latitude == pytest.approx(48.8566)
        assert loaded.address.longitude == pytest.approx(2.3522)

    async def test_get_returns_none_for_an_unknown_id(
        self, session: AsyncSession
    ) -> None:
        """An absent customer reads as None, not as an error."""
        assert await CustomerRepository(session).get("no-such-id") is None

    async def test_a_new_customer_is_active(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A stored customer defaults to being served."""
        stored = await CustomerRepository(session).create(customer)
        assert stored.registration_status is RegistrationStatus.ACTIVE

    # ------------------------------------------------------------------ #
    #  Update
    # ------------------------------------------------------------------ #

    async def test_update_changes_the_stored_values(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """An updated customer reads back with the new values."""
        repository = CustomerRepository(session)
        stored = await repository.create(customer)
        edited = stored.model_copy(update={"last_name": "Durand-Petit"})
        updated = await repository.update(edited)
        assert updated is not None
        assert updated.last_name == "Durand-Petit"
        reloaded = await repository.get(stored.id)
        assert reloaded is not None
        assert reloaded.last_name == "Durand-Petit"

    async def test_update_does_not_move_the_creation_timestamp(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The row's own creation time is the truth, not the payload's.

        Notes:
            A client echoing back a stale created_at must not be able to
            rewrite when the record came into existence.
        """
        repository = CustomerRepository(session)
        stored = await repository.create(customer)
        created_at = stored.created_at
        edited = stored.model_copy(update={"first_name": "Marie-Claire"})
        updated = await repository.update(edited)
        assert updated is not None
        assert updated.created_at == created_at

    async def test_update_of_an_unknown_customer_returns_none(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Updating an absent customer reports rather than inserting."""
        ghost = customer.model_copy(update={"id": "no-such-id"})
        assert await CustomerRepository(session).update(ghost) is None

    async def test_update_without_an_id_returns_none(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A customer with no identifier cannot be updated."""
        assert await CustomerRepository(session).update(customer) is None

    # ------------------------------------------------------------------ #
    #  set_status
    # ------------------------------------------------------------------ #

    async def test_set_status_stops_a_customer(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Stopping a customer flips only the status."""
        repository = CustomerRepository(session)
        stored = await repository.create(customer)
        updated = await repository.set_status(stored.id, RegistrationStatus.STOPPED)
        assert updated is not None
        assert updated.is_active() is False
        assert updated.first_name == "Marie"

    async def test_set_status_of_an_unknown_customer_returns_none(
        self, session: AsyncSession
    ) -> None:
        """Stopping an absent customer reports rather than raising."""
        repository = CustomerRepository(session)
        assert (
            await repository.set_status("no-such-id", RegistrationStatus.STOPPED)
            is None
        )

    # ------------------------------------------------------------------ #
    #  Listing, search and pagination
    # ------------------------------------------------------------------ #

    async def test_list_orders_by_family_name(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Customers come back alphabetically, which is how they are browsed."""
        repository = CustomerRepository(session)
        for last_name in ("Zola", "Anouilh", "Molière"):
            await repository.create(
                Customer(**{**customer_kwargs, "last_name": last_name})
            )
        listed = await repository.list()
        assert [entry.last_name for entry in listed] == [
            "Anouilh",
            "Molière",
            "Zola",
        ]

    async def test_search_matches_the_name_case_insensitively(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A lower-case fragment finds a capitalised name."""
        repository = CustomerRepository(session)
        await repository.create(Customer(**customer_kwargs))
        await repository.create(
            Customer(
                **{
                    **customer_kwargs,
                    "last_name": "Bernard",
                    "email": "claire.bernard@example.com",
                }
            )
        )
        found = await repository.list(search="dura")
        assert len(found) == 1
        assert found[0].last_name == "Durand"

    async def test_search_matches_the_email(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """The email is searchable, so a customer can be found from a mail."""
        repository = CustomerRepository(session)
        await repository.create(Customer(**customer_kwargs))
        await repository.create(
            Customer(
                **{
                    **customer_kwargs,
                    "last_name": "Bernard",
                    "email": "claire.bernard@example.com",
                }
            )
        )
        found = await repository.list(search="claire.bernard@")
        assert len(found) == 1
        assert found[0].last_name == "Bernard"

    async def test_search_matches_the_city(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """The city is searchable, since rounds are organised by area."""
        repository = CustomerRepository(session)
        await repository.create(Customer(**customer_kwargs))
        found = await repository.list(search="paris")
        assert len(found) == 1

    async def test_the_status_filter_restricts_the_page(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Filtering by status returns only that status."""
        repository = CustomerRepository(session)
        active = await repository.create(Customer(**customer_kwargs))
        stopped = await repository.create(
            Customer(**{**customer_kwargs, "last_name": "Bernard"})
        )
        await repository.set_status(stopped.id, RegistrationStatus.STOPPED)
        listed = await repository.list(status=RegistrationStatus.ACTIVE)
        assert [entry.id for entry in listed] == [active.id]

    async def test_pagination_splits_the_result(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Pages are one-based and do not overlap."""
        repository = CustomerRepository(session)
        for index in range(5):
            await repository.create(
                Customer(**{**customer_kwargs, "last_name": f"Name{index}"})
            )
        first = await repository.list(page=1, size=2)
        second = await repository.list(page=2, size=2)
        assert len(first) == 2
        assert len(second) == 2
        assert {entry.id for entry in first}.isdisjoint({entry.id for entry in second})

    async def test_a_page_number_below_one_is_clamped(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A zero page reads as the first page, not as a negative offset.

        Notes:
            PostgreSQL rejects a negative OFFSET outright, so clamping turns a
            caller's off-by-one into a sensible page instead of a 500.
        """
        repository = CustomerRepository(session)
        await repository.create(customer)
        assert len(await repository.list(page=0)) == 1

    async def test_count_matches_the_same_filters_as_list(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A page total is computed from the filters that built the page."""
        repository = CustomerRepository(session)
        await repository.create(Customer(**customer_kwargs))
        await repository.create(
            Customer(
                **{
                    **customer_kwargs,
                    "last_name": "Bernard",
                    "email": "claire.bernard@example.com",
                }
            )
        )
        assert await repository.count() == 2
        assert await repository.count(search="dura") == 1

    async def test_count_is_zero_on_an_empty_table(self, session: AsyncSession) -> None:
        """An empty table counts as zero, not as an error."""
        assert await CustomerRepository(session).count() == 0

    # ------------------------------------------------------------------ #
    #  Delete
    # ------------------------------------------------------------------ #

    async def test_delete_removes_the_customer(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A deleted customer no longer reads back."""
        repository = CustomerRepository(session)
        stored = await repository.create(customer)
        assert await repository.delete(stored.id) is True
        assert await repository.get(stored.id) is None

    async def test_delete_of_an_unknown_customer_reports_false(
        self, session: AsyncSession
    ) -> None:
        """Deleting an absent customer is a no-op, not an error."""
        assert await CustomerRepository(session).delete("no-such-id") is False
