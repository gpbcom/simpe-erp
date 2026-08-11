from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Dict, Optional, Tuple, Type, Union

# Third-party imports
from pydantic import (
    Field,
    HttpUrl,
    JsonValue,
    field_validator,
    model_validator,
)
from pydantic_extra_types.phone_numbers import PhoneNumber

# First-party imports
from models.auth.exceptions import (
    MTUserCustomerLinkRequiresCustomerRole,
    MTUserInvalidAccountOrigin,
    MTUserInvalidAddress,
    MTUserInvalidCompanyId,
    MTUserInvalidCustomerId,
    MTUserInvalidDate,
    MTUserInvalidEmail,
    MTUserInvalidFullName,
    MTUserInvalidHashedPassword,
    MTUserInvalidHcaId,
    MTUserInvalidId,
    MTUserInvalidLanguage,
    MTUserInvalidMustChangePassword,
    MTUserInvalidPhoneNumber,
    MTUserInvalidPhotoUrl,
    MTUserInvalidRole,
    MTUserRoleCustomerRequiresCustomerId,
    MTUserRoleHcaRequiresHcaId,
    MTUserStaffAccountNeedsChange,
)
from models.base.exceptions import MTInvalidPersonException
from models.base.person import Person
from models.base.portrait_holder import PortraitHolder
from models.enums import AccountOrigin, Language, UserRole
from models.geo.postal_address import PostalAddress


