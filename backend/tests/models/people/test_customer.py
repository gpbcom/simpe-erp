from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Dict

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.enums import BillingPeriodicity, RegistrationStatus
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.people.customer.exceptions import (
    MTCustomerInvalidAddress,
    MTCustomerInvalidBillingPeriodicity,
    MTCustomerInvalidDate,
    MTCustomerInvalidEmail,
    MTCustomerInvalidFirstName,
    MTCustomerInvalidId,
    MTCustomerInvalidLastName,
    MTCustomerInvalidPhoneNumber,
    MTCustomerInvalidRegistrationStatus,
    MTInvalidCustomerException,
)
from tests.annotations import ModelInput


@pytest.fixture
def valid_customer_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid customer.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {
        "first_name": "Marie",
        "last_name": "Durand",
        "phone_number": "+33612345678",
        "email": "marie.durand@example.com",
        "address": {
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
        },
    }


class TestCustomer:
    """Tests for the Customer model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A customer is a name, contact details and an address."""
        customer = Customer(**valid_customer_kwargs)
        assert customer.first_name == "Marie"
        assert customer.last_name == "Durand"
        assert customer.id is None

    def test_registration_status_defaults_to_prospect(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """**A new customer is somebody the agency is talking to.**

        Notes:
            Registering a customer records an enquiry. Agreeing to deliver care
            is a separate act. Defaulting to active would have the planner
            routing an assistant to a door nobody had agreed to knock on.
        """
        customer = Customer(**valid_customer_kwargs)
        assert customer.registration_status is RegistrationStatus.PROSPECT

    def test_the_address_is_built_from_a_mapping(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A mapping becomes a PostalAddress."""
        customer = Customer(**valid_customer_kwargs)
        assert isinstance(customer.address, PostalAddress)
        assert customer.address.city == "Paris"

    def test_an_already_built_address_is_accepted(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The address may be handed in as a built model."""
        address = PostalAddress(street="1 rue A", postal_code="75001", city="Paris")
        customer = Customer(**{**valid_customer_kwargs, "address": address})
        assert customer.address == address

    # ------------------------------------------------------------------ #
    #  Name validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_invalid_first_name_raises(
        self, valid_customer_kwargs: Dict[str, ModelInput], invalid_name: ModelInput
    ) -> None:
        """A first name that is not a non-empty string is rejected."""
        with pytest.raises(MTCustomerInvalidFirstName):
            Customer(**{**valid_customer_kwargs, "first_name": invalid_name})

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_invalid_last_name_raises(
        self, valid_customer_kwargs: Dict[str, ModelInput], invalid_name: ModelInput
    ) -> None:
        """A last name that is not a non-empty string is rejected."""
        with pytest.raises(MTCustomerInvalidLastName):
            Customer(**{**valid_customer_kwargs, "last_name": invalid_name})

    def test_names_are_stripped(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Surrounding whitespace is removed from both names."""
        customer = Customer(
            **{
                **valid_customer_kwargs,
                "first_name": "  Marie ",
                "last_name": " Durand  ",
            }
        )
        assert customer.full_name() == "Marie Durand"

    # ------------------------------------------------------------------ #
    #  phone_number validation
    # ------------------------------------------------------------------ #

    def test_a_phone_number_is_normalised(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A valid number is stored in its canonical form."""
        customer = Customer(
            **{**valid_customer_kwargs, "phone_number": "+33 6 12 34 56 78"}
        )
        assert "33" in customer.phone_number
        assert " " not in customer.phone_number

    @pytest.mark.parametrize(
        "invalid_phone",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(33612345678, id="Invalid - int"),
        ],
    )
    def test_a_missing_phone_number_raises_the_model_exception(
        self, valid_customer_kwargs: Dict[str, ModelInput], invalid_phone: ModelInput
    ) -> None:
        """A missing number raises the model's own exception.

        Notes:
            Without the wrapping validator this would surface as a bare
            ValidationError from the phone-number type.
        """
        with pytest.raises(MTCustomerInvalidPhoneNumber):
            Customer(**{**valid_customer_kwargs, "phone_number": invalid_phone})

    def test_an_undialable_number_is_rejected(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Digits that do not form a real number are rejected."""
        with pytest.raises(ValidationError):
            Customer(**{**valid_customer_kwargs, "phone_number": "not-a-number"})

    # ------------------------------------------------------------------ #
    #  email validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_email",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(123, id="Invalid - int"),
        ],
    )
    def test_a_missing_email_raises_the_model_exception(
        self, valid_customer_kwargs: Dict[str, ModelInput], invalid_email: ModelInput
    ) -> None:
        """A missing address raises the model's own exception."""
        with pytest.raises(MTCustomerInvalidEmail):
            Customer(**{**valid_customer_kwargs, "email": invalid_email})

    def test_a_malformed_email_is_rejected(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An address without a domain is rejected."""
        with pytest.raises(ValidationError):
            Customer(**{**valid_customer_kwargs, "email": "marie.durand"})

    # ------------------------------------------------------------------ #
    #  address validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_address",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param("12 rue de Rivoli", id="Invalid - string"),
            pytest.param([], id="Invalid - list"),
        ],
    )
    def test_invalid_address_raises(
        self, valid_customer_kwargs: Dict[str, ModelInput], invalid_address: ModelInput
    ) -> None:
        """An address that is neither a model nor a mapping is rejected."""
        with pytest.raises(MTCustomerInvalidAddress):
            Customer(**{**valid_customer_kwargs, "address": invalid_address})

    def test_a_malformed_address_raises_the_address_exception(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A bad field inside the address names that field.

        Notes:
            The customer validator asserts the shape and hands the payload
            back, so the nested model raises the precise exception.
        """
        # First-party imports
        from models.geo.exceptions import MTPostalAddressInvalidPostalCode

        with pytest.raises(MTPostalAddressInvalidPostalCode):
            Customer(
                **{
                    **valid_customer_kwargs,
                    "address": {
                        "street": "1 rue A",
                        "postal_code": "",
                        "city": "Paris",
                    },
                }
            )

    # ------------------------------------------------------------------ #
    #  registration_status validation
    # ------------------------------------------------------------------ #

    def test_status_is_coerced_from_a_string(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A string status becomes a RegistrationStatus member."""
        customer = Customer(
            **{**valid_customer_kwargs, "registration_status": "stopped"}
        )
        assert customer.registration_status is RegistrationStatus.STOPPED

    def test_a_none_status_defaults_to_prospect(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An explicit None yields the default rather than an error.

        Notes:
            Omitting the field and sending ``null`` mean the same thing —
            nobody has said — and the safe reading of that is the state that
            schedules nothing.
        """
        customer = Customer(**{**valid_customer_kwargs, "registration_status": None})
        assert customer.registration_status is RegistrationStatus.PROSPECT

    @pytest.mark.parametrize(
        "invalid_status",
        [
            pytest.param("paused", id="Invalid - unknown status"),
            pytest.param("ACTIVE", id="Invalid - wrong case"),
            pytest.param(1, id="Invalid - int"),
        ],
    )
    def test_invalid_status_raises(
        self, valid_customer_kwargs: Dict[str, ModelInput], invalid_status: ModelInput
    ) -> None:
        """A status outside the enum is rejected."""
        with pytest.raises(MTCustomerInvalidRegistrationStatus):
            Customer(**{**valid_customer_kwargs, "registration_status": invalid_status})

    # ------------------------------------------------------------------ #
    #  Billing periodicity
    # ------------------------------------------------------------------ #

    def test_a_customer_follows_the_agency_by_default(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """**Unset is the ordinary case, and it is not monthly.**

        Notes:
            The absence of an override has to stay an absence. Defaulting it to
            monthly would look identical on the day the record is written and
            wrong the day a manager changes the agency's rule, because every
            customer would be carrying a frozen copy of the old one.
        """
        customer = Customer(**valid_customer_kwargs)

        assert customer.billing_periodicity is None
        assert (
            customer.effective_periodicity(BillingPeriodicity.WEEKLY)
            is BillingPeriodicity.WEEKLY
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("weekly", id="As the string the API sends"),
            pytest.param(BillingPeriodicity.WEEKLY, id="As the enum member"),
        ],
    )
    def test_an_override_is_kept_whichever_way_it_arrives(
        self, valid_customer_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """Their own rule wins over the agency's, however it was sent."""
        customer = Customer(**{**valid_customer_kwargs, "billing_periodicity": value})

        assert customer.billing_periodicity is BillingPeriodicity.WEEKLY
        assert (
            customer.effective_periodicity(BillingPeriodicity.MONTHLY)
            is BillingPeriodicity.WEEKLY
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("fortnightly", id="Invalid - not a periodicity"),
            pytest.param("MONTHLY", id="Invalid - the wrong case"),
            pytest.param(2, id="Invalid - a number of weeks"),
        ],
    )
    def test_an_unknown_periodicity_is_refused(
        self, valid_customer_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """A granularity nothing can bill on is refused, not coerced."""
        with pytest.raises(MTCustomerInvalidBillingPeriodicity):
            Customer(**{**valid_customer_kwargs, "billing_periodicity": value})

    # ------------------------------------------------------------------ #
    #  Timestamp validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", ["created_at", "updated_at"])
    def test_invalid_timestamp_raises(
        self, valid_customer_kwargs: Dict[str, ModelInput], field: str
    ) -> None:
        """A non datetime-like timestamp is rejected."""
        with pytest.raises(MTCustomerInvalidDate):
            Customer(**{**valid_customer_kwargs, field: 1234567890})

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def test_full_name(self, valid_customer_kwargs: Dict[str, ModelInput]) -> None:
        """The display name joins the given and family names."""
        assert Customer(**valid_customer_kwargs).full_name() == "Marie Durand"

    def test_an_active_customer_may_be_served(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An active customer takes new work."""
        active = Customer(
            **{
                **valid_customer_kwargs,
                "registration_status": RegistrationStatus.ACTIVE,
            }
        )
        assert active.is_active() is True

    @pytest.mark.parametrize(
        ("status", "schedulable"),
        [
            pytest.param(RegistrationStatus.ACTIVE, True, id="active"),
            pytest.param(RegistrationStatus.PROSPECT, False, id="prospect"),
            pytest.param(RegistrationStatus.STOPPED, False, id="stopped"),
        ],
    )
    def test_only_an_active_customer_can_be_scheduled(
        self,
        valid_customer_kwargs: Dict[str, ModelInput],
        status: RegistrationStatus,
        schedulable: bool,
    ) -> None:
        """**The predicate the planner asks, and the reason PROSPECT exists.**

        Args:
            valid_customer_kwargs (Dict[str, ModelInput]): A valid customer.
            status (RegistrationStatus): The status under test.
            schedulable (bool): Whether the planner may place their work.

        Notes:
            A prospect may hold accepted, priced, perfectly routable quotes and
            still be unschedulable. That is not a defect in the quote — it is
            the agency not having agreed to deliver it yet.
        """
        customer = Customer(**{**valid_customer_kwargs, "registration_status": status})

        assert customer.can_be_scheduled() is schedulable

    def test_a_stopped_customer_may_not(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A stopped customer keeps their history but takes no new work."""
        customer = Customer(
            **{**valid_customer_kwargs, "registration_status": "stopped"}
        )
        assert customer.is_active() is False

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTCustomerInvalidAddress,
            MTCustomerInvalidBillingPeriodicity,
            MTCustomerInvalidDate,
            MTCustomerInvalidEmail,
            MTCustomerInvalidFirstName,
            MTCustomerInvalidId,
            MTCustomerInvalidLastName,
            MTCustomerInvalidPhoneNumber,
            MTCustomerInvalidRegistrationStatus,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidCustomerException."""
        assert issubclass(exception_class, MTInvalidCustomerException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_timestamps_serialize_to_iso_strings(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Timestamps leave the model as ISO-8601 text."""
        customer = Customer(
            **{
                **valid_customer_kwargs,
                "created_at": datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            }
        )
        assert customer.model_dump()["created_at"] == "2026-08-05T12:00:00+00:00"

    def test_model_dump_round_trip(
        self, valid_customer_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A customer survives a dump-and-rebuild unchanged."""
        customer = Customer(**valid_customer_kwargs)
        assert Customer(**customer.model_dump()) == customer
