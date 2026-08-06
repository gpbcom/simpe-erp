from __future__ import annotations

# Third-party imports
import pytest

# First-party imports
from models.enums import EventRoutingKey
from models.exceptions import MTRoutingKeyMissingCompany

COMPANY = "156940b2-f71e-5aeb-8bfd-22a452311d8c"


class TestRoutingKeysAreScopedToAnAgency:
    """Tests for the routing key every message is published under.

    Notes:
        This is where the broker isolation actually lives. A queue bound to the
        wrong key does not error — it simply never receives anything, which
        looks exactly like a quiet system.
    """

    @pytest.mark.parametrize(
        "routing_key",
        list(EventRoutingKey),
        ids=lambda key: key.value,
    )
    def test_every_event_can_be_scoped(self, routing_key: EventRoutingKey) -> None:
        """Including the lifecycle one, so there is no special case.

        Args:
            routing_key (EventRoutingKey): The event to scope.

        Notes:
            ``company.created`` is scoped under the agency it announces rather
            than published globally. A "global" event would be one more rule to
            remember, and the worker that wants all of them binds
            ``company.created.*`` explicitly instead.
        """
        assert routing_key.scoped_to(COMPANY) == f"{routing_key.value}.{COMPANY}"

    def test_the_agency_goes_last(self) -> None:
        """So a binding can select one agency, or every agency, by suffix.

        Notes:
            Putting the identifier first would make "every event for this
            agency" easy and "this event for every agency" impossible — and the
            worker needs the second one to notice a newly founded agency.
        """
        scoped = EventRoutingKey.QUOTE_SUBMITTED.scoped_to(COMPANY)

        assert scoped.startswith("quote.submitted.")
        assert scoped.endswith(COMPANY)

    def test_two_agencies_never_share_a_key(self) -> None:
        """The property the isolation rests on."""
        first = EventRoutingKey.QUOTE_SUBMITTED.scoped_to("company-1")
        second = EventRoutingKey.QUOTE_SUBMITTED.scoped_to("company-2")

        assert first != second

    @pytest.mark.parametrize(
        "company_id",
        [
            pytest.param("", id="Refused - empty"),
            pytest.param(None, id="Refused - missing"),
        ],
    )
    def test_an_agencyless_key_is_refused(self, company_id: object) -> None:
        """``"quote.submitted."`` is valid, and binds to nothing.

        Args:
            company_id (object): The identifier to refuse.

        Notes:
            That is the point of raising: a key that silently reaches no queue
            is the failure this enumeration was written to prevent, one level
            down. A message published under it is lost with no error anywhere.
        """
        with pytest.raises(MTRoutingKeyMissingCompany):
            EventRoutingKey.QUOTE_SUBMITTED.scoped_to(company_id)

    def test_the_refusal_names_the_event(self) -> None:
        """So a log line says which publish was dropped."""
        with pytest.raises(MTRoutingKeyMissingCompany) as refusal:
            EventRoutingKey.PLANNING_RUN_REQUESTED.scoped_to("")

        assert "planning.run.requested" in str(refusal.value)