class User(Person, PortraitHolder):
    """An account able to sign in to the backend.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        email (EmailStr): Sign-in address; unique across accounts.
        full_name (str): Display name.
        hashed_password (Optional[str]): Bcrypt hash of the password.
        role (UserRole): What the account may do.
        is_active (bool): Whether sign-in is permitted.
        hca_id (Optional[str]): The assistant record this account belongs to.
        customer_id (Optional[str]): The customer record this account belongs
            to. Set for a customer account and forbidden on any other — see
            :meth:`check_customer_link`.
        company_id (str): The company this account belongs to. Required for
            every role — see :meth:`validate_company_id`.
        account_origin (AccountOrigin): Whether the account was
            self-registered or created by staff.
        photo_url (Optional[HttpUrl]): URL of the holder's portrait in the
            object store, when one has been uploaded. Inherited from
            :class:`~models.base.portrait_holder.PortraitHolder`.
        must_change_password (bool): Whether the holder must set a new
            password before the account can do anything else.
        password_changed_at (Optional[datetime]): When the holder last
            chose their own password; ``None`` if they never have.
            Required for an assistant account, and absent otherwise.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - ``hca_id`` is what makes row-level access possible. An assistant may
          only read their own planning, and the check compares this field with
          the assistant whose planning was asked for — a route guard alone would
          only prove the caller is *an* assistant, not the right one. The
          cross-field validator therefore refuses to build an assistant account
          that carries no link, since such an account could never be checked.
        - ``hashed_password`` is optional so a user record can exist before a
          password is set, but it is never serialised: see
          :meth:`to_public_dict`.
        - ``photo_url`` lives on the *account* rather than only on the assistant
          record, because every signed-in person has an account and only some of
          them are assistants. A manager or an administrator had nowhere to put a
          portrait at all, so their own account screen showed a blank circle with
          nothing to click.
        - ``customer_id`` is the same idea on the other axis, and its rule runs
          **both ways**: a customer account must carry one, and no other role
          may. A manager holding a ``customer_id`` would pass the staff guards
          *and* resolve to a household, which is the shape a privilege bug takes.
    """

    INVALID_ID: ClassVar[Type[MTInvalidPersonException]] = MTUserInvalidId
    INVALID_FIRST_NAME: ClassVar[Type[MTInvalidPersonException]] = MTUserInvalidFullName  # noqa: E501
    INVALID_LAST_NAME: ClassVar[Type[MTInvalidPersonException]] = MTUserInvalidFullName  # noqa: E501
    INVALID_PHONE_NUMBER: ClassVar[Type[MTInvalidPersonException]] = (
        MTUserInvalidPhoneNumber
    )
    INVALID_EMAIL: ClassVar[Type[MTInvalidPersonException]] = MTUserInvalidEmail  # noqa: E501
    INVALID_ADDRESS: ClassVar[Type[MTInvalidPersonException]] = MTUserInvalidAddress  # noqa: E501
    INVALID_DATE: ClassVar[Type[MTInvalidPersonException]] = MTUserInvalidDate
    INVALID_PHOTO_URL: ClassVar[Type[MTInvalidPersonException]] = MTUserInvalidPhotoUrl  # noqa: E501
    phone_number: Optional[PhoneNumber] = Field(
        default=None,
        description="Contact telephone number, when one has been recorded.",
    )
    address: Optional[PostalAddress] = Field(
        default=None,
        description="Postal address, when one has been recorded.",
    )
    hashed_password: Optional[str] = Field(
        default=None,
        description="Bcrypt hash of the password.",
    )
    role: UserRole = Field(
        default=UserRole.HCA,
        description="What the account may do.",
    )
    is_active: bool = Field(
        default=True,
        description="Whether sign-in is permitted.",
    )
    hca_id: Optional[str] = Field(
        default=None,
        description="The assistant record this account belongs to.",
    )
    customer_id: Optional[str] = Field(
        default=None,
        description="The customer record this account belongs to.",
    )
    company_id: str = Field(
        description="The company this account belongs to.",
    )
    account_origin: AccountOrigin = Field(
        default=AccountOrigin.SELF_REGISTERED,
        description="Whether the account was self-registered or staff-created.",
    )
    photo_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL of the holder's portrait in the object store.",
    )
    language: Language = Field(
        default=Language.FR,
        description="The language this holder reads the application in.",
    )
    must_change_password: bool = Field(
        default=False,
        description="Whether the password must be changed before anything else.",
    )
    password_changed_at: Optional[datetime] = Field(
        default=None,
        description="When the holder last chose their own password.",
    )

    @classmethod
    def name_parts(cls, display_name: str) -> Tuple[str, str]:
        """Split a display name into a given name and a family name.

        Args:
            display_name (str): The single name an account is given.

        Returns:
            Tuple[str, str]: The given name — empty for a mononym — and the
            family name.

        Raises:
            MTUserInvalidFullName: If ``display_name`` is not a non-empty
                string.

        Notes:
            - **The one place the rule lives.** It is used by
              :meth:`split_display_name` when an account is built and by
              :meth:`~service.auth.auth.AuthService.update_account` when one is
              renamed, and a second copy of "where does the surname start" is a
              second answer.
            - The split is on the **first** space, so the round trip through
              :meth:`full_name` is exact. A name with no space goes entirely into
              the family name; see :meth:`validate_first_name`.
        """
        if not isinstance(display_name, str) or not display_name.strip():
            raise cls.INVALID_FIRST_NAME(
                f"Invalid full_name: {display_name!r}. "  # noqa: E501
                "Must be a non-empty string."
            )
        given, _, family = display_name.strip().partition(" ")
        return (given, family.strip()) if family.strip() else ("", given)

    @model_validator(mode="before")
    def split_display_name(cls, values: JsonValue) -> JsonValue:
        """Accept a single ``full_name`` and store it as two names.

        Args:
            values (JsonValue): The raw payload the account is built from.

        Returns:
            JsonValue: The payload, with ``first_name`` and ``last_name``
            filled in when only a display name was supplied.

        Notes:
            - **An account collects one name, a person has two.** Every caller —
             the sign-up form, the staff-account route, the seeder — has always
             passed ``full_name="Claire Bernard"``, and there is no screen
             anywhere that asks an account holder for their surname separately.
             Rather than change all of them, the display name is split here and
             recomposed by :meth:`~models.base.person.Person.full_name`.
           - The split is on the **first** space, which makes the round trip
             exact: ``"Jean Pierre de la Tour"`` stores ``"Jean"`` and
             ``"Pierre de la Tour"`` and reads back identical. A name with no
             space at all — a mononym, or a service account called ``root`` —
             goes entirely into ``last_name``, which is why
            :meth:`validate_first_name` below accepts an empty given name where
            :class:`~models.base.person.Person` does not.
           - Explicit ``first_name``/``last_name`` win, so nothing here gets in
             the way of a caller that does know both.
        """
        if not isinstance(values, dict) or "full_name" not in values:
            return values
        if values.get("first_name") is not None or values.get("last_name") is not None:  # noqa: E501
            return values
        given, family = cls.name_parts(values["full_name"])
        supplied = dict(values)
        supplied["first_name"] = given
        supplied["last_name"] = family
        return supplied

    @field_validator("first_name", mode="before")
    def validate_first_name(cls, value: Optional[str]) -> str:
        """Validates that ``first_name`` is a string, possibly empty.

        Args:
            value (Optional[str]): Raw ``first_name`` value.

        Returns:
            str: The stripped given name, or ``""``.

        Raises:
            MTUserInvalidFullName: If ``value`` is not a string.

        Notes:
            **Overrides** :meth:`~models.base.person.Person.validate_first_name`,
            which requires a non-empty value. An account may be a mononym or a
            service account, and :meth:`split_display_name` puts such a name
            entirely in ``last_name`` — so an empty given name is a real state
            here, unlike for an assistant or a customer, who are people the
            agency has a form for.
        """
        if value is None:
            return ""
        if not isinstance(value, str):
            raise cls.INVALID_FIRST_NAME(
                f"Invalid first_name: {value!r}. Must be a string."
            )
        return value.strip()

    @field_validator("email", mode="before")
    def validate_email(cls, value: Optional[str]) -> str:
        """Validates that ``email`` is a non-empty string, and lower-cases it.

        Args:
            value (Optional[str]): Raw ``email`` value.

        Returns:
            str: The stripped, lower-cased address.

        Raises:
            MTUserInvalidEmail: If ``value`` is not a non-empty string.

        Notes:
            **Overrides** :meth:`~models.base.person.Person.validate_email`,
            which leaves the case alone because for most people the address is
            contact information. This one is the *sign-in*, so it is lower-cased
            to make sign-in case-insensitive and to stop the uniqueness index
            being defeated by capitalisation.
        """
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_EMAIL(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("phone_number", mode="before")
    def validate_phone_number(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``phone_number`` is absent or a non-empty string.

        Args:
            value (Optional[str]): Raw ``phone_number`` value.

        Returns:
            Optional[str]: The stripped number, or ``None``.

        Raises:
            MTUserInvalidPhoneNumber: If ``value`` is present but not a
                non-empty string.

        Notes:
            **Overrides** the base's, which requires one. An account is a
            credential; the number of somebody the agency schedules is on their
            assistant record.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_PHONE_NUMBER(
                f"Invalid phone_number: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("address", mode="before")
    def validate_address(
        cls, value: Optional[Union[PostalAddress, Dict[str, JsonValue]]]
    ) -> Optional[Union[PostalAddress, Dict[str, JsonValue]]]:
        """Validates that ``address`` is absent, an address or a mapping.

        Args:
            value (Optional[Union[PostalAddress, Dict[str, JsonValue]]]): Raw
                ``address`` value.

        Returns:
            Union[PostalAddress, Dict[str, JsonValue], None]: The value handed
            back for Pydantic to build, or ``None``.

        Raises:
            MTUserInvalidAddress: If ``value`` is present but is neither a
                :class:`~models.geo.postal_address.PostalAddress` nor a
                mapping.

        Notes:
            **Overrides** the base's, which requires one, for the same reason
            as :meth:`validate_phone_number`.
        """
        if value is None:
            return None
        if not isinstance(value, (PostalAddress, dict)):
            raise cls.INVALID_ADDRESS(
                f"Invalid address: {value!r}. "
                f"Must be a PostalAddress, a mapping, or None."
            )
        return value

    @field_validator("hashed_password", mode="before")
    def validate_hashed_password(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``hashed_password`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``hashed_password`` value.

        Returns:
            Optional[str]: The hash, or ``None`` when no password is set.

        Raises:
            MTUserInvalidHashedPassword: If ``value`` is neither ``None`` nor a
                non-empty string.

        Notes:
            The value is not stripped: a hash is opaque, and trimming it would
            silently corrupt a credential rather than reject it.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidHashedPassword(
                "Invalid hashed_password. Must be a non-empty string or None."
            )
        return value

    @field_validator("role", mode="before")
    def validate_role(cls, value: Optional[Union[str, UserRole]]) -> UserRole:
        """Validates that ``role`` is a known user role.

        Args:
            value (Optional[Union[str, UserRole]]): Raw ``role`` value. ``None``
                falls back to :attr:`UserRole.HCA`.

        Returns:
            UserRole: The coerced role.

        Raises:
            MTUserInvalidRole: If ``value`` is not a known role.

        Notes:
            The default is the least-privileged role. A typo in a stored role
            must never fail open into a manager or admin account.
        """
        if value is None:
            return UserRole.HCA
        if isinstance(value, UserRole):
            return value
        try:
            return UserRole(value)
        except ValueError:
            raise MTUserInvalidRole(
                f"Invalid role: {value!r}. Must be one of: "
                f"{', '.join(UserRole.values())}."
            ) from None

    @field_validator("hca_id", mode="before")
    def validate_hca_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``hca_id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``hca_id`` value.

        Returns:
            Optional[str]: The assistant identifier, or ``None``.

        Raises:
            MTUserInvalidHcaId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidHcaId(
                f"Invalid hca_id: {value!r}. "  # noqa: E501
                "Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("customer_id", mode="before")
    def validate_customer_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``customer_id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``customer_id`` value.

        Returns:
            Optional[str]: The customer identifier, or ``None``.

        Raises:
            MTUserInvalidCustomerId: If ``value`` is neither ``None`` nor a
                non-empty string.

        Notes:
            Stripped, and a whitespace-only value refused rather than kept. Every
            portal route resolves the household from this field by equality; a
            ``" "`` that matched nothing would present an empty space as though
            the customer simply had no visits.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidCustomerId(
                f"Invalid customer_id: {value!r}. "  # noqa: E501
                "Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("language", mode="before")
    def validate_language(cls, value: Optional[Union[str, Language]]) -> Language:  # noqa: E501
        """Validates that ``language`` is one the application speaks.

        Args:
            value (Optional[Union[str, Language]]): Raw ``language`` value.

        Returns:
            Language: The coerced language.

        Raises:
            MTUserInvalidLanguage: If ``value`` is not a known language.

        Notes:
            - ``None`` reads as the default rather than as an error: the
              column arrived after the rows did, and an account nobody has
              set a preference on is an ordinary account.
            - An *unknown* code is refused. A preference the holder set and
              the server silently ignored is worse than one it rejected —
              the screen would go on showing their choice while every
              document came out in the other language.
        """
        if value is None:
            return Language.FR
        if isinstance(value, Language):
            return value
        try:
            return Language(value)
        except ValueError:
            raise MTUserInvalidLanguage(
                f"Invalid language: {value!r}. Must be one of: "
                f"{', '.join(Language.values())}."
            ) from None

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that ``company_id`` names the agency this account is in.

        Args:
            value (Optional[str]): Raw ``company_id`` value.

        Returns:
            str: The identifier.

        Raises:
            MTUserInvalidCompanyId: If ``value`` is not a non-empty string.

        Notes:
            **Required, for every role.** An administrator, a manager and an
            assistant all belong to exactly one agency, and an account without
            one cannot be placed: it is not covered by any per-company scoping,
            and nothing it publishes can be routed to the right agency's queue.
            Allowing ``None`` here is what made that possible, so the field no
            longer accepts it.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidCompanyId(
                f"Invalid company_id: {value!r}. Must be a non-empty string "
                f"naming the agency this account belongs to."
            )
        return value.strip()

    @field_validator("account_origin", mode="before")
    def validate_account_origin(
        cls, value: Optional[Union[str, AccountOrigin]]
    ) -> AccountOrigin:
        """Validates that ``account_origin`` is a known origin.

        Args:
            value (Optional[Union[str, AccountOrigin]]): Raw origin value.

        Returns:
            AccountOrigin: The coerced origin.

        Raises:
            MTUserInvalidAccountOrigin: If ``value`` is not a known origin.
        """
        if value is None:
            return AccountOrigin.SELF_REGISTERED
        if isinstance(value, AccountOrigin):
            return value
        try:
            return AccountOrigin(value)
        except ValueError:
            raise MTUserInvalidAccountOrigin(
                f"Invalid account_origin: {value!r}. Must be one of: "
                f"{', '.join(AccountOrigin.values())}."
            ) from None

    @field_validator("must_change_password", mode="before")
    def validate_must_change_password(cls, value: Optional[bool]) -> bool:
        """Validates that the forced-change flag is a boolean.

        Args:
            value (Optional[bool]): Raw flag value.

        Returns:
            bool: The flag.

        Raises:
            MTUserInvalidMustChangePassword: If ``value`` is neither ``None``
                nor a boolean.

        Notes:
            Strings are refused rather than coerced. ``"false"`` is truthy, and
            a stored ``"false"`` read as "must change" would lock somebody out
            of their own account — while the reverse would quietly waive the
            change this whole flag exists to force.
        """
        if value is None:
            return False
        if not isinstance(value, bool):
            raise MTUserInvalidMustChangePassword(
                f"Invalid must_change_password: {value!r}. Must be a boolean."
            )
        return value

    @model_validator(mode="after")
    def check_staff_account_must_change(self) -> User:
        """Ensure a staff-created account is made to choose its own password.

        Returns:
            User: ``self`` for chaining.

        Raises:
            MTUserStaffAccountNeedsChange: If the account was created by staff,
                already carries a credential, and is not required to change it.

        Notes:
            - **The specification's "MANDATORY" is enforced here, at
              construction.** An account whose password was typed by somebody
              else is a credential two people know; requiring the change is what
              ends that, and a flag that can be left off by whoever writes the
              next admin screen is not a requirement.
            - The check applies only while the temporary password is still the
              one in force. Once ``password_changed_at`` is set the holder has
              chosen their own, so the flag is correctly off — without that
              second condition an account could not be *read back* after changing
              its password, which is a validator making a legitimate state
              unrepresentable.
            - It also applies only once a credential exists: an account being
              assembled before its temporary password is set has nothing to
              change yet.
        """
        if (
            self.account_origin is AccountOrigin.CREATED_BY_STAFF
            and self.hashed_password
            and not self.password_changed_at
            and not self.must_change_password
        ):
            raise MTUserStaffAccountNeedsChange(
                "Invalid must_change_password: an account created by an "
                "administrator or manager must change its temporary password "
                "at first sign-in."
            )
        return self

    @model_validator(mode="after")
    def check_hca_link(self) -> User:
        """Ensure an assistant account is linked to an assistant record.

        Returns:
            User: ``self`` for chaining.

        Raises:
            MTUserRoleHcaRequiresHcaId: If the role is
                :attr:`UserRole.HCA` and no ``hca_id`` is set.

        Notes:
            Without the link there is nothing to compare a planning request
            against, so the account could read no planning at all — or, worse,
            a naive check could read it as "unrestricted". Refusing to build
            the account removes that state entirely.
        """
        if self.role is UserRole.HCA and self.hca_id is None:
            raise MTUserRoleHcaRequiresHcaId(
                "Invalid hca_id: an account with the 'hca' role must be linked "
                "to an assistant record, or its planning access cannot be "
                "checked."
            )
        return self

    @model_validator(mode="after")
    def check_customer_link(self) -> User:
        """Ensure the customer role and the customer link imply each other.

        Returns:
            User: ``self`` for chaining.

        Raises:
            MTUserRoleCustomerRequiresCustomerId: If the role is
                :attr:`UserRole.CUSTOMER` and no ``customer_id`` is set.
            MTUserCustomerLinkRequiresCustomerRole: If any other role carries a
                ``customer_id``.

        Notes:
            - **Both directions, unlike the assistant rule, and deliberately so.**
              Missing link, missing space: every portal route resolves the
              household from this field, so a customer account without one could
              read nothing — or, under a check written the forgiving way,
              everything.
            - The other direction is the one that matters. A manager carrying a
              ``customer_id`` is an account that satisfies the staff guards *and*
              resolves to one household, which is the exact shape a privilege
              bug takes. Refused at construction, so the state never exists.
        """
        if self.role is UserRole.CUSTOMER and self.customer_id is None:
            raise MTUserRoleCustomerRequiresCustomerId(
                "Invalid customer_id: an account with the 'customer' role must "
                "be linked to a customer record, or it resolves to no household."  # noqa: E501
            )
        if self.role is not UserRole.CUSTOMER and self.customer_id is not None:
            raise MTUserCustomerLinkRequiresCustomerRole(
                f"Invalid customer_id: an account with the {self.role.value!r} "  # noqa: E501
                f"role must not name a customer record."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_public_dict(self) -> Dict[str, JsonValue]:
        """Return a JSON-serializable view of the account without its secret.

        Returns:
            Dict[str, JsonValue]: Every field except ``hashed_password``.

        Notes:
            This is the only shape an account may leave the backend in. The
            password hash is excluded here rather than at each call site, so a
            new endpoint cannot leak it by forgetting to.
        """
        published = self.model_dump(mode="json", exclude={"hashed_password"})
        published["full_name"] = self.full_name()
        return published

    def full_name(self) -> str:
        """Return the account's display name.

        Returns:
            str: The two names joined, or just the one when there is only one.

        Notes:
            **Overrides** :meth:`~models.base.person.Person.full_name`, which
            joins both halves unconditionally because for an assistant or a
            customer both are required. An account may be a mononym or a
            service account, whose whole name sits in ``last_name`` with an
            empty given name — and the base's version would render that with a
            leading space, which then reaches every screen and every email that
            greets somebody by name.
        """
        return " ".join(part for part in (self.first_name, self.last_name) if part)  # noqa: E501

    def is_manager(self) -> bool:
        """Return whether the account has manager privileges or above.

        Returns:
            bool: ``True`` for a manager or an admin.
        """
        return self.role.has_at_least(UserRole.MANAGER)

    def is_admin(self) -> bool:
        """Return whether the account is an administrator.

        Returns:
            bool: ``True`` only for the admin role.

        Notes:
            Compared by identity rather than by rank: admin is the highest
            role, so the two agree today, but an identity check keeps the
            meaning exact if a higher role is ever added.
        """
        return self.role is UserRole.ADMIN

    def owns_hca(self, hca_id: str) -> bool:
        """Return whether the account may read a given assistant's planning.

        Args:
            hca_id (str): The assistant whose planning is being requested.

        Returns:
            bool: ``True`` when the account is a manager or admin, or when it
            is the assistant's own account.

        Notes:
            - This is the row-level rule behind "an assistant cannot see another
              assistant's planning". It lives on the model so every caller
              answers the question the same way.
            - **The staff test is positive, not "not an assistant".** It read
              ``role is not HCA`` until the customer role existed, at which point
              that spelling silently handed every household's planning to every
              customer — the blanket ``True`` was written when the only roles
              left were manager and admin. A role added later must not inherit
              access by not being mentioned.
        """
        if self.role is UserRole.CUSTOMER:
            return False
        if self.role is not UserRole.HCA:
            return True
        return self.hca_id is not None and self.hca_id == hca_id

    def owns_customer(self, customer_id: str) -> bool:
        """Return whether the account may read a given customer's records.

        Args:
            customer_id (str): The household whose records are being requested.

        Returns:
            bool: ``True`` for the household's own account, and for staff.

        Notes:
            - The mirror of :meth:`owns_hca`, and the row-level rule behind "a
              customer sees only their own file". Staff are answered ``True``
              because the manager screens already list every household; this
              method is not what gates them, their route guards are.
            - A customer with no link is ``False`` rather than an error. The
              model refuses to build one — see :meth:`check_customer_link` — so
              this arm is unreachable, and it is written the closed way so that
              if it ever becomes reachable it fails shut.
        """
        if self.role is not UserRole.CUSTOMER:
            return True
        return self.customer_id is not None and self.customer_id == customer_id
