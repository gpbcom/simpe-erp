from __future__ import annotations

# Standard library imports
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Standard library imports
import re
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator

from models.companies.company_choice import CompanyChoice

# First-party imports
from models.companies.exceptions import (
    MTCompanyInvalidBic,
    MTCompanyInvalidDate,
    MTCompanyInvalidEmail,
    MTCompanyInvalidIban,
    MTCompanyInvalidId,
    MTCompanyInvalidIsAcceptingApplications,
    MTCompanyInvalidLegalForm,
    MTCompanyInvalidLogoUrl,
    MTCompanyInvalidName,
    MTCompanyInvalidPhoneNumber,
    MTCompanyInvalidRcsNumber,
    MTCompanyInvalidRegistrationNumber,
    MTCompanyInvalidShareCapital,
    MTCompanyInvalidVatNumber,
)
from models.geo.postal_address import PostalAddress


class Company(BaseModel):
    """A care agency an assistant can apply to work for.

    Attributes:
        MAX_NAME_LENGTH (ClassVar[int]): Longest accepted trading name.
        MAX_REGISTRATION_LENGTH (ClassVar[int]): Longest accepted registration
            number.
        id (Optional[str]): Identifier, populated on read from the store.
        name (str): Trading name, shown to an applicant choosing between
            agencies.
        registration_number (Optional[str]): The company's registration number.
        contact_email (Optional[EmailStr]): Where an applicant's questions go.
        address (Optional[PostalAddress]): The registered office.
        iban (Optional[str]): Account the agency is paid into.
        bic (Optional[str]): Bank identifier code of that account.
        logo_url (Optional[str]): URL of the agency's logo in the object store.
        is_accepting_applications (bool): Whether it appears on the public list
            an applicant chooses from.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - This exists because an assistant registering themselves has to say
          *which agency they are applying to*. Without it there is nobody to
          route the application to and nobody with standing to approve it.
        - **Only the name and the identifier are ever shown publicly.** The list
          an applicant picks from is served without a credential, so the address
          and contact details stay behind the authenticated routes — publishing
          a directory of agencies with their registered offices is not what
          "choose your employer" needs.
        - ``is_accepting_applications`` is how an agency stops appearing on that
          list without being deleted. A company with assistants and quotes cannot
          be removed, and hiding it is the only honest alternative.
        - The company is *not* a tenancy boundary. Customers, quotes and
          plannings are agency-wide, not scoped per company — see the note in the
          service layer. What a company scopes is who may approve whose
          application.
        - **The IBAN is the one field here nobody but an administrator reads in
          full.** It is stored whole, and the routes a manager can reach hand
          back :meth:`masked_iban` instead — see
          :class:`~models.schemas.responses.companies.company_view.CompanyView`.
          Masking at the boundary rather than in the column keeps the stored
          value usable for the one caller entitled to it.
    """

    MAX_NAME_LENGTH: ClassVar[int] = 200
    MAX_REGISTRATION_LENGTH: ClassVar[int] = 64
    MAX_LEGAL_FORM_LENGTH: ClassVar[int] = 64
    MAX_RCS_LENGTH: ClassVar[int] = 64
    #: The longest IBAN any country issues.
    MAX_IBAN_LENGTH: ClassVar[int] = 34
    VAT_NUMBER_PATTERN: ClassVar[str] = r"^[A-Z]{2}[0-9A-Z]{2}[0-9]{9}$"
    IBAN_PATTERN: ClassVar[str] = r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$"
    BIC_PATTERN: ClassVar[str] = r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$"
    IBAN_VISIBLE_CHARACTERS: ClassVar[int] = 4
    IBAN_MASK_CHARACTER: ClassVar[str] = "•"
    LOGO_KEY_PREFIX: ClassVar[str] = "company-logos/"

    id: Optional[str] = Field(
        default=None, description="Identifier, assigned by the store."
    )
    name: str = Field(description="Trading name.")
    legal_form: Optional[str] = Field(
        default=None,
        description="Legal form, such as SARL, SAS or Association.",
    )
    share_capital: Optional[Decimal] = Field(
        default=None,
        description="Share capital, in euros.",
    )
    rcs_number: Optional[str] = Field(
        default=None,
        description="Trade-register entry, such as 'RCS Paris B 123 456 789'.",
    )
    vat_number: Optional[str] = Field(
        default=None,
        description="Intra-community VAT number, such as FR12345678901.",
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="Contact telephone number.",
    )
    registration_number: Optional[str] = Field(
        default=None, description="Company registration number."
    )
    contact_email: Optional[EmailStr] = Field(
        default=None, description="Where an applicant's questions go."
    )
    address: Optional[PostalAddress] = Field(
        default=None, description="The registered office."
    )
    iban: Optional[str] = Field(
        default=None,
        description="Account the agency is paid into, for SEPA transfers.",
    )
    bic: Optional[str] = Field(
        default=None,
        description="Bank identifier code of the account holding the IBAN.",
    )
    logo_url: Optional[str] = Field(
        default=None,
        description="URL of the agency's logo in the object store.",
    )
    is_accepting_applications: bool = Field(
        default=True, description="Whether it appears on the public list."
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Creation timestamp."
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last-update timestamp."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id``, when given, is a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is stored.

        Raises:
            MTCompanyInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a usable trading name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTCompanyInvalidName: If ``value`` is not a non-empty string within
                :attr:`MAX_NAME_LENGTH`.

        Notes:
            Required, because this is the one field an applicant sees. A
            company with no name is an unlabelled option in a list somebody has
            to choose from.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > cls.MAX_NAME_LENGTH:
            raise MTCompanyInvalidName(
                f"Invalid name: {len(trimmed)} characters. Must be at most "
                f"{cls.MAX_NAME_LENGTH}."
            )
        return trimmed

    @field_validator("registration_number", mode="before")
    def validate_registration_number(cls, value: Optional[str]) -> Optional[str]:  # noqa: E501
        """Validates that the registration number, when given, is usable.

        Args:
            value (Optional[str]): Raw registration-number value.

        Returns:
            Optional[str]: The upper-cased number, or ``None``.

        Raises:
            MTCompanyInvalidRegistrationNumber: If ``value`` is neither
                ``None`` nor a string of alphanumerics within
                :attr:`MAX_REGISTRATION_LENGTH`.

        Notes:
            Upper-cased and stripped of separators so that "123 456 789" and
            "123456789" are the same company. Registration numbers get typed by
            hand from letterheads, and the spacing varies by who is reading.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyInvalidRegistrationNumber(
                f"Invalid registration_number: {value!r}. Must be a string."
            )
        cleaned = value.replace(" ", "").replace("-", "").upper()
        if not cleaned:
            return None
        if not cleaned.isalnum():
            raise MTCompanyInvalidRegistrationNumber(
                f"Invalid registration_number: {value!r}. Must contain only "
                f"letters and digits."
            )
        if len(cleaned) > cls.MAX_REGISTRATION_LENGTH:
            raise MTCompanyInvalidRegistrationNumber(
                f"Invalid registration_number: {len(cleaned)} characters. Must "
                f"be at most {cls.MAX_REGISTRATION_LENGTH}."
            )
        return cleaned

    @field_validator("contact_email", mode="before")
    def validate_contact_email(cls, value: Optional[str]) -> Optional[str]:
        """Validates that the contact address, when given, is an address.

        Args:
            value (Optional[str]): Raw ``contact_email`` value.

        Returns:
            Optional[str]: The lower-cased address, or ``None``.

        Raises:
            MTCompanyInvalidEmail: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyInvalidEmail(
                f"Invalid contact_email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("is_accepting_applications", mode="before")
    def validate_is_accepting_applications(cls, value: Union[bool, None]) -> bool:  # noqa: E501
        """Validates that the open-to-applications flag is a boolean.

        Args:
            value (Union[bool, None]): Raw flag value.

        Returns:
            bool: The flag.

        Raises:
            MTCompanyInvalidIsAcceptingApplications: If ``value`` is neither
                ``None`` nor a boolean.

        Notes:
            Strings are refused rather than coerced. ``"false"`` is truthy, and
            a company that silently kept accepting applications after being
            told to stop would be discovered by the applications arriving.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTCompanyInvalidIsAcceptingApplications(
                f"Invalid is_accepting_applications: {value!r}. Must be a boolean."
            )
        return value

    @field_validator("created_at", "updated_at", mode="before")
    def validate_timestamps(
        cls, value: Union[datetime, str, None]
    ) -> Optional[datetime]:
        """Validates that a timestamp is a datetime.

        Args:
            value (Union[datetime, str, None]): Raw timestamp value.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTCompanyInvalidDate: If ``value`` is neither ``None`` nor a
                datetime or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTCompanyInvalidDate(
                    f"Invalid timestamp: {value!r}. Must be an ISO-8601 datetime."
                ) from None
        raise MTCompanyInvalidDate(f"Invalid timestamp: {value!r}. Must be a datetime.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_public_choice(self) -> CompanyChoice:
        """Return the company as an applicant is allowed to see it.

        Returns:
            CompanyChoice: Its identifier and name, and nothing else.

        Notes:
            The list an applicant chooses from is served without a credential.
            Returning the whole record there would publish a directory of every
            agency's registered office and contact address to anybody who asks.
        """
        return CompanyChoice(id=self.id if self.id else "", name=self.name)

    def masked_iban(self) -> Optional[str]:
        """Return the account number as somebody not entitled to it may see it.

        Returns:
            Optional[str]: The IBAN with its middle replaced by bullets, or
            ``None`` when no account is recorded.

        Notes:
            - The country code and the last four characters are kept, because
              those are what let an administrator recognise *which* account is on
              file without the reader being able to pay into it — the same trade
              a bank statement makes.
            - A number too short to mask on both ends is replaced entirely rather
              than partially. The validators make that unreachable, but a masking
              routine that quietly reveals more the shorter the input gets is the
              wrong shape to leave lying around.
        """
        if self.iban is None:
            return None
        visible = self.IBAN_VISIBLE_CHARACTERS
        if len(self.iban) <= visible * 2:
            return self.IBAN_MASK_CHARACTER * len(self.iban)
        hidden = self.IBAN_MASK_CHARACTER * (len(self.iban) - visible * 2)
        return f"{self.iban[:visible]}{hidden}{self.iban[-visible:]}"

    @field_validator("legal_form", "rcs_number", mode="before")
    def validate_printed_label(
        cls, value: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        """Validates a legal label that is only ever printed.

        Args:
            value (Optional[str]): Raw ``legal_form`` or ``rcs_number`` value.
            info (ValidationInfo): Names the field, so each raises its own
                exception.

        Returns:
            Optional[str]: The trimmed label, or ``None`` when blank.

        Raises:
            MTCompanyInvalidLegalForm: If the value is neither ``None`` nor a
                string within the accepted length.

        Notes:
            - Free text, not an enumeration. French home care is delivered by
              SARLs, SAS, associations, CCAS, mutuelles and sole traders alike,
              and a closed list would lock out a provider whose form nobody
              thought of — on a field the application only ever prints.
            - Blank becomes ``None`` rather than an empty string. The quote joins
              only the parts that are set, and an empty string would print a
              stray separator on a document a customer is asked to sign.
            - One rule, two exceptions. The check is identical for both
              fields, but the API's exception-to-status map is keyed on the
              class — so a rejected RCS entry has to say so rather than
              report itself as a bad legal form.
        """
        refuse = (
            MTCompanyInvalidRcsNumber
            if info.field_name == "rcs_number"
            else MTCompanyInvalidLegalForm
        )
        limit = (
            cls.MAX_RCS_LENGTH
            if info.field_name == "rcs_number"
            else cls.MAX_LEGAL_FORM_LENGTH
        )
        if value is None:
            return None
        if not isinstance(value, str):
            raise refuse(
                f"Invalid {info.field_name}: {value!r}. Must be a string or None."
            )
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > limit:
            raise refuse(
                f"Invalid {info.field_name}: {trimmed!r}. Must be at most "
                f"{limit} characters."
            )
        return trimmed

    @field_validator("share_capital", mode="before")
    def validate_share_capital(
        cls, value: Union[str, int, float, Decimal, None]
    ) -> Optional[Decimal]:
        """Validates that the share capital is a positive amount.

        Args:
            value (Union[str, int, float, Decimal, None]): Raw capital.

        Returns:
            Optional[Decimal]: The capital, or ``None`` when unset.

        Raises:
            MTCompanyInvalidShareCapital: If the value is neither ``None`` nor
                a positive number.

        Notes:
            - A :class:`~decimal.Decimal`, and built from the string form, so a
              capital of ``10000.50`` is exact rather than the binary
              approximation a float would carry onto a printed document.
            - Zero is refused. A company with no capital does not declare
              "0 €" on its papers, it declares nothing — which is ``None``.
        """
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTCompanyInvalidShareCapital(
                f"Invalid share_capital: {value!r}. Must be a number."
            ) from None
        if amount <= 0:
            raise MTCompanyInvalidShareCapital(
                f"Invalid share_capital: {amount!r}. Must be greater than zero."
            )
        return amount

    @field_validator("vat_number", mode="before")
    def validate_vat_number(cls, value: Optional[str]) -> Optional[str]:
        """Validates the intra-community VAT number.

        Args:
            value (Optional[str]): Raw ``vat_number`` value.

        Returns:
            Optional[str]: The number, upper-cased and stripped of spaces, or
            ``None``.

        Raises:
            MTCompanyInvalidVatNumber: If the value does not look like an
                intra-community VAT number.

        Notes:
            - Checked against a shape rather than merely stored. This number
              appears on every quote and invoice, and one with a digit missing
              is the kind of error nobody notices until an accountant does.
            - Spaces are removed and the letters upper-cased before the check, so
              ``fr 123 456 789 01`` and ``FR12345678901`` are the same number —
              which is how somebody reads it off a document to type it in.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyInvalidVatNumber(
                f"Invalid vat_number: {value!r}. Must be a string or None."
            )
        cleaned = value.replace(" ", "").upper()
        if not cleaned:
            return None
        if not re.match(cls.VAT_NUMBER_PATTERN, cleaned):
            raise MTCompanyInvalidVatNumber(
                f"Invalid vat_number: {value!r}. Must be a country code, a "
                f"two-character key and nine digits, such as FR12345678901."
            )
        return cleaned

    @field_validator("phone_number", mode="before")
    def validate_phone_number(cls, value: Optional[str]) -> Optional[str]:
        """Validates that the contact telephone number is usable.

        Args:
            value (Optional[str]): Raw ``phone_number`` value.

        Returns:
            Optional[str]: The trimmed number, or ``None`` when blank.

        Raises:
            MTCompanyInvalidPhoneNumber: If the value is neither ``None`` nor a
                string of plausible length.

        Notes:
            Deliberately looser than the assistant's ``PhoneNumber``. That one
            is dialled by the application; this one is printed on a quote, and
            an agency whose papers carry a switchboard number written
            "01 23 45 67 89 (poste 12)" should not be refused for it.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyInvalidPhoneNumber(
                f"Invalid phone_number: {value!r}. Must be a string or None."
            )
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > cls.MAX_REGISTRATION_LENGTH:
            raise MTCompanyInvalidPhoneNumber(
                f"Invalid phone_number: {trimmed!r}. Must be at most "
                f"{cls.MAX_REGISTRATION_LENGTH} characters."
            )
        return trimmed

    @field_validator("iban", mode="before")
    def validate_iban(cls, value: Optional[str]) -> Optional[str]:
        """Validates the account the agency is paid into.

        Args:
            value (Optional[str]): Raw ``iban`` value.

        Returns:
            Optional[str]: The number, upper-cased and stripped of spaces, or
            ``None`` when blank.

        Raises:
            MTCompanyInvalidIban: If the value is neither ``None`` nor an IBAN
                that satisfies both its shape and its check digits.

        Notes:
            - The **ISO 7064 mod-97 checksum is verified**, not just the shape.
              Two check digits exist precisely so that a transposed pair is
              caught where it is typed; skipping them would let a wrong account
              number reach a quote, where the error surfaces weeks later as a
              payment that never arrived rather than as a rejected form.
            - Spaces are removed before the check, so the grouped form printed on
              a bank statement and the unbroken form are the same number — which
              is how somebody reads one off a document to type it in.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyInvalidIban(
                f"Invalid iban: {value!r}. Must be a string or None."
            )
        cleaned = value.replace(" ", "").upper()
        if not cleaned:
            return None
        if len(cleaned) > cls.MAX_IBAN_LENGTH or not re.match(
            cls.IBAN_PATTERN, cleaned
        ):
            raise MTCompanyInvalidIban(
                f"Invalid iban: {value!r}. Must be a country code, two check "
                f"digits and up to {cls.MAX_IBAN_LENGTH - 4} more characters, "
                f"such as FR7630006000011234567890189."
            )
        rotated = cleaned[4:] + cleaned[:4]
        digits = "".join(
            str(ord(character) - 55) if character.isalpha() else character
            for character in rotated
        )
        if int(digits) % 97 != 1:
            raise MTCompanyInvalidIban(
                f"Invalid iban: {value!r}. Its check digits do not match the "
                f"account number; one character is probably wrong."
            )
        return cleaned

    @field_validator("bic", mode="before")
    def validate_bic(cls, value: Optional[str]) -> Optional[str]:
        """Validates the bank identifier code of the account.

        Args:
            value (Optional[str]): Raw ``bic`` value.

        Returns:
            Optional[str]: The code, upper-cased and stripped of spaces, or
            ``None`` when blank.

        Raises:
            MTCompanyInvalidBic: If the value is neither ``None`` nor an eight-
                or eleven-character bank identifier code.

        Notes:
            Optional even when an IBAN is set, and deliberately not made
            conditional on it. Inside SEPA the IBAN alone is enough to route a
            transfer, so demanding a BIC would refuse a complete answer for
            missing something the payment does not need.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyInvalidBic(
                f"Invalid bic: {value!r}. Must be a string or None."
            )
        cleaned = value.replace(" ", "").upper()
        if not cleaned:
            return None
        if not re.match(cls.BIC_PATTERN, cleaned):
            raise MTCompanyInvalidBic(
                f"Invalid bic: {value!r}. Must be eight or eleven characters, "
                f"such as BNPAFRPP or BNPAFRPPXXX."
            )
        return cleaned

    @field_validator("logo_url", mode="before")
    def validate_logo_url(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``logo_url`` points at a logo this application stored.

        Args:
            value (Optional[str]): Raw ``logo_url`` value.

        Returns:
            Optional[str]: The stripped URL, or ``None`` when blank.

        Raises:
            MTCompanyInvalidLogoUrl: If the value is neither ``None`` nor an
                ``http``/``https`` URL whose path lies under
                :attr:`LOGO_KEY_PREFIX`.

        Notes:
            - The same security rule as
              :meth:`~models.base.portrait_holder.PortraitHolder.validate_photo_url`,
              and it is duplicated rather than shared because that mixin owns a
              ``photo_url`` field a company has no use for. Requiring the prefix
              is what stops an arbitrary third-party URL being stored: the logo is
              rendered on every screen and on the quote, so a remote one would
              report every viewer to whoever hosts it, and the object store could
              not own the object it is later asked to remove.
            - Which *bucket* the URL belongs to cannot be checked here — the model
              has no access to configuration. The object store re-checks that
              before deleting, where getting it wrong would remove somebody
              else's object.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyInvalidLogoUrl(
                f"Invalid logo_url: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.startswith(("http://", "https://")):
            raise MTCompanyInvalidLogoUrl(
                f"Invalid logo_url: {stripped!r}. Must be an http or https URL."
            )
        if f"/{cls.LOGO_KEY_PREFIX}" not in stripped:
            raise MTCompanyInvalidLogoUrl(
                f"Invalid logo_url: {stripped!r}. Must point at a logo stored "
                f"by this application, under the {cls.LOGO_KEY_PREFIX!r} prefix."
            )
        return stripped
