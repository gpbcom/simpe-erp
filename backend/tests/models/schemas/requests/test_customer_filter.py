from __future__ import annotations

# Standard library imports
from typing import Any, Optional

# Third-party imports
import pytest

# First-party imports
from models.enums import RegistrationStatus
from models.schemas.exceptions import (
    MTCustomerFilterInvalidFlag,
    MTCustomerFilterInvalidFragment,
    MTCustomerFilterInvalidStatus,
    MTInvalidCustomerFilterException,
)
from models.schemas.requests.customers.customer_filter import CustomerFilter

#: Every text filter, so the shared rules are asserted on all of them rather
#: than on whichever one somebody thought of.
FRAGMENTS = ("search", "city", "postal_code", "email", "phone")

#: Every three-state flag.
FLAGS = ("has_ongoing_arrangement", "is_geocoded")


class TestCustomerFilter:
    """Tests for what narrows the customer book."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_an_empty_filter_narrows_nothing(self) -> None:
        """**The default has to be harmless.**

        Notes:
            The screen sends the two boxes somebody filled in, not eight. If an
            unset field narrowed anything, opening the page would show a
            filtered book and nothing would say so.
        """
        applied = CustomerFilter()

        assert applied.is_empty() is True
        assert applied.model_dump(exclude_none=True) == {}

    def test_a_populated_filter_is_not_empty(self) -> None:
        """One field is enough to make it a filter."""
        assert CustomerFilter(city="Paris").is_empty() is False

    def test_every_field_is_optional(self) -> None:
        """Constructing one with no arguments must not raise."""
        assert set(CustomerFilter().model_dump()) == {
            "search",
            "status",
            "city",
            "postal_code",
            "email",
            "phone",
            "has_ongoing_arrangement",
            "is_geocoded",
        }

    # ------------------------------------------------------------------ #
    #  Text fragments
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", FRAGMENTS)
    def test_a_fragment_is_stripped(self, field: str) -> None:
        """Surrounding space is the user's, not part of what they meant.

        Args:
            field (str): The text filter under test.
        """
        assert getattr(CustomerFilter(**{field: "  Paris  "}), field) == "Paris"

    @pytest.mark.parametrize("field", FRAGMENTS)
    @pytest.mark.parametrize(
        "value",
        [pytest.param("", id="empty"), pytest.param("   ", id="whitespace")],
    )
    def test_a_blank_fragment_reads_as_unset(self, field: str, value: str) -> None:
        """**A cleared input box is not a filter on the empty string.**

        Args:
            field (str): The text filter under test.
            value (str): The blank value the box sends.

        Notes:
            This is the case that would otherwise answer nobody: a manager
            types into the town box, changes their mind and clears it, and the
            grid empties because no customer lives in a town called "".
        """
        assert getattr(CustomerFilter(**{field: value}), field) is None

    @pytest.mark.parametrize("field", FRAGMENTS)
    @pytest.mark.parametrize(
        "value",
        [pytest.param(42, id="int"), pytest.param(["Paris"], id="list")],
    )
    def test_a_fragment_of_the_wrong_type_is_refused(
        self, field: str, value: Any
    ) -> None:
        """Only a string or nothing.

        Args:
            field (str): The text filter under test.
            value (Any): The rejected value.
        """
        with pytest.raises(MTCustomerFilterInvalidFragment):
            CustomerFilter(**{field: value})

    # ------------------------------------------------------------------ #
    #  Status
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("status", list(RegistrationStatus))
    def test_every_status_is_accepted(self, status: RegistrationStatus) -> None:
        """Each of the three is a filter somebody may want.

        Args:
            status (RegistrationStatus): The status under test.
        """
        assert CustomerFilter(status=status.value).status is status

    def test_an_absent_status_stays_absent(self) -> None:
        """**It must not inherit the customer model's default.**

        Notes:
            ``Customer`` defaults an unset status to ``PROSPECT``. Copying that
            here would turn "I did not filter by status" into "show me only
            prospects", which is the whole book silently disappearing.
        """
        assert CustomerFilter().status is None
        assert CustomerFilter(status=None).status is None
        assert CustomerFilter(status="").status is None

    def test_an_unknown_status_is_refused(self) -> None:
        """A status the system has no word for is a mistake, not a filter."""
        with pytest.raises(MTCustomerFilterInvalidStatus):
            CustomerFilter(status="lapsed")

    def test_the_refusal_names_the_alternatives(self) -> None:
        """The message says what would have worked."""
        with pytest.raises(MTCustomerFilterInvalidStatus) as raised:
            CustomerFilter(status="lapsed")

        for value in RegistrationStatus.values():
            assert value in str(raised.value)

    # ------------------------------------------------------------------ #
    #  Three-state flags
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", FLAGS)
    @pytest.mark.parametrize("value", [True, False])
    def test_a_flag_keeps_both_of_its_two_set_states(
        self, field: str, value: bool
    ) -> None:
        """**False is a filter, not an absence.**

        Args:
            field (str): The flag under test.
            value (bool): The value it is given.

        Notes:
            "Only customers with no ongoing arrangement" is a question a
            manager asks. Treating ``False`` as unset would answer a different
            one — every customer — and look like the filter simply not working.
        """
        assert getattr(CustomerFilter(**{field: value}), field) is value

    @pytest.mark.parametrize("field", FLAGS)
    def test_an_absent_flag_is_none_rather_than_false(self, field: str) -> None:
        """Three states, and the unset one is distinguishable.

        Args:
            field (str): The flag under test.
        """
        assert getattr(CustomerFilter(), field) is None

    @pytest.mark.parametrize("field", FLAGS)
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("false", id="a truthy string"),
            pytest.param("true", id="a string that looks right"),
            pytest.param(1, id="an int"),
        ],
    )
    def test_a_flag_that_is_not_a_boolean_is_refused(
        self, field: str, value: Any
    ) -> None:
        """``"false"`` is truthy, and a filter read backwards is silent.

        Args:
            field (str): The flag under test.
            value (Any): The rejected value.

        Notes:
            Over the wire this never happens — the endpoint binds the filter
            with ``Depends()``, so FastAPI coerces ``?is_geocoded=false`` to a
            boolean before the model sees it. What this guards is a filter
            built by hand in Python, where a stray string would otherwise
            answer the opposite question without a word.
        """
        with pytest.raises(MTCustomerFilterInvalidFlag):
            CustomerFilter(**{field: value})

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTCustomerFilterInvalidFlag,
            MTCustomerFilterInvalidFragment,
            MTCustomerFilterInvalidStatus,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the family the API maps.

        Args:
            exception_class (type): The exception under test.

        Notes:
            ``api/exception_handlers.py`` has one row for the family, so a leaf
            that fell outside it would answer 500 instead of 422.
        """
        assert issubclass(exception_class, MTInvalidCustomerFilterException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_it_round_trips(self) -> None:
        """A filter survives a dump-and-rebuild unchanged."""
        applied = CustomerFilter(
            search="Martin",
            status=RegistrationStatus.PROSPECT,
            city="Paris",
            has_ongoing_arrangement=False,
        )

        assert CustomerFilter(**applied.model_dump()) == applied

    @pytest.mark.parametrize("field", FRAGMENTS)
    def test_an_unset_field_is_omitted_from_a_sparse_dump(self, field: str) -> None:
        """What the repository logs is what was actually asked for.

        Args:
            field (str): The one field that is set.
        """
        dumped = CustomerFilter(**{field: "x"}).model_dump(exclude_none=True)

        assert dumped == {field: "x"}

    @pytest.mark.parametrize("value", [None, "Paris"])
    def test_the_city_filter_accepts_absence_and_a_value(
        self, value: Optional[str]
    ) -> None:
        """The two states a text filter legitimately has.

        Args:
            value (Optional[str]): Unset, or a fragment.
        """
        assert CustomerFilter(city=value).city == value
