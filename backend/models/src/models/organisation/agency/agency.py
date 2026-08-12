from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Tuple, Union

# Third-party imports
from pydantic import Field, field_serializer, field_validator, model_validator

# First-party imports
from models.enums import AgencyType
from models.geo.geo_point import GeoPoint
from models.geo.postal_address import PostalAddress
from models.organisation.agency.exceptions import (
    MTAgencyInvalidAddress,
    MTAgencyInvalidCompanyId,
    MTAgencyInvalidDate,
    MTAgencyInvalidId,
    MTAgencyInvalidName,
    MTAgencyInvalidType,
    MTAgencyLegalIdentityMisplaced,
)
from models.organisation.companies.company import Company


class Agency(Company):
    """One of the places a company operates from.

    Attributes:
        MAX_NAME_LENGTH (ClassVar[int]): Longest accepted site name.
        LEGAL_IDENTITY_FIELDS (ClassVar[Tuple[str, ...]]): The inherited fields
            that describe the *business* rather than the place.
        company_id (str): The company this site belongs to.
        agency_type (AgencyType): Whether it is the head office, a warehouse or
            an ordinary branch.

    Notes:
        - **A site extends the company rather than merely referring to one**,
          which is why this subclasses
          :class:`~models.organisation.companies.company.Company` and inherits
          every one of its attributes. The head office *is* where the business
          is registered: the SIRET, the legal form, the share capital, the VAT
          number and the account money is paid into are printed from it onto
          every quote and invoice. Declaring those fields again here would be a
          second copy free to disagree with the first, and reaching them through
          a join would mean the document renderer had to know which of two
          objects to ask.
        - **They mean something only on the head office**, and that is
          enforced — see :meth:`check_legal_identity`.
        - The **address is optional**, inherited as such.
          ``CompanyRegistrationService.register`` founds a company from a form
          that asks for no address, so the head office it creates alongside can
          have none either. The consequence is stated rather than hidden: a site
          with no coordinate cannot win a closest-team contest, and its teams
          are reachable only through the busyness tie-break.
        - The first site of a company is its head office and every later one
          defaults to a branch — but **neither rule lives here**. Both are
          questions about *other rows*, which a value cannot answer about
          itself; :class:`~service.organisation.agencies.AgencyService` owns
          them, and a partial unique index is what makes the singularity a
          database fact rather than a service's good intentions.
        - ``id``, ``name`` and the timestamps override the inherited validators
          **by method name**, so they replace them rather than stacking on top:
          a differently-named validator on the same field would run alongside
          the base's in an order nobody reading either could predict. They are
          overridden so a malformed *site* raises this model's own exception —
          the API's status map is keyed on the class.
    """

    MAX_NAME_LENGTH: ClassVar[int] = 200
    #: What belongs to the business rather than to the building. Read by the
    #: invariant below, so adding a legal field to ``Company`` is one line here
    #: rather than a check somebody forgets.
    LEGAL_IDENTITY_FIELDS: ClassVar[Tuple[str, ...]] = (
        "registration_number",
        "legal_form",
        "share_capital",
        "rcs_number",
        "vat_number",
        "sap_declaration_number",
        "iban",
        "bic",
    )

    company_id: str = Field(description="The company this site belongs to.")
    agency_type: AgencyType = Field(
        default=AgencyType.OFFICE, description="What the site is used for."
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
            MTAgencyInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTAgencyInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a usable site name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTAgencyInvalidName: If ``value`` is not a non-empty string within
                :attr:`MAX_NAME_LENGTH`.

        Notes:
            This is the site's name, not the company's — "Antenne Est" rather
            than the trading name — and it is the only field an operator picking
            a site sees. An empty one is an unlabelled option in a list somebody
            has to choose from.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAgencyInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > cls.MAX_NAME_LENGTH:
            raise MTAgencyInvalidName(
                f"Invalid name: {len(trimmed)} characters. Must be at most "
                f"{cls.MAX_NAME_LENGTH}."
            )
        return trimmed

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that the owning company is named.

        Args:
            value (Optional[str]): Raw ``company_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTAgencyInvalidCompanyId: If ``value`` is not a non-empty string.

        Notes:
            Required, never optional. A site belonging to no company is covered
            by no scoping and appears on no list, so the state is refused rather
            than stored and puzzled over later — the same reasoning that made
            ``company_id`` required on an account and on an assistant.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAgencyInvalidCompanyId(
                f"Invalid company_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("agency_type", mode="before")
    def validate_agency_type(cls, value: Union[AgencyType, str, None]) -> AgencyType:
        """Validates that ``agency_type`` names a known kind of site.

        Args:
            value (Union[AgencyType, str, None]): Raw ``agency_type`` value.

        Returns:
            AgencyType: The type, defaulting to :attr:`AgencyType.OFFICE`.

        Raises:
            MTAgencyInvalidType: If ``value`` is a value the enumeration does
                not carry.

        Notes:
            ``None`` reads as a branch office rather than as an error, because
            that is what a site created after the first one is. The head office
            is decided by the service counting the company's existing sites, so
            a payload that says nothing gets the safe answer rather than the
            privileged one.
        """
        if value is None:
            return AgencyType.OFFICE
        if isinstance(value, AgencyType):
            return value
        if isinstance(value, str):
            try:
                return AgencyType(value)
            except ValueError:
                raise MTAgencyInvalidType(
                    f"Invalid agency_type: {value!r}. Must be one of "
                    f"{AgencyType.values()}."
                ) from None
        raise MTAgencyInvalidType(
            f"Invalid agency_type: {value!r}. Must be one of {AgencyType.values()}."
        )

    @field_validator("address", mode="before")
    def validate_address(
        cls, value: Union[PostalAddress, dict, None]
    ) -> Optional[PostalAddress]:
        """Validates that the address, when given, is a postal address.

        Args:
            value (Union[PostalAddress, dict, None]): Raw ``address`` value.

        Returns:
            Optional[PostalAddress]: The address, or ``None`` when the site has
            none recorded.

        Raises:
            MTAgencyInvalidAddress: If ``value`` is neither ``None`` nor
                something a :class:`PostalAddress` can be built from.

        Notes:
            The nested model's own validators run underneath this one, so a
            malformed street or postal code still raises its own exception. What
            this adds is the refusal of a value that is not an address at all,
            which would otherwise surface as a raw Pydantic error the API's
            exception map has no row for.
        """
        if value is None:
            return None
        if isinstance(value, PostalAddress):
            return value
        if isinstance(value, dict):
            return PostalAddress(**value)
        raise MTAgencyInvalidAddress(
            f"Invalid address: {value!r}. Must be a postal address or None."
        )

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
            MTAgencyInvalidDate: If ``value`` is neither ``None`` nor a datetime
                or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTAgencyInvalidDate(
                    f"Invalid timestamp: {value!r}. Must be an ISO-8601 datetime."
                ) from None
        raise MTAgencyInvalidDate(f"Invalid timestamp: {value!r}. Must be a datetime.")

    @field_serializer("created_at", "updated_at")
    def serialize_timestamps(self, value: Optional[datetime]) -> Optional[str]:
        """Serialise a timestamp as an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialise.

        Returns:
            Optional[str]: The ISO-8601 form, or ``None``.
        """
        return value.isoformat() if value else None

    @model_validator(mode="after")
    def check_legal_identity(self) -> Agency:
        """Keep the business's identity on the head office and nowhere else.

        Returns:
            Agency: The validated site.

        Raises:
            MTAgencyLegalIdentityMisplaced: If a site that is not the head
                office carries any of :attr:`LEGAL_IDENTITY_FIELDS`.

        Notes:
            - **Stated as a prohibition on the branches rather than as a
              requirement on the head office**, and the asymmetry is the point.
              Every one of these fields is optional on a company — an agency
              that has not filled in its RCS entry prints without it — so "the
              head office must have them all" is a rule no existing row
              satisfies. Validation runs on the way *out* of the database as
              well as in, so such a rule would make a perfectly good stored site
              unreadable rather than catching anything.
            - What can be enforced, and matters more, is the other direction: a
              warehouse carrying its own SIRET and its own IBAN would print two
              different companies on two quotes from one agency, and route two
              different bank accounts on two invoices. There is exactly one
              legal entity, and exactly one place it is registered.
            - ``logo_url``, ``contact_email``, ``phone_number``, ``address`` and
              ``is_accepting_applications`` are deliberately **not** in the
              list. A branch has its own telephone number and its own street,
              and those are facts about the place rather than about the
              business.
        """
        if self.agency_type.is_headquarters():
            return self
        carried = [
            field
            for field in self.LEGAL_IDENTITY_FIELDS
            if getattr(self, field) is not None
        ]
        if carried:
            raise MTAgencyLegalIdentityMisplaced(
                f"A {self.agency_type.value} site cannot carry "
                f"{', '.join(carried)}: the legal identity of the business "
                f"belongs to the head office, and only one site may hold it."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_headquarters(self) -> bool:
        """Return whether this site is the company's head office.

        Returns:
            bool: ``True`` when the type is :attr:`AgencyType.HQ`.
        """
        return self.agency_type.is_headquarters()

    def holds_legal_identity(self) -> bool:
        """Return whether the business's identity is recorded on this site.

        Returns:
            bool: ``True`` when at least one of
            :attr:`LEGAL_IDENTITY_FIELDS` is set.

        Notes:
            Asked by the service after it copies the company's identity onto a
            new head office, so a head office that has none of it is reported at
            ``WARNING`` rather than discovered when a quote prints without a
            SIRET. It is not a validation rule, for the reason
            :meth:`check_legal_identity` gives.
        """
        return any(
            getattr(self, field) is not None for field in self.LEGAL_IDENTITY_FIELDS
        )

    def coordinate(self) -> Optional[GeoPoint]:
        """Return where the site is, as a point the distance rule can use.

        Returns:
            Optional[GeoPoint]: The resolved point, or ``None`` when the site
            has no address or its address never geocoded.

        Notes:
            ``None`` is a real answer rather than an error. A site whose address
            Nominatim could not resolve still exists, still has people and still
            has teams; what it cannot do is win a *closest* contest, and the
            attribution rule says so explicitly instead of treating an
            unresolved address as a distance of zero — which would send every
            quote in the company to it.
        """
        if self.address is None:
            return None
        return self.address.to_geo_point()
