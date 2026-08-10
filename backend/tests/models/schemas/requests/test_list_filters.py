from __future__ import annotations

# Standard library imports
from typing import Any, Dict, Type

# Third-party imports
import pytest

# First-party imports
from models.base.entity_filter import EntityFilter
from models.base.exceptions import MTInvalidEntityFilterException
from models.enums import (
    ContractType,
    NotificationKind,
    QuoteStatus,
    ServiceCategory,
)
from models.schemas.exceptions import (
    MTCertificationTypeFilterInvalidFlag,
    MTCertificationTypeFilterInvalidFragment,
    MTHcaFilterInvalidContractType,
    MTHcaFilterInvalidFlag,
    MTHcaFilterInvalidFragment,
    MTInterventionTypeFilterInvalidCategory,
    MTInterventionTypeFilterInvalidFlag,
    MTInterventionTypeFilterInvalidFragment,
    MTNotificationFilterInvalidFlag,
    MTNotificationFilterInvalidFragment,
    MTNotificationFilterInvalidKind,
    MTQuoteFilterInvalidFlag,
    MTQuoteFilterInvalidFragment,
    MTQuoteFilterInvalidStatus,
    MTSkillTypeFilterInvalidFlag,
    MTSkillTypeFilterInvalidFragment,
)
from models.schemas.requests.catalog.certification_type_filter import (
    CertificationTypeFilter,
)
from models.schemas.requests.catalog.intervention_type_filter import (
    InterventionTypeFilter,
)
from models.schemas.requests.catalog.skill_type_filter import SkillTypeFilter
from models.schemas.requests.hca.hca_filter import HcaFilter
from models.schemas.requests.notifications.notification_filter import (
    NotificationFilter,
)
from models.schemas.requests.quoting.quote_filter import QuoteFilter

#: Every screen's filter, with one text field and one flag field each.
FILTERS = (
    pytest.param(QuoteFilter, "search", "is_ongoing", id="quotes"),
    pytest.param(HcaFilter, "city", "field_employee", id="assistants"),
    pytest.param(InterventionTypeFilter, "code", "is_active", id="catalogue"),
    pytest.param(CertificationTypeFilter, "label", "is_active", id="certifications"),
    pytest.param(SkillTypeFilter, "search", "is_active", id="skills"),
    pytest.param(NotificationFilter, "search", "is_read", id="notifications"),
)


class TestEveryFilterObeysTheSharedRules:
    """Tests the rules :class:`EntityFilter` exists to state once."""

    @pytest.mark.parametrize(("filter_class", "text", "flag"), FILTERS)
    def test_an_unset_filter_narrows_nothing(
        self, filter_class: Type[EntityFilter], text: str, flag: str
    ) -> None:
        """**The difference between a filter and a search form.**

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            text (str): One of its text fields.
            flag (str): One of its flag fields.

        Notes:
            A caller sends the two boxes they filled in, not eight. A field
            they left alone must not silently narrow anything, or half the list
            disappears for a reason nothing on the screen explains.
        """
        assert filter_class().is_empty() is True

    @pytest.mark.parametrize(("filter_class", "text", "flag"), FILTERS)
    def test_one_set_field_makes_it_non_empty(
        self, filter_class: Type[EntityFilter], text: str, flag: str
    ) -> None:
        """``is_empty`` is what lets a caller log the right sentence.

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            text (str): One of its text fields.
            flag (str): One of its flag fields.
        """
        assert filter_class(**{text: "anything"}).is_empty() is False

    @pytest.mark.parametrize(("filter_class", "text", "flag"), FILTERS)
    @pytest.mark.parametrize("blank", ["", "   "])
    def test_a_cleared_box_is_not_a_filter(
        self, filter_class: Type[EntityFilter], text: str, flag: str, blank: str
    ) -> None:
        """**The case a form produces on every submission.**

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            text (str): One of its text fields.
            flag (str): One of its flag fields.
            blank (str): The blank the form submits.

        Notes:
            An input somebody typed in and then cleared sends ``""``. Read as a
            filter it matches nobody, and the screen shows an empty list for a
            box that looks empty too.
        """
        narrowed = filter_class(**{text: blank})

        assert getattr(narrowed, text) is None
        assert narrowed.is_empty() is True

    @pytest.mark.parametrize(("filter_class", "text", "flag"), FILTERS)
    def test_a_fragment_is_stripped(
        self, filter_class: Type[EntityFilter], text: str, flag: str
    ) -> None:
        """Surrounding space is not part of what somebody meant to type.

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            text (str): One of its text fields.
            flag (str): One of its flag fields.
        """
        assert getattr(filter_class(**{text: "  paris  "}), text) == "paris"

    @pytest.mark.parametrize(("filter_class", "text", "flag"), FILTERS)
    @pytest.mark.parametrize("value", [7, [], {}])
    def test_a_non_string_fragment_is_refused(
        self, filter_class: Type[EntityFilter], text: str, flag: str, value: Any
    ) -> None:
        """Tidying is not the same as accepting anything.

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            text (str): One of its text fields.
            flag (str): One of its flag fields.
            value (Any): The rejected fragment.
        """
        with pytest.raises(MTInvalidEntityFilterException):
            filter_class(**{text: value})

    @pytest.mark.parametrize(("filter_class", "text", "flag"), FILTERS)
    @pytest.mark.parametrize("value", ["false", "true", 0, 1])
    def test_a_non_boolean_flag_is_refused(
        self, filter_class: Type[EntityFilter], text: str, flag: str, value: Any
    ) -> None:
        """**``"false"`` is truthy, and that is the whole problem.**

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            text (str): One of its text fields.
            flag (str): One of its flag fields.
            value (Any): The rejected flag.

        Notes:
            A flag read the wrong way round answers the opposite question in
            silence — on a control whose entire job is to narrow a list.
        """
        with pytest.raises(MTInvalidEntityFilterException):
            filter_class(**{flag: value})

    @pytest.mark.parametrize(("filter_class", "text", "flag"), FILTERS)
    @pytest.mark.parametrize("value", [True, False])
    def test_a_flag_keeps_its_three_states(
        self, filter_class: Type[EntityFilter], text: str, flag: str, value: bool
    ) -> None:
        """``None`` is "do not filter", ``False`` is "only the false ones".

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            text (str): One of its text fields.
            flag (str): One of its flag fields.
            value (bool): The flag being set.

        Notes:
            Conflating the two would make an unticked box hide every record
            that *has* the thing, which is the opposite of doing nothing.
        """
        assert getattr(filter_class(**{flag: value}), flag) is value
        assert getattr(filter_class(), flag) is None


