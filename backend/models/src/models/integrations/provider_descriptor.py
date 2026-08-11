from __future__ import annotations

# Standard library imports
from typing import ClassVar, List, Optional, Sequence, Tuple, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import EInvoicingProvider, TransmissionKind
from models.integrations.exceptions import (
    MTProviderDescriptorInvalidCoverage,
    MTProviderDescriptorInvalidFields,
    MTProviderDescriptorInvalidName,
    MTProviderDescriptorInvalidProvider,
    MTProviderDescriptorInvalidUrl,
    MTProviderDescriptorInvalidVerified,
)
from models.integrations.integration_credentials import IntegrationCredentials


class ProviderDescriptor(BaseModel):
    """What is true of a platform for everybody, rather than for one agency.

    Attributes:
        MAX_NAME_LENGTH (ClassVar[int]): Longest accepted display name.
        HTTPS (ClassVar[str]): The only scheme a published address may use.
        REQUIRED_ALWAYS (ClassVar[str]): The field every platform must ask for.
        provider (EInvoicingProvider): The platform this describes.
        name (str): What the platform is called, as it spells itself.
        home_url (str): The platform's own site.
        documentation_url (str): Where its API is documented.
        coverage (Tuple[TransmissionKind, ...]): What it can be asked to send.
        required_fields (Tuple[str, ...]): Which credential fields it needs.
        documentation_verified (bool): Whether its API docs were read directly.

    Notes:
        - **The catalogue is a model rather than a TypeScript constant** so that
          one statement of a vendor fact serves the gallery, the enable dialog
          and the transmission service. A display name duplicated into the
          front-end is a display name that goes stale in one of the two places.
        - ``coverage`` is what the gallery's tabs filter on **and** what the
          transmission service checks before handing over an invoice. A platform
          that cannot reach Chorus Pro must refuse a public body's invoice
          rather than send it somewhere that will silently drop it, and this is
          the field that makes refusing possible.
        - ``required_fields`` drives the dialog: it is why enabling Storecove
          asks for a legal-entity reference and enabling Iopole does not. It is
          validated against
          :class:`~models.integrations.integration_credentials.IntegrationCredentials`
          so a platform cannot declare a field the credentials have no room for
          — which would render an input whose value goes nowhere.
        - ``documentation_verified`` is unusual and deliberate. Three of the four
          platforms have documentation that was read directly; Iopole's renders
          client-side and its servers return malformed headers, so its connector
          is written to documented *shape* rather than to something anybody
          confirmed. A screen offering all four as equals would be lying by
          omission, so the flag rides with the descriptor and the card says so.
    """

    MAX_NAME_LENGTH: ClassVar[int] = 64
    HTTPS: ClassVar[str] = "https://"
    REQUIRED_ALWAYS: ClassVar[str] = "api_key"

    provider: EInvoicingProvider = Field(description="The platform this describes.")
    name: str = Field(description="What the platform is called.")
    home_url: str = Field(description="The platform's own site.")
    documentation_url: str = Field(description="Where its API is documented.")
    coverage: Tuple[TransmissionKind, ...] = Field(
        description="What it can be asked to send.",
    )
    required_fields: Tuple[str, ...] = Field(
        default=(REQUIRED_ALWAYS,),
        description="Which credential fields it needs.",
    )
    documentation_verified: bool = Field(
        default=False,
        description="Whether its API documentation was read directly.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("provider", mode="before")
    def validate_provider(
        cls, value: Optional[Union[str, EInvoicingProvider]]
    ) -> EInvoicingProvider:
        """Validates that ``provider`` names a supported platform.

        Args:
            value (Optional[Union[str, EInvoicingProvider]]): Raw platform.

        Returns:
            EInvoicingProvider: The coerced platform.

        Raises:
            MTProviderDescriptorInvalidProvider: If ``value`` is missing or is
                not a supported platform.
        """
        if value is None:
            raise MTProviderDescriptorInvalidProvider(
                "Invalid provider: a platform is required."
            )
        if isinstance(value, EInvoicingProvider):
            return value
        try:
            return EInvoicingProvider(value)
        except ValueError:
            raise MTProviderDescriptorInvalidProvider(
                f"Invalid provider: {value!r}. Must be one of: "
                f"{', '.join(EInvoicingProvider.values())}."
            ) from None

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a usable display name.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTProviderDescriptorInvalidName: If ``value`` is not a non-empty
                string of bounded length.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTProviderDescriptorInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        stripped = value.strip()
        if len(stripped) > cls.MAX_NAME_LENGTH:
            raise MTProviderDescriptorInvalidName(
                f"Invalid name: longer than {cls.MAX_NAME_LENGTH} characters."
            )
        return stripped

    @field_validator("home_url", "documentation_url", mode="before")
    def validate_urls(cls, value: Optional[str]) -> str:
        """Validates that a published address is absolute HTTPS.

        Args:
            value (Optional[str]): Raw address.

        Returns:
            str: The stripped address.

        Raises:
            MTProviderDescriptorInvalidUrl: If ``value`` is not an absolute
                HTTPS address.

        Notes:
            These are rendered as links on a card a manager clicks. An address
            that is not absolute would resolve against this application's own
            host and open a page that does not exist.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTProviderDescriptorInvalidUrl(
                f"Invalid url: {value!r}. Must be a non-empty string."
            )
        stripped = value.strip()
        if not stripped.startswith(cls.HTTPS):
            raise MTProviderDescriptorInvalidUrl(
                f"Invalid url: {stripped!r}. Must start with {cls.HTTPS!r}."
            )
        return stripped

    @field_validator("coverage", mode="before")
    def validate_coverage(
        cls, value: Optional[Sequence[Union[str, TransmissionKind]]]
    ) -> Tuple[TransmissionKind, ...]:
        """Validates that the declared coverage is a non-empty set of kinds.

        Args:
            value (Optional[Sequence[Union[str, TransmissionKind]]]): Raw
                coverage.

        Returns:
            Tuple[TransmissionKind, ...]: The coerced kinds, deduplicated and
            in the order declared.

        Raises:
            MTProviderDescriptorInvalidCoverage: If ``value`` is missing, empty,
                or names something that is not a transmission kind.

        Notes:
            - Empty is refused. Coverage decides which tab a card appears under
              and whether an invoice may be handed over, so a platform covering
              nothing would render everywhere and then refuse everything.
            - Order is kept rather than sorted, because it is the order the tabs
              are written in and the order a card lists what a platform does.
        """
        if value is None or isinstance(value, (str, bytes)):
            raise MTProviderDescriptorInvalidCoverage(
                f"Invalid coverage: {value!r}. "  # noqa: E501
                "Must be a list of transmission kinds."
            )
        try:
            declared: List[Union[str, TransmissionKind]] = list(value)
        except TypeError:
            raise MTProviderDescriptorInvalidCoverage(
                f"Invalid coverage: {value!r}. " # noqa: E501
                "Must be a list of transmission kinds."
            ) from None
        if not declared:
            raise MTProviderDescriptorInvalidCoverage(
                "Invalid coverage: a platform must cover at least one kind."
            )
        kinds: List[TransmissionKind] = []
        for entry in declared:
            if isinstance(entry, TransmissionKind):
                coerced = entry
            else:
                try:
                    coerced = TransmissionKind(entry)
                except (ValueError, TypeError):
                    raise MTProviderDescriptorInvalidCoverage(
                        f"Invalid coverage: {entry!r}. Must be one of: "
                        f"{', '.join(TransmissionKind.values())}."
                    ) from None
            if coerced not in kinds:
                kinds.append(coerced)
        return tuple(kinds)

    @field_validator("required_fields", mode="before")
    def validate_required_fields(
        cls, value: Optional[Sequence[str]]
    ) -> Tuple[str, ...]:
        """Validates that the declared credential fields exist and include the key.

        Args:
            value (Optional[Sequence[str]]): Raw field names.

        Returns:
            Tuple[str, ...]: The field names, deduplicated, always including the
            API key.

        Raises:
            MTProviderDescriptorInvalidFields: If ``value`` names something that
                is not a credential field.

        Notes:
            - Checked against
              :class:`~models.integrations.integration_credentials.IntegrationCredentials`
              rather than against a list written here, so the two cannot drift: a
              platform declaring a field the credentials have no room for would
              render a dialog input whose value goes nowhere.
            - The API key is added when omitted rather than demanded, because
              every platform authenticates on one and a descriptor that forgot to
              say so is a typo rather than a different kind of platform.
        """
        known = set(IntegrationCredentials.model_fields)
        if value is None:
            return (cls.REQUIRED_ALWAYS,)
        if isinstance(value, (str, bytes)):
            raise MTProviderDescriptorInvalidFields(
                f"Invalid required_fields: {value!r}. " # noqa: E501
                "Must be a list of names."
            )
        try:
            declared = list(value)
        except TypeError:
            raise MTProviderDescriptorInvalidFields(
                f"Invalid required_fields: {value!r}. " # noqa: E501
                "Must be a list of names."
            ) from None
        names: List[str] = [cls.REQUIRED_ALWAYS]
        for entry in declared:
            if not isinstance(entry, str) or entry not in known:
                raise MTProviderDescriptorInvalidFields(
                    f"Invalid required_fields: {entry!r}. Must be one of: "
                    f"{', '.join(sorted(known))}."
                )
            if entry not in names:
                names.append(entry)
        return tuple(names)

    @field_validator("documentation_verified", mode="before")
    def validate_documentation_verified(cls, value: Optional[bool]) -> bool:
        """Validates that the verified flag is a boolean.

        Args:
            value (Optional[bool]): Raw flag.

        Returns:
            bool: The flag; ``None`` reads as unverified.

        Raises:
            MTProviderDescriptorInvalidVerified: If ``value`` is neither
                ``None`` nor a boolean.

        Notes:
            ``None`` reads as *unverified* rather than verified. The flag is a
            claim about diligence, and the safe direction for a missing claim is
            the one that under-promises.
        """
        if value is None:
            return False
        if not isinstance(value, bool):
            raise MTProviderDescriptorInvalidVerified(
                f"Invalid documentation_verified: {value!r}. Must be a boolean."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def covers(self, kind: TransmissionKind) -> bool:
        """Return whether this platform can be asked to send a kind of message.

        Args:
            kind (TransmissionKind): What needs transmitting.

        Returns:
            bool: ``True`` when the platform covers it.

        Notes:
            Asked before an invoice is handed over, not after it is refused.
            A platform that cannot reach Chorus Pro answers a public body's
            invoice with a 404 or, worse, a 200 that goes nowhere — neither of
            which is distinguishable from success without this check.
        """
        return kind in self.coverage

    def requires(self, field_name: str) -> bool:
        """Return whether the enable dialog must ask for a credential field.

        Args:
            field_name (str): The credential field in question.

        Returns:
            bool: ``True`` when this platform needs it.
        """
        return field_name in self.required_fields
