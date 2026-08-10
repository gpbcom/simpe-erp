from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Optional, Tuple

# First-party imports
from models.auth.user import User
from models.companies.company import Company
from models.configuration.auth_config import AuthConfig
from models.enums import EventRoutingKey, UserRole
from service.auth.auth import AuthService
from service.companies.companies import CompanyService
from service.companies.exceptions import MTCompanyRegistrationDisabled
from service.messaging.publisher import EventPublisher


class CompanyRegistrationService:
    """Founds an agency and its first administrator in one step.

    Attributes:
        companies (CompanyService): The company service.
        auth (AuthService): The authentication service, for the account.
        publisher (EventPublisher): Announces the agency to the workers.
        config (AuthConfig): Authentication settings, for the feature flag.
        logger (Logger): Logger for registration operations.

    Notes:
        - **The company is always new, and that is the security argument.**
          This is the one unauthenticated route that grants an administrator
          role, so the role has to be over something the caller has just
          brought into existence. There is no parameter naming an existing
          company, and adding one would turn founding an agency into taking
          over somebody else's.
        - **Off unless the deployment turns it on.** A company is not yet a
          tenancy boundary: customers, quotes and plannings are global and the
          administrator gate does not look at the company, so an administrator
          minted here can read every agency's records rather than only their
          own. The flag is what keeps that from being the default posture of
          every deployment; see
          :attr:`~models.configuration.auth_config.AuthConfig.allow_company_registration`.
        - The company is written **before** the account, and the account names
          it. If the account fails — a taken address, most likely — the request
          fails as a whole and the transaction takes the company back out with
          it, rather than leaving an agency nobody can sign in to. That
          rollback is the request's, not this class's: the session commits on a
          successful response and rolls back otherwise.
    """

    def __init__(
        self,
        companies: CompanyService,
        auth: AuthService,
        publisher: EventPublisher,
        config: AuthConfig,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            companies (CompanyService): The company service.
            auth (AuthService): The authentication service.
            publisher (EventPublisher): The broker publisher.
            config (AuthConfig): Authentication settings.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.companies = companies
        self.auth = auth
        self.publisher = publisher
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("CompanyRegistrationService created.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_open(self) -> bool:
        """Return whether founding an agency is currently allowed.

        Returns:
            bool: ``True`` when the deployment has opted in.
        """
        return self.config.allow_company_registration

    async def register(
        self,
        company_name: str,
        full_name: str,
        email: str,
        password: str,
        registration_number: Optional[str] = None,
    ) -> Tuple[Company, User]:
        """Create an agency and the administrator account that founded it.

        Args:
            company_name (str): The trading name of the agency.
            full_name (str): The founder's display name.
            email (str): The founder's sign-in address.
            password (str): The founder's plaintext password.
            registration_number (Optional[str]): The agency's registration
                number, if it has one yet.

        Returns:
            Tuple[Company, User]: The agency, and its administrator.

        Raises:
            MTCompanyRegistrationDisabled: If the deployment has not opted in.
            MTCompanyNameTaken: If another agency already trades under the name.
            MTAuthEmailAlreadyRegistered: If the address is already in use.

        Notes:
            - The new agency starts **accepting applications**. Founding one and
              then discovering that no assistant can apply to it would make the
              first thing a founder does an obscure settings change.
            - The role is :attr:`~models.enums.UserRole.ADMIN` and is written
              here, not taken from any argument. There is no parameter for it
              precisely so that no caller can supply one.
            - ``must_change_password`` is left false: the founder chose this
              password a moment ago, and demanding they replace it before the
              first screen would be a password change with nothing to protect
              against.
        """
        if not self.is_open():
            self.logger.warning(
                "Refused to found %r for %s: company registration is disabled.",
                company_name,
                email,
            )
            raise MTCompanyRegistrationDisabled(
                "Founding an agency is not enabled on this deployment."
            )
        self.logger.info("Founding agency %r for %s.", company_name, email)
        company = await self.companies.create(
            Company(
                name=company_name,
                registration_number=registration_number,
                contact_email=email,
                is_accepting_applications=True,
            )
        )
        administrator = await self.auth.register(
            email=email,
            full_name=full_name,
            password=password,
            role=UserRole.ADMIN,
            company_id=company.id,
        )
        announced = await self.publisher.publish(
            EventRoutingKey.COMPANY_CREATED,
            company.id or "",
            {"company_id": company.id, "name": company.name},
        )
        if not announced:
            self.logger.warning(
                "Agency %s was founded but could not be announced; its queues "
                "will be bound the next time a worker starts.",
                company.id,
            )
        self.logger.info(
            "Founded agency %s with administrator %s.",
            company.id,
            administrator.id,
        )
        return company, administrator