class TestEachFilterNamesItsOwnScreen:
    """Tests that a rejection points at the screen that caused it."""

    @pytest.mark.parametrize(
        ("filter_class", "field", "value", "expected"),
        [
            pytest.param(
                QuoteFilter, "search", 7, MTQuoteFilterInvalidFragment, id="quote text"
            ),
            pytest.param(
                QuoteFilter,
                "is_ongoing",
                "yes",
                MTQuoteFilterInvalidFlag,
                id="quote flag",
            ),
            pytest.param(
                HcaFilter, "city", 7, MTHcaFilterInvalidFragment, id="hca text"
            ),
            pytest.param(
                HcaFilter, "has_photo", "yes", MTHcaFilterInvalidFlag, id="hca flag"
            ),
            pytest.param(
                InterventionTypeFilter,
                "code",
                7,
                MTInterventionTypeFilterInvalidFragment,
                id="catalogue text",
            ),
            pytest.param(
                InterventionTypeFilter,
                "is_active",
                "yes",
                MTInterventionTypeFilterInvalidFlag,
                id="catalogue flag",
            ),
            pytest.param(
                CertificationTypeFilter,
                "code",
                7,
                MTCertificationTypeFilterInvalidFragment,
                id="certification text",
            ),
            pytest.param(
                CertificationTypeFilter,
                "is_active",
                "yes",
                MTCertificationTypeFilterInvalidFlag,
                id="certification flag",
            ),
            pytest.param(
                SkillTypeFilter,
                "code",
                7,
                MTSkillTypeFilterInvalidFragment,
                id="skill text",
            ),
            pytest.param(
                SkillTypeFilter,
                "is_active",
                "yes",
                MTSkillTypeFilterInvalidFlag,
                id="skill flag",
            ),
            pytest.param(
                NotificationFilter,
                "search",
                7,
                MTNotificationFilterInvalidFragment,
                id="notification text",
            ),
            pytest.param(
                NotificationFilter,
                "is_read",
                "yes",
                MTNotificationFilterInvalidFlag,
                id="notification flag",
            ),
        ],
    )
    def test_the_exception_belongs_to_the_screen(
        self,
        filter_class: Type[EntityFilter],
        field: str,
        value: Any,
        expected: Type[Exception],
    ) -> None:
        """**The status map is keyed on the class.**

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            field (str): The field being given a bad value.
            value (Any): That bad value.
            expected (Type[Exception]): The exception the screen must raise.

        Notes:
            A rejected assistant filter reporting itself as a quote one would
            send whoever is debugging it to the wrong screen. That is why the
            shared rules live on a base but the exceptions do not.
        """
        with pytest.raises(expected):
            filter_class(**{field: value})


