from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Type

# Third-party imports
import pytest

# First-party imports
from models.auth.exceptions import (
    MTUserInvalidDate,
    MTUserInvalidEmail,
    MTUserInvalidFullName,
    MTUserInvalidId,
    MTUserInvalidPhotoUrl,
)
from models.auth.user import User
from models.base.exceptions import (
    MTInvalidPersonException,
    MTPersonInvalidAddress,
    MTPersonInvalidDate,
    MTPersonInvalidEmail,
    MTPersonInvalidFirstName,
    MTPersonInvalidId,
    MTPersonInvalidLastName,
    MTPersonInvalidPhoneNumber,
)
from models.base.person import Person
from models.base.portrait_holder import PortraitHolder
from models.enums import ContractType, UserRole
from models.people.customer import Customer
from models.people.customer.exceptions import (
    MTCustomerInvalidAddress,
    MTCustomerInvalidDate,
    MTCustomerInvalidEmail,
    MTCustomerInvalidFirstName,
    MTCustomerInvalidId,
    MTCustomerInvalidLastName,
    MTCustomerInvalidPhoneNumber,
)
from models.people.hca.exceptions import (
    MTHcaInvalidAddress,
    MTHcaInvalidDate,
    MTHcaInvalidEmail,
    MTHcaInvalidFirstName,
    MTHcaInvalidId,
    MTHcaInvalidLastName,
    MTHcaInvalidPhoneNumber,
    MTHcaInvalidPhotoUrl,
)
from models.people.hca_application.exceptions import (
    MTHcaApplicationInvalidEmail,
    MTHcaApplicationInvalidName,
)
from models.people.hca import Hca
from models.people.hca_application import HcaApplication

ADDRESS = {"street": "12 rue de Rivoli", "postal_code": "75004", "city": "Paris"}
HASH = "$2b$12$" + "a" * 53


def _hca(**overrides: object) -> Hca:
    """Build an assistant.

    Args:
        **overrides (object): Fields to replace.

    Returns:
        Hca: The assistant.
    """
    fields = {
        "company_id": "company-1",
        "first_name": "Luc",
        "last_name": "Martin",
        "phone_number": "+33698765432",
        "email": "luc.martin@example.com",
        "address": ADDRESS,
        "contract_type": ContractType.CDI,
    }
    fields.update(overrides)
    return Hca(**fields)


def _customer(**overrides: object) -> Customer:
    """Build a customer.

    Args:
        **overrides (object): Fields to replace.

    Returns:
        Customer: The customer.
    """
    fields = {
        "first_name": "Marie",
        "last_name": "Durand",
        "phone_number": "+33612345678",
        "email": "marie.durand@example.com",
        "address": ADDRESS,
    }
    fields.update(overrides)
    return Customer(**fields)


def _application(**overrides: object) -> HcaApplication:
    """Build an application.

    Args:
        **overrides (object): Fields to replace.

    Returns:
        HcaApplication: The application.
    """
    fields = {
        "company_id": "company-1",
        "first_name": "Ana",
        "last_name": "Lopez",
        "phone_number": "+33611223344",
        "email": "ana.lopez@example.com",
        "address": ADDRESS,
        "hashed_password": HASH,
    }
    fields.update(overrides)
    return HcaApplication(**fields)


def _user(**overrides: object) -> User:
    """Build an account.

    Args:
        **overrides (object): Fields to replace.

    Returns:
        User: The account.
    """
    fields = {
        "company_id": "company-1",
        "email": "claire.bernard@example.com",
        "full_name": "Claire Bernard",
        "role": UserRole.MANAGER,
    }
    fields.update(overrides)
    return User(**fields)


class TestEveryPersonModelDescendsFromPerson:
    """Tests that the shared record really is shared."""

    @pytest.mark.parametrize(
        "model",
        [
            pytest.param(Hca, id="Hca"),
            pytest.param(Customer, id="Customer"),
            pytest.param(HcaApplication, id="HcaApplication"),
            pytest.param(User, id="User"),
        ],
    )
    def test_it_is_a_person(self, model: Type[Person]) -> None:
        """**The point of the base.**

        Args:
            model (Type[Person]): The model under test.

        Notes:
            Asserted as a class relationship rather than by comparing field
            lists, because the value is that the *rules* are shared. Four
            copies of "an email must be a non-empty string" is four places for
            a fix to be applied to one of them.
        """
        assert issubclass(model, Person)

    @pytest.mark.parametrize(
        "field",
        [
            "id",
            "first_name",
            "last_name",
            "phone_number",
            "email",
            "address",
            "created_at",
            "updated_at",
        ],
    )
    def test_the_shared_fields_are_declared_once(self, field: str) -> None:
        """Every person carries the same eight fields.

        Args:
            field (str): The field the base is expected to own.
        """
        assert field in Person.model_fields


