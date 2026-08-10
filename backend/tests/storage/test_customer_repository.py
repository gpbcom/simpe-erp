from __future__ import annotations

# Standard library imports
from datetime import date, timedelta
from typing import Any, Dict

# Third-party imports
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import QuoteStatus, RegistrationStatus
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.customers.customer_filter import CustomerFilter
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.quoting.quote import QuoteRepository


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

    async def test_a_new_customer_is_a_prospect(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A stored customer defaults to somebody the agency is talking to.

        Notes:
            The store keeps whatever the model decided; this asserts the two
            agree, so a default changed in one place cannot be silently
            overridden by the other.
        """
        stored = await CustomerRepository(session).create(customer)
        assert stored.registration_status is RegistrationStatus.PROSPECT

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

    @pytest.mark.parametrize(
        ("field", "matching", "other"),
        [
            pytest.param("city", "Lyon", "Paris", id="town"),
            pytest.param("postal_code", "69001", "75004", id="postcode"),
            pytest.param("email", "needle@example.fr", "hay@example.fr", id="email"),
            pytest.param("phone", "+33699999999", "+33612345678", id="phone"),
        ],
    )
    async def test_each_named_filter_matches_only_its_own_column(
        self,
        session: AsyncSession,
        customer_kwargs: Dict[str, Any],
        field: str,
        matching: str,
        other: str,
    ) -> None:
        """**A named filter is narrower than the search box, on purpose.**

        Args:
            session (AsyncSession): The database session.
            customer_kwargs (Dict[str, Any]): A valid customer.
            field (str): The filter under test.
            matching (str): The value the wanted customer carries.
            other (str): The value the unwanted one carries.

        Notes:
            ``search`` sweeps four columns because somebody typing into it has
            not decided which field they mean. A manager who has chosen the
            postcode box has decided, and matching their fragment against a
            surname would be the wrong answer.
        """
        repository = CustomerRepository(session)
        column = {"phone": "phone_number"}.get(field, field)
        address_fields = {"city", "postal_code"}

        def _kwargs(value: str, last_name: str) -> Dict[str, Any]:
            """Build a customer carrying one distinguishing value."""
            built = {**customer_kwargs, "last_name": last_name}
            if column in address_fields:
                built["address"] = {**built["address"], column: value}
            else:
                built[column] = value
            return built

        wanted = await repository.create(Customer(**_kwargs(matching, "Wanted")))
        await repository.create(Customer(**_kwargs(other, "Other")))

        listed = await repository.list(
            customer_filter=CustomerFilter(**{field: matching})
        )

        assert [entry.id for entry in listed] == [wanted.id]

    @pytest.mark.parametrize(
        "typed",
        [
            pytest.param("+33699999999", id="as stored, international"),
            pytest.param("+33 6 99 99 99 99", id="with spaces"),
            pytest.param("999999", id="the last digits off a caller display"),
        ],
    )
    async def test_the_phone_filter_matches_however_it_was_typed(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any], typed: str
    ) -> None:
        """**A stored number does not look like a typed one.**

        Args:
            session (AsyncSession): The database session.
            customer_kwargs (Dict[str, Any]): A valid customer.
            typed (str): One of the forms a manager might type.

        Notes:
            Pydantic normalises ``+33699999999`` to ``tel:+33-6-99-99-99-99`` on
            the way in. A plain ``ILIKE`` against that matches none of the forms
            above, so both sides are reduced to digits before comparing — and
            this is the test that would have caught it, because the naive
            version passed for the one input that happened to be typed exactly
            as stored.
        """
        repository = CustomerRepository(session)
        wanted = await repository.create(
            Customer(**{**customer_kwargs, "phone_number": "+33699999999"})
        )
        await repository.create(
            Customer(
                **{
                    **customer_kwargs,
                    "last_name": "Other",
                    "phone_number": "+33611111111",
                }
            )
        )

        listed = await repository.list(customer_filter=CustomerFilter(phone=typed))

        assert [entry.id for entry in listed] == [wanted.id]

    async def test_the_geocoding_filter_separates_the_two_kinds(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Whose address resolved, and whose did not.

        Args:
            session (AsyncSession): The database session.
            customer_kwargs (Dict[str, Any]): A valid customer.

        Notes:
            An operational worklist rather than a search: a customer with no
            coordinate is one no planning run can route to, and finding them
            all is how somebody fixes it before the next run.
        """
        repository = CustomerRepository(session)
        located = await repository.create(Customer(**customer_kwargs))
        unlocated = await repository.create(
            Customer(
                **{
                    **customer_kwargs,
                    "last_name": "Nowhere",
                    "address": {
                        **customer_kwargs["address"],
                        "latitude": None,
                        "longitude": None,
                    },
                }
            )
        )

        resolved = await repository.list(
            customer_filter=CustomerFilter(is_geocoded=True)
        )
        unresolved = await repository.list(
            customer_filter=CustomerFilter(is_geocoded=False)
        )

        assert [entry.id for entry in resolved] == [located.id]
        assert [entry.id for entry in unresolved] == [unlocated.id]

    async def test_the_ongoing_filter_finds_who_is_being_served(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """**Who are we serving right now, as opposed to who is on the book.**

        Args:
            session (AsyncSession): The database session.
            customer_kwargs (Dict[str, Any]): A valid customer.

        Notes:
            The one filter that is a join rather than a column. "Ongoing" means
            an **accepted** quote that has not passed its interruption date —
            narrower than the customer drawer's notion of "in flight", which
            also counts quotes merely sent or awaiting validation. The two
            answer different questions and are allowed to differ; this test is
            what pins the server's answer down.
        """
        customers = CustomerRepository(session)
        quotes = QuoteRepository(session)
        served = await customers.create(Customer(**customer_kwargs))
        idle = await customers.create(
            Customer(**{**customer_kwargs, "last_name": "Idle"})
        )
        await quotes.create(
            Quote(
                company_id="company-1",
                reference="Q-ONGOING",
                customer_id=served.id,
                status=QuoteStatus.ACCEPTED,
            )
        )

        with_work = await customers.list(
            customer_filter=CustomerFilter(has_ongoing_arrangement=True)
        )
        without_work = await customers.list(
            customer_filter=CustomerFilter(has_ongoing_arrangement=False)
        )

        assert [entry.id for entry in with_work] == [served.id]
        assert [entry.id for entry in without_work] == [idle.id]

    async def test_an_interrupted_arrangement_is_no_longer_ongoing(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A quote ended before today is history, not current work.

        Args:
            session (AsyncSession): The database session.
            customer_kwargs (Dict[str, Any]): A valid customer.

        Notes:
            The interruption date is **inclusive**, so a quote interrupted today
            is still running today. This uses yesterday, which is the first day
            it is not.
        """
        customers = CustomerRepository(session)
        quotes = QuoteRepository(session)
        stopped = await customers.create(Customer(**customer_kwargs))
        await quotes.create(
            Quote(
                company_id="company-1",
                reference="Q-ENDED",
                customer_id=stopped.id,
                status=QuoteStatus.ACCEPTED,
                interrupted_on=date.today() - timedelta(days=1),
            )
        )

        with_work = await customers.list(
            customer_filter=CustomerFilter(has_ongoing_arrangement=True)
        )

        assert with_work == []

    async def test_a_page_and_its_total_agree_about_the_filter(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """**The reason the predicates live in the shared query builder.**

        Args:
            session (AsyncSession): The database session.
            customer_kwargs (Dict[str, Any]): A valid customer.

        Notes:
            ``list`` and ``count`` build from one statement so a filtered page
            can never be counted against an unfiltered total — which would show
            a manager "1–25 of 40" over a grid holding three rows.
        """
        repository = CustomerRepository(session)
        await repository.create(Customer(**customer_kwargs))
        await repository.create(
            Customer(
                **{
                    **customer_kwargs,
                    "last_name": "Other",
                    "address": {**customer_kwargs["address"], "city": "Lyon"},
                }
            )
        )
        applied = CustomerFilter(city="Lyon")

        listed = await repository.list(customer_filter=applied)
        total = await repository.count(customer_filter=applied)

        assert len(listed) == total == 1

    async def test_the_status_filter_restricts_the_page(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Filtering by status returns only that status."""
        repository = CustomerRepository(session)
        active = await repository.create(
            Customer(
                **{
                    **customer_kwargs,
                    "registration_status": RegistrationStatus.ACTIVE,
                }
            )
        )
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