class TestTheEnumeratedFilters:
    """Tests the one field per screen that is a closed list."""

    @pytest.mark.parametrize(
        ("filter_class", "field", "good", "expected"),
        [
            pytest.param(QuoteFilter, "status", "sent", QuoteStatus.SENT, id="quote"),
            pytest.param(
                HcaFilter, "contract_type", "cdi", ContractType.CDI, id="assistant"
            ),
            pytest.param(
                InterventionTypeFilter,
                "service_category",
                "comfort",
                ServiceCategory.COMFORT,
                id="catalogue",
            ),
            pytest.param(
                NotificationFilter,
                "kind",
                "quote-validated",
                NotificationKind.QUOTE_VALIDATED,
                id="notification",
            ),
        ],
    )
    def test_a_known_value_is_coerced(
        self,
        filter_class: Type[EntityFilter],
        field: str,
        good: str,
        expected: Any,
    ) -> None:
        """The wire carries a string; the repository wants the enum.

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            field (str): Its enumerated field.
            good (str): A valid value as the query string spells it.
            expected (Any): The enum member it must become.
        """
        assert getattr(filter_class(**{field: good}), field) is expected

    @pytest.mark.parametrize(
        ("filter_class", "field", "expected"),
        [
            pytest.param(QuoteFilter, "status", MTQuoteFilterInvalidStatus, id="quote"),
            pytest.param(
                HcaFilter,
                "contract_type",
                MTHcaFilterInvalidContractType,
                id="assistant",
            ),
            pytest.param(
                InterventionTypeFilter,
                "service_category",
                MTInterventionTypeFilterInvalidCategory,
                id="catalogue",
            ),
            pytest.param(
                NotificationFilter,
                "kind",
                MTNotificationFilterInvalidKind,
                id="notification",
            ),
        ],
    )
    def test_an_unknown_value_is_refused(
        self, filter_class: Type[EntityFilter], field: str, expected: Type[Exception]
    ) -> None:
        """A hand-edited link must not silently filter on nothing.

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            field (str): Its enumerated field.
            expected (Type[Exception]): The exception it must raise.
        """
        with pytest.raises(expected):
            filter_class(**{field: "invented"})

    @pytest.mark.parametrize(
        ("filter_class", "field"),
        [
            pytest.param(QuoteFilter, "status", id="quote"),
            pytest.param(HcaFilter, "contract_type", id="assistant"),
            pytest.param(InterventionTypeFilter, "service_category", id="catalogue"),
            pytest.param(NotificationFilter, "kind", id="notification"),
        ],
    )
    def test_a_select_reset_to_blank_clears_the_filter(
        self, filter_class: Type[EntityFilter], field: str
    ) -> None:
        """**A select reset to its blank option submits ``""``.**

        Args:
            filter_class (Type[EntityFilter]): The filter under test.
            field (str): Its enumerated field.

        Notes:
            Answering 422 for it would put an error where a list belongs, for a
            gesture that means "stop filtering by this".
        """
        narrowed = filter_class(**{field: ""})

        assert getattr(narrowed, field) is None
        assert narrowed.is_empty() is True


class TestWhatTheFiltersRefuseToCarry:
    """Tests the fields that are absent, which is where the permission lives."""

    def test_a_notification_filter_cannot_name_a_recipient(self) -> None:
        """**The whole of a cross-account read, had it been a field.**

        Notes:
            The account whose notifications these are comes from the
            credential. A ``recipient_id`` here would let anybody read anybody
            else's, and no amount of care in the endpoint would take that field
            away again.
        """
        smuggled: Dict[str, Any] = {"recipient_id": "user-9", "search": "x"}

        narrowed = NotificationFilter(**smuggled)

        assert not hasattr(narrowed, "recipient_id")

    def test_a_quote_filter_matches_identifiers_exactly(self) -> None:
        """``customer_id`` is an identifier, not a fragment.

        Notes:
            A quote list narrowed to "customers whose id contains 7" is not a
            question anybody asks, and matching an identifier loosely is how one
            customer's arrangements appear under another's name. The value is
            still tidied, but the repository compares it whole.
        """
        assert QuoteFilter(customer_id="  customer-1  ").customer_id == "customer-1"