class TestPerModelExceptionsSurvive:
    """Tests that a shared rule still raises each model's own exception."""

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidEmail, id="Hca"),
            pytest.param(_customer, MTCustomerInvalidEmail, id="Customer"),
            pytest.param(_application, MTHcaApplicationInvalidEmail, id="Application"),
            pytest.param(_user, MTUserInvalidEmail, id="User"),
        ],
    )
    def test_a_blank_email_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """**The check the whole design rests on.**

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.

        Notes:
            The rule lives once, on ``Person``, and raises ``cls.INVALID_*``.
            Pydantic binds ``cls`` to the concrete subclass, so each model
            answers with its own class — which matters beyond tidiness: the
            API's exception-to-status map is keyed on them, and collapsing them
            would answer every model's malformed field with one status.
        """
        with pytest.raises(expected):
            build(email="   ")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidId, id="Hca"),
            pytest.param(_customer, MTCustomerInvalidId, id="Customer"),
            pytest.param(_user, MTUserInvalidId, id="User"),
        ],
    )
    def test_a_blank_identifier_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """The identifier rule dispatches the same way.

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.
        """
        with pytest.raises(expected):
            build(id="   ")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidFirstName, id="Hca"),
            pytest.param(_customer, MTCustomerInvalidFirstName, id="Customer"),
            pytest.param(_application, MTHcaApplicationInvalidName, id="Application"),
        ],
    )
    def test_a_blank_given_name_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """A person the agency has a form for must have both names.

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.

        Notes:
            ``User`` is absent on purpose: an account may be a mononym, and it
            relaxes this rule deliberately. See the account's own suite.
        """
        with pytest.raises(expected):
            build(first_name="   ")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidLastName, id="Hca"),
            pytest.param(_customer, MTCustomerInvalidLastName, id="Customer"),
            pytest.param(_application, MTHcaApplicationInvalidName, id="Application"),
            pytest.param(_user, MTUserInvalidFullName, id="User"),
        ],
    )
    def test_a_blank_family_name_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """Every person, account included, needs something to be called.

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.
        """
        with pytest.raises(expected):
            build(last_name="   ")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidPhoneNumber, id="Hca"),
            pytest.param(_customer, MTCustomerInvalidPhoneNumber, id="Customer"),
        ],
    )
    def test_a_blank_telephone_number_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """A number that is present must be usable.

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.
        """
        with pytest.raises(expected):
            build(phone_number="   ")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidAddress, id="Hca"),
            pytest.param(_customer, MTCustomerInvalidAddress, id="Customer"),
        ],
    )
    def test_a_malformed_address_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """The address rule dispatches the same way.

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.
        """
        with pytest.raises(expected):
            build(address="12 rue de Rivoli, Paris")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidDate, id="Hca"),
            pytest.param(_customer, MTCustomerInvalidDate, id="Customer"),
            pytest.param(_user, MTUserInvalidDate, id="User"),
        ],
    )
    def test_a_malformed_timestamp_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """The timestamp rule dispatches the same way.

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.
        """
        with pytest.raises(expected):
            build(created_at=17)


class TestSharedBehaviour:
    """Tests for what every person model now gets for free."""

    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(_hca, id="Hca"),
            pytest.param(_customer, id="Customer"),
            pytest.param(_application, id="Application"),
        ],
    )
    def test_the_display_name_is_composed(self, build: object) -> None:
        """One implementation, so no model can disagree about the format.

        Args:
            build (object): The factory for the model under test.
        """
        assert build().full_name() == build().first_name + " " + build().last_name

    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(_hca, id="Hca"),
            pytest.param(_customer, id="Customer"),
            pytest.param(_user, id="User"),
        ],
    )
    def test_timestamps_serialize_to_iso_8601(self, build: object) -> None:
        """A client reads a string, not a Python datetime.

        Args:
            build (object): The factory for the model under test.
        """
        record = build(updated_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC))

        assert record.model_dump()["updated_at"] == "2026-08-05T12:00:00+00:00"

    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(_hca, id="Hca"),
            pytest.param(_customer, id="Customer"),
        ],
    )
    def test_names_are_trimmed(self, build: object) -> None:
        """The stripping rule is stated once and applies everywhere.

        Args:
            build (object): The factory for the model under test.
        """
        record = build(first_name="  Jean  ", last_name="  Dupont  ")

        assert record.full_name() == "Jean Dupont"


