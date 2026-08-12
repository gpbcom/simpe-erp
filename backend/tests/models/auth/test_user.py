from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Dict

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.auth.exceptions import (
    MTInvalidUserException,
    MTUserInvalidLanguage,
    MTUserInvalidAddress,
    MTUserInvalidDate,
    MTUserInvalidEmail,
    MTUserInvalidFullName,
    MTUserInvalidHashedPassword,
    MTUserInvalidHcaId,
    MTUserInvalidId,
    MTUserInvalidPhoneNumber,
    MTUserInvalidPhotoUrl,
    MTUserInvalidRole,
    MTUserCustomerLinkRequiresCustomerRole,
    MTUserInvalidCustomerId,
    MTUserRoleCustomerRequiresCustomerId,
    MTUserRoleHcaRequiresHcaId,
)
from models.auth.user import User
from models.base.person import Person
from models.enums import Language, UserRole
from tests.annotations import ModelInput


@pytest.fixture
def valid_manager_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid manager account.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {
        "email": "manager@example.com",
        "full_name": "Claire Bernard",
        "role": UserRole.MANAGER,
        "company_id": "company-1",
        "hashed_password": "$2b$12$abcdefghijklmnopqrstuv",
    }


class TestUser:
    """Tests for the User model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An account is an address, a display name and a role."""
        user = User(**valid_manager_kwargs)
        assert user.email == "manager@example.com"
        assert user.role is UserRole.MANAGER
        assert user.is_active is True

    def test_an_hca_account_needs_an_hca_id(self) -> None:
        """An assistant account is linked to its assistant record."""
        user = User(
            company_id="company-1",
            email="luc@example.com",
            full_name="Luc Martin",
            role=UserRole.HCA,
            hca_id="hca-1",
        )
        assert user.hca_id == "hca-1"

    def test_a_password_is_optional(self) -> None:
        """An account can exist before a password is set."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=UserRole.MANAGER,
        )
        assert user.hashed_password is None

    # ------------------------------------------------------------------ #
    #  email validation
    # ------------------------------------------------------------------ #

    def test_the_email_is_lower_cased(self) -> None:
        """Sign-in is case-insensitive.

        Notes:
            Lower-casing is also what stops the uniqueness index being defeated
            by changing capitalisation.
        """
        user = User(
            company_id="company-1",
            email="  Manager@Example.COM  ",
            full_name="Claire",
            role=UserRole.MANAGER,
        )
        assert user.email == "manager@example.com"

    @pytest.mark.parametrize(
        "invalid_email",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_a_missing_email_raises_the_model_exception(
        self, valid_manager_kwargs: Dict[str, ModelInput], invalid_email: ModelInput
    ) -> None:
        """A missing address raises the model's own exception."""
        with pytest.raises(MTUserInvalidEmail):
            User(**{**valid_manager_kwargs, "email": invalid_email})

    def test_a_malformed_email_is_rejected(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An address without a domain is rejected."""
        with pytest.raises(ValidationError):
            User(**{**valid_manager_kwargs, "email": "manager"})

    # ------------------------------------------------------------------ #
    #  Other field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("field", "invalid_value", "expected_exception"),
        [
            pytest.param("id", "", MTUserInvalidId, id="Invalid - empty id"),
            pytest.param("id", 7, MTUserInvalidId, id="Invalid - int id"),
            pytest.param(
                "full_name", "", MTUserInvalidFullName, id="Invalid - empty name"
            ),
            pytest.param(
                "full_name", None, MTUserInvalidFullName, id="Invalid - None name"
            ),
            pytest.param(
                "hashed_password",
                "",
                MTUserInvalidHashedPassword,
                id="Invalid - empty hash",
            ),
            pytest.param(
                "hashed_password",
                1,
                MTUserInvalidHashedPassword,
                id="Invalid - int hash",
            ),
            pytest.param(
                "role", "superuser", MTUserInvalidRole, id="Invalid - unknown role"
            ),
            pytest.param(
                "role", "ADMIN", MTUserInvalidRole, id="Invalid - wrong case role"
            ),
            pytest.param("hca_id", "", MTUserInvalidHcaId, id="Invalid - empty hca_id"),
            pytest.param(
                "created_at",
                1234567890,
                MTUserInvalidDate,
                id="Invalid - int timestamp",
            ),
        ],
    )
    def test_invalid_fields_raise(
        self,
        valid_manager_kwargs: Dict[str, ModelInput],
        field: str,
        invalid_value: ModelInput,
        expected_exception: type,
    ) -> None:
        """Each field rejects its own invalid values with its own exception."""
        with pytest.raises(expected_exception):
            User(**{**valid_manager_kwargs, field: invalid_value})

    def test_a_none_role_defaults_to_the_least_privileged(self) -> None:
        """A missing role never fails open into a manager or admin account."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=None,
            hca_id="hca-1",
        )
        assert user.role is UserRole.HCA

    def test_the_password_hash_is_not_stripped(self) -> None:
        """A hash is opaque; trimming it would corrupt the credential."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=UserRole.MANAGER,
            hashed_password="  $2b$12$abc  ",
        )
        assert user.hashed_password == "  $2b$12$abc  "

    # ------------------------------------------------------------------ #
    #  Cross-field validation
    # ------------------------------------------------------------------ #

    def test_an_hca_account_without_a_link_raises(self) -> None:
        """An assistant account with no hca_id cannot be built.

        Notes:
            Without the link there is nothing to compare a planning request
            against, so the account could read no planning at all — or a naive
            check could read it as unrestricted. Refusing to build it removes
            the state entirely.
        """
        with pytest.raises(MTUserRoleHcaRequiresHcaId):
            User(
                company_id="company-1",
                email="luc@example.com",
                full_name="Luc Martin",
                role=UserRole.HCA,
            )

    @pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.ADMIN])
    def test_non_hca_accounts_need_no_link(self, role: UserRole) -> None:
        """Only assistant accounts require an assistant record."""
        user = User(company_id="company-1", email="a@b.com", full_name="A B", role=role)
        assert user.hca_id is None

    # ------------------------------------------------------------------ #
    #  Role helpers
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            pytest.param(UserRole.HCA, False, id="hca is not a manager"),
            pytest.param(UserRole.MANAGER, True, id="manager is a manager"),
            pytest.param(UserRole.ADMIN, True, id="admin outranks manager"),
        ],
    )
    def test_is_manager(self, role: UserRole, expected: bool) -> None:
        """Manager privileges are held by managers and admins."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=role,
            hca_id="hca-1" if role is UserRole.HCA else None,
        )
        assert user.is_manager() is expected

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            pytest.param(UserRole.HCA, False, id="hca is not an admin"),
            pytest.param(UserRole.MANAGER, False, id="manager is not an admin"),
            pytest.param(UserRole.ADMIN, True, id="admin is an admin"),
        ],
    )
    def test_is_admin(self, role: UserRole, expected: bool) -> None:
        """Only the admin role is an administrator."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=role,
            hca_id="hca-1" if role is UserRole.HCA else None,
        )
        assert user.is_admin() is expected

    # ------------------------------------------------------------------ #
    #  owns_hca — the row-level planning rule
    # ------------------------------------------------------------------ #

    def test_an_assistant_owns_their_own_planning(self) -> None:
        """An assistant may read the planning of their own record."""
        user = User(
            company_id="company-1",
            email="luc@example.com",
            full_name="Luc",
            role=UserRole.HCA,
            hca_id="hca-1",
        )
        assert user.owns_hca("hca-1") is True

    def test_an_assistant_does_not_own_another_planning(self) -> None:
        """An assistant may not read another assistant's planning.

        Notes:
            This is the rule a route guard cannot express: the guard only
            proves the caller is *an* assistant, not the right one.
        """
        user = User(
            company_id="company-1",
            email="luc@example.com",
            full_name="Luc",
            role=UserRole.HCA,
            hca_id="hca-1",
        )
        assert user.owns_hca("hca-2") is False

    @pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.ADMIN])
    def test_managers_and_admins_see_every_planning(self, role: UserRole) -> None:
        """Managers and admins are not restricted to one assistant."""
        user = User(company_id="company-1", email="a@b.com", full_name="A B", role=role)
        assert user.owns_hca("hca-1") is True
        assert user.owns_hca("hca-2") is True

    def test_a_customer_owns_nobodys_planning(self) -> None:
        """**The hole the customer role opened, closed.**

        Notes:
            ``owns_hca`` read "not an assistant means yes" — written when the
            only other roles were manager and administrator. The moment a fourth
            role existed, that spelling handed every assistant's diary, with
            every household's name and address on it, to every customer.

            The test is here rather than in a security review because the bug is
            invisible: nothing raises, nothing looks wrong, the data is simply
            served to the wrong person.
        """
        customer = User(
            company_id="company-1",
            email="marie@example.com",
            full_name="Marie Durand",
            role=UserRole.CUSTOMER,
            customer_id="customer-1",
        )

        assert customer.owns_hca("hca-1") is False
        assert customer.owns_hca("hca-2") is False

    # ------------------------------------------------------------------ #
    #  owns_customer — the row-level portal rule
    # ------------------------------------------------------------------ #

    def test_a_customer_owns_their_own_file(self) -> None:
        """A household may read its own records."""
        user = User(
            company_id="company-1",
            email="marie@example.com",
            full_name="Marie Durand",
            role=UserRole.CUSTOMER,
            customer_id="customer-1",
        )

        assert user.owns_customer("customer-1") is True

    def test_a_customer_does_not_own_another_file(self) -> None:
        """One household may not read another's.

        Notes:
            The portal never takes a customer identifier from the path — it
            resolves the household from the credential — so this is the second
            of two gates rather than the only one. It exists because a route
            added later may not remember the first.
        """
        user = User(
            company_id="company-1",
            email="marie@example.com",
            full_name="Marie Durand",
            role=UserRole.CUSTOMER,
            customer_id="customer-1",
        )

        assert user.owns_customer("customer-2") is False

    @pytest.mark.parametrize("role", [UserRole.HCA, UserRole.MANAGER, UserRole.ADMIN])
    def test_staff_are_not_narrowed_to_one_household(self, role: UserRole) -> None:
        """Staff are answered ``True``; their own route guards gate them.

        Args:
            role (UserRole): The staff role under test.
        """
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=role,
            hca_id="hca-1" if role is UserRole.HCA else None,
        )

        assert user.owns_customer("customer-1") is True

    # ------------------------------------------------------------------ #
    #  The customer link runs both ways
    # ------------------------------------------------------------------ #

    def test_a_customer_account_must_name_a_customer(self) -> None:
        """Without the link the account resolves to no household."""
        with pytest.raises(MTUserRoleCustomerRequiresCustomerId):
            User(
                company_id="company-1",
                email="marie@example.com",
                full_name="Marie Durand",
                role=UserRole.CUSTOMER,
            )

    @pytest.mark.parametrize("role", [UserRole.HCA, UserRole.MANAGER, UserRole.ADMIN])
    def test_no_staff_account_may_name_a_customer(self, role: UserRole) -> None:
        """**The direction that matters.**

        Args:
            role (UserRole): The staff role under test.

        Notes:
            A manager carrying a ``customer_id`` satisfies every staff guard
            *and* resolves to one household — an account that is both sides of
            the boundary at once. Refused at construction, so no service has to
            remember to check for it.
        """
        with pytest.raises(MTUserCustomerLinkRequiresCustomerRole):
            User(
                company_id="company-1",
                email="a@b.com",
                full_name="A B",
                role=role,
                hca_id="hca-1" if role is UserRole.HCA else None,
                customer_id="customer-1",
            )

    @pytest.mark.parametrize(
        "value",
        [pytest.param("", id="empty"), pytest.param("   ", id="whitespace")],
    )
    def test_a_blank_customer_link_is_refused(self, value: str) -> None:
        """A link that matches nothing is worse than no link.

        Args:
            value (str): The blank identifier.

        Notes:
            Kept, it would present an empty portal as though the household
            simply had no visits — which is indistinguishable from the truth.
        """
        with pytest.raises(MTUserInvalidCustomerId):
            User(
                company_id="company-1",
                email="marie@example.com",
                full_name="Marie Durand",
                role=UserRole.CUSTOMER,
                customer_id=value,
            )

    def test_a_customer_link_is_stripped(self) -> None:
        """Surrounding space is not part of the identifier."""
        user = User(
            company_id="company-1",
            email="marie@example.com",
            full_name="Marie Durand",
            role=UserRole.CUSTOMER,
            customer_id="  customer-1  ",
        )

        assert user.customer_id == "customer-1"

    # ------------------------------------------------------------------ #
    #  An account is a Person
    # ------------------------------------------------------------------ #

    def test_an_account_is_a_person(self) -> None:
        """The account shares the person record rather than restating it."""
        assert issubclass(User, Person)

    @pytest.mark.parametrize(
        ("display_name", "given", "family"),
        [
            pytest.param("Claire Bernard", "Claire", "Bernard", id="two names"),
            pytest.param(
                "Jean Pierre de la Tour",
                "Jean",
                "Pierre de la Tour",
                id="split on the first space, not the last",
            ),
            pytest.param("Root", "", "Root", id="a mononym is all family name"),
            pytest.param("  Ana  Lopez  ", "Ana", "Lopez", id="trimmed"),
        ],
    )
    def test_a_display_name_is_stored_as_two_names(
        self,
        valid_manager_kwargs: Dict[str, ModelInput],
        display_name: str,
        given: str,
        family: str,
    ) -> None:
        """**The compatibility shim the whole rebase rests on.**

        Args:
            valid_manager_kwargs (Dict[str, ModelInput]): A valid account.
            display_name (str): What the caller passes.
            given (str): The given name expected.
            family (str): The family name expected.

        Notes:
            Every caller — the sign-up form, the staff-account route, the
            seeder — has always passed one ``full_name``, and no screen asks an
            account holder for their surname separately. Splitting here is what
            let ``User`` become a ``Person`` without touching any of them.
        """
        user = User(**{**valid_manager_kwargs, "full_name": display_name})

        assert (user.first_name, user.last_name) == (given, family)

    @pytest.mark.parametrize(
        "display_name",
        [
            pytest.param("Claire Bernard", id="two names"),
            pytest.param("Jean Pierre de la Tour", id="a long family name"),
            pytest.param("Root", id="a mononym"),
        ],
    )
    def test_the_display_name_round_trips_exactly(
        self, valid_manager_kwargs: Dict[str, ModelInput], display_name: str
    ) -> None:
        """What went in comes back out.

        Args:
            valid_manager_kwargs (Dict[str, ModelInput]): A valid account.
            display_name (str): The name to round-trip.

        Notes:
            This is why the split is on the *first* space. Splitting on the
            last would read back identically for two-part names and file
            "Jean Pierre de la Tour" under the surname "Tour" — and it is the
            round trip that lets the stored column be replaced without anybody
            noticing.
        """
        user = User(**{**valid_manager_kwargs, "full_name": display_name})

        assert user.full_name() == display_name

    def test_explicit_names_win_over_a_display_name(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A caller that knows both names is not second-guessed."""
        user = User(
            **{
                **valid_manager_kwargs,
                "full_name": "Ignored Entirely",
                "first_name": "Claire",
                "last_name": "Bernard",
            }
        )

        assert user.full_name() == "Claire Bernard"

    def test_a_mononym_renders_without_a_leading_space(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An empty given name must not reach a screen as " Root".

        Notes:
            The base joins both halves unconditionally, which is right for a
            person the agency has a form for. An account overrides it because
            a service account has one name, and the greeting on every email
            would otherwise start with a space.
        """
        user = User(**{**valid_manager_kwargs, "full_name": "Root"})

        assert user.full_name() == "Root"

    def test_a_missing_display_name_raises_the_models_exception(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A blank name is refused as a name, not as a missing field.

        Notes:
            Without this the shim would pass the payload through untouched and
            Pydantic would report "first_name: Field required" — a message
            about a field no caller has ever heard of.
        """
        with pytest.raises(MTUserInvalidFullName):
            User(**{**valid_manager_kwargs, "full_name": "   "})

    def test_the_public_view_still_carries_the_display_name(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """**The API surface did not move.**

        Notes:
            The two halves are published as well, so nothing is hidden, but
            ``full_name`` is what the account screen, the emails and the
            front-end read — and it is derived rather than stored, so it cannot
            disagree with them.
        """
        published = User(**valid_manager_kwargs).to_public_dict()

        assert published["full_name"] == "Claire Bernard"
        assert published["first_name"] == "Claire"
        assert published["last_name"] == "Bernard"

    @pytest.mark.parametrize("field", ["phone_number", "address"])
    def test_the_contact_fields_are_optional_on_an_account(
        self, valid_manager_kwargs: Dict[str, ModelInput], field: str
    ) -> None:
        """An account is a credential, not a contact record.

        Args:
            valid_manager_kwargs (Dict[str, ModelInput]): A valid account.
            field (str): The field expected to default to None.

        Notes:
            Required on ``Person``, because an assistant's address is a routing
            depot and a customer's is where the care happens. A manager has
            neither, and there is no screen that asks them for one — so the
            account widens the two rather than storing blanks.
        """
        assert getattr(User(**valid_manager_kwargs), field) is None

    def test_a_supplied_telephone_number_is_still_checked(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Optional means absent or usable, never present and blank."""
        with pytest.raises(MTUserInvalidPhoneNumber):
            User(**{**valid_manager_kwargs, "phone_number": "   "})

    def test_a_supplied_address_is_still_checked(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Same rule as the telephone number."""
        with pytest.raises(MTUserInvalidAddress):
            User(**{**valid_manager_kwargs, "address": "12 rue de Rivoli"})

    def test_the_sign_in_address_is_lower_cased(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The account overrides the base, which leaves case alone.

        Notes:
            For an assistant and a customer the address is contact
            information. Here it is the sign-in, so lower-casing is what makes
            sign-in case-insensitive and stops the uniqueness index being
            defeated by capitalisation.
        """
        user = User(**{**valid_manager_kwargs, "email": "Claire.BERNARD@Example.com"})

        assert user.email == "claire.bernard@example.com"

    # ------------------------------------------------------------------ #
    #  Portrait
    # ------------------------------------------------------------------ #

    def test_an_account_has_no_portrait_until_one_is_uploaded(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A manager's account is valid with no photograph at all."""
        assert User(**valid_manager_kwargs).photo_url is None

    def test_a_portrait_the_object_store_issued_is_accepted(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A URL under the photo prefix is what an upload hands back."""
        user = User(
            **{
                **valid_manager_kwargs,
                "photo_url": "https://cdn.example.com/hca-photos/user-1/abc.jpg",
            }
        )
        assert str(user.photo_url).endswith("/hca-photos/user-1/abc.jpg")

    def test_a_blank_portrait_reads_as_none(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An empty form field means "no photo", not "invalid photo"."""
        user = User(**{**valid_manager_kwargs, "photo_url": "   "})
        assert user.photo_url is None

    @pytest.mark.parametrize(
        "photo_url",
        [
            "https://evil.example.com/tracker.png",
            "ftp://cdn.example.com/hca-photos/user-1/abc.jpg",
            "/hca-photos/user-1/abc.jpg",
            42,
        ],
    )
    def test_a_portrait_this_application_did_not_store_is_refused(
        self, valid_manager_kwargs: Dict[str, ModelInput], photo_url: ModelInput
    ) -> None:
        """Only a URL under the photo prefix may be stored.

        Notes:
            The avatar is rendered wherever the account is shown, so a remote
            one would report every viewer to whoever hosts it.
        """
        with pytest.raises(MTUserInvalidPhotoUrl):
            User(**{**valid_manager_kwargs, "photo_url": photo_url})

    def test_a_portrait_serializes_as_plain_text(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The store column is text, so a dump must not carry a URL object."""
        user = User(
            **{
                **valid_manager_kwargs,
                "photo_url": "https://cdn.example.com/hca-photos/user-1/abc.jpg",
            }
        )
        assert user.model_dump()["photo_url"] == (
            "https://cdn.example.com/hca-photos/user-1/abc.jpg"
        )

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTUserInvalidDate,
            MTUserInvalidEmail,
            MTUserInvalidFullName,
            MTUserInvalidHashedPassword,
            MTUserInvalidHcaId,
            MTUserInvalidId,
            MTUserInvalidPhoneNumber,
            MTUserInvalidPhotoUrl,
            MTUserInvalidRole,
            MTUserRoleHcaRequiresHcaId,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidUserException."""
        assert issubclass(exception_class, MTInvalidUserException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_to_public_dict_excludes_the_password_hash(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The credential never leaves the backend.

        Notes:
            Excluded here rather than at each call site, so a new endpoint
            cannot leak it by forgetting to.
        """
        public = User(**valid_manager_kwargs).to_public_dict()
        assert "hashed_password" not in public
        assert public["email"] == "manager@example.com"

    def test_to_public_dict_is_json_serializable(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The public view survives a JSON round-trip."""
        # Standard library imports
        import json

        user = User(
            **{
                **valid_manager_kwargs,
                "created_at": datetime(2026, 8, 5, tzinfo=UTC),
            }
        )
        assert json.loads(json.dumps(user.to_public_dict()))["role"] == "manager"

    def test_timestamps_serialize_to_iso_strings(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Timestamps leave the model as ISO-8601 text."""
        user = User(
            **{
                **valid_manager_kwargs,
                "updated_at": datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            }
        )
        assert user.model_dump()["updated_at"] == "2026-08-05T12:00:00+00:00"

    def test_model_dump_round_trip(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An account survives a dump-and-rebuild unchanged."""
        user = User(**valid_manager_kwargs)
        assert User(**user.model_dump()) == user


class TestAccountLanguage:
    """Tests for the language preference the emailed documents follow."""

    def test_french_is_the_default(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An account nobody has set a preference on is a French one."""
        assert User(**valid_manager_kwargs).language is Language.FR

    def test_a_known_language_is_coerced_from_a_string(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The API sends ``"en"``; the model holds a member."""
        assert (
            User(**{**valid_manager_kwargs, "language": "en"}).language is Language.EN
        )

    def test_none_reads_as_the_default(
        self, valid_manager_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The column arrived after the rows did.

        Notes:
            An account with no stored preference is ordinary, not broken, so
            ``None`` is the default rather than an error.
        """
        assert (
            User(**{**valid_manager_kwargs, "language": None}).language is Language.FR
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("de", id="Invalid - a language we do not speak"),
            pytest.param("french", id="Invalid - the name, not the code"),
            pytest.param("FR", id="Invalid - the right code, wrong case"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_an_unknown_language_is_refused(
        self, valid_manager_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """**Refused rather than quietly defaulted.**

        Args:
            valid_manager_kwargs (Dict[str, ModelInput]): Base arguments.
            value (ModelInput): The rejected language.

        Notes:
            A preference the holder set and the server ignored is worse than
            one it rejected: the screen would go on showing their choice while
            every emailed document came out in the other language.
        """
        with pytest.raises(MTUserInvalidLanguage):
            User(**{**valid_manager_kwargs, "language": value})

    def test_the_language_exception_shares_the_model_base(self) -> None:
        """One except clause still catches everything this model raises."""
        assert issubclass(MTUserInvalidLanguage, MTInvalidUserException)