class TestThePortraitMixin:
    """Tests for the photograph the two records that hold one share."""

    @pytest.mark.parametrize(
        "model",
        [pytest.param(Hca, id="Hca"), pytest.param(User, id="User")],
    )
    def test_a_holder_carries_the_portrait(self, model: Type[PortraitHolder]) -> None:
        """Both records that show a face inherit the same field.

        Args:
            model (Type[PortraitHolder]): The model under test.
        """
        assert issubclass(model, PortraitHolder)
        assert "photo_url" in model.model_fields

    @pytest.mark.parametrize(
        "model",
        [
            pytest.param(Customer, id="Customer"),
            pytest.param(HcaApplication, id="HcaApplication"),
        ],
    )
    def test_a_record_with_no_photograph_does_not_carry_one(
        self, model: Type[Person]
    ) -> None:
        """**Why the portrait is a mixin and not part of Person.**

        Args:
            model (Type[Person]): The model under test.

        Notes:
            Folding it into the base would publish a ``photo_url`` on every
            customer and every job application — a field the API would carry,
            the front-end would render, and nobody would ever fill in.
        """
        assert "photo_url" not in model.model_fields

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            pytest.param(_hca, MTHcaInvalidPhotoUrl, id="Hca"),
            pytest.param(_user, MTUserInvalidPhotoUrl, id="User"),
        ],
    )
    def test_a_third_party_url_raises_the_models_own_exception(
        self, build: object, expected: Type[MTInvalidPersonException]
    ) -> None:
        """**A security rule, which is why it is worth having in one place.**

        Args:
            build (object): The factory for the model under test.
            expected (Type[MTInvalidPersonException]): Its own exception.

        Notes:
            Both holders render the image wherever the person appears, so a
            remote one would report every viewer to whoever hosts it. Two
            copies of that check are two chances for one of them to be relaxed.
        """
        with pytest.raises(expected):
            build(photo_url="https://evil.example.com/tracker.png")

    @pytest.mark.parametrize(
        "build",
        [pytest.param(_hca, id="Hca"), pytest.param(_user, id="User")],
    )
    def test_a_url_the_object_store_issued_is_accepted(self, build: object) -> None:
        """The prefix the upload endpoint writes under is what passes.

        Args:
            build (object): The factory for the model under test.
        """
        stored = "https://cdn.example.com/hca-photos/subject/abc.jpg"

        assert str(build(photo_url=stored).photo_url) == stored

    @pytest.mark.parametrize(
        "build",
        [pytest.param(_hca, id="Hca"), pytest.param(_user, id="User")],
    )
    def test_a_blank_portrait_reads_as_none(self, build: object) -> None:
        """An empty form field means "no photo", not "invalid photo".

        Args:
            build (object): The factory for the model under test.
        """
        assert build(photo_url="   ").photo_url is None


class TestTheBaseItself:
    """Tests for Person's own defaults, which nothing in the app relies on."""

    @pytest.mark.parametrize(
        ("attribute", "expected"),
        [
            pytest.param("INVALID_ID", MTPersonInvalidId, id="id"),
            pytest.param("INVALID_FIRST_NAME", MTPersonInvalidFirstName, id="first"),
            pytest.param("INVALID_LAST_NAME", MTPersonInvalidLastName, id="last"),
            pytest.param(
                "INVALID_PHONE_NUMBER", MTPersonInvalidPhoneNumber, id="phone"
            ),
            pytest.param("INVALID_EMAIL", MTPersonInvalidEmail, id="email"),
            pytest.param("INVALID_ADDRESS", MTPersonInvalidAddress, id="address"),
            pytest.param("INVALID_DATE", MTPersonInvalidDate, id="date"),
        ],
    )
    def test_it_falls_back_to_a_typed_exception(
        self, attribute: str, expected: Type[MTInvalidPersonException]
    ) -> None:
        """A new person model raises something typed before it declares its own.

        Args:
            attribute (str): The class attribute under test.
            expected (Type[MTInvalidPersonException]): Its default.

        Notes:
            The default matters because the alternative is a bare ``ValueError``
            reaching the API's catch-all as an opaque 500.
        """
        assert getattr(Person, attribute) is expected

    def test_every_default_is_answerable_by_the_api(self) -> None:
        """The fallbacks all descend from the family the status map knows.

        Notes:
            ``MTInvalidPersonException`` has a row of its own, so a model that
            declares no exception of its own is still answered 422 rather than
            500.
        """
        for attribute in (
            "INVALID_ID",
            "INVALID_FIRST_NAME",
            "INVALID_LAST_NAME",
            "INVALID_PHONE_NUMBER",
            "INVALID_EMAIL",
            "INVALID_ADDRESS",
            "INVALID_DATE",
        ):
            assert issubclass(getattr(Person, attribute), MTInvalidPersonException)
