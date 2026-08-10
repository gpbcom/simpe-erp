from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Type

# Third-party imports
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

# First-party imports
from models.base.exceptions import (
    MTInvalidEntityFilterException,
    MTInvalidPersonException,
)
from models.auth.exceptions import (
    MTInvalidAccessTokenException,
    MTInvalidUserException,
)
from models.catalog.exceptions import (
    MTInvalidCertificationTypeException,
    MTInvalidSkillTypeException,
    MTInvalidInterventionTypeException,
)
from models.companies.exceptions import MTInvalidCompanyException
from models.configuration.exceptions import (
    MTInvalidAppConfigException,
    MTInvalidAuthConfigException,
    MTInvalidDatabaseConfigException,
    MTInvalidEmailConfigException,
    MTInvalidGeocodingConfigException,
    MTInvalidHolidaySurchargeException,
    MTInvalidObservabilityConfigException,
    MTInvalidPlanningConfigException,
    MTInvalidPricingConfigException,
    MTInvalidRabbitMqConfigException,
    MTInvalidS3ConfigException,
    MTInvalidServerConfigException,
    MTInvalidWebhookConfigException,
)
from models.exceptions.enum_exceptions import MTInvalidEnumException
from models.geo.exceptions import (
    MTInvalidGeoPointException,
    MTInvalidPostalAddressException,
)
from models.messaging.exceptions import MTInvalidEventEnvelopeException
from models.notifications.exceptions import MTInvalidNotificationException
from models.people.customer.exceptions import MTInvalidCustomerException
from models.people.hca.exceptions import (
    MTInvalidAvailabilitySlotException,
    MTInvalidCertificationException,
    MTInvalidDrivingLicenseException,
    MTInvalidHcaException,
    MTInvalidSkillException,
)
from models.people.hca_application.exceptions import MTInvalidHcaApplicationException
from models.planning.hca_planning.exceptions import MTInvalidHcaPlanningException
from models.planning.intervention.exceptions import (
    MTInvalidInterventionException,
    MTInvalidInterventionRequirementException,
)
from models.planning.planning_run.exceptions import (
    MTInvalidPlanningRunException,
    MTInvalidSuggestedSlotException,
    MTInvalidUnplacedQuoteException,
    MTInvalidUnplacedRequirementException,
)
from models.quoting.exceptions import (
    MTInvalidQuoteException,
    MTInvalidQuoteLineException,
    MTInvalidQuoteTypeWeekAggregateException,
)
from models.schemas.exceptions import (
    MTInvalidCertificationTypeUpdateRequestException,
    MTInvalidSkillCreateRequestException,
    MTInvalidSkillTypeUpdateRequestException,
    MTInvalidAccountUpdateRequestException,
    MTInvalidCompanyProfileUpdateRequestException,
    MTInvalidCompanyViewException,
    MTInvalidInterventionTypeChangeRequestException,
    MTInvalidInterventionTypeUpdateRequestException,
    MTInvalidQuoteCreateRequestException,
    MTInvalidQuoteHeaderRequestException,
    MTInvalidQuoteInterruptionRequestException,
    MTInvalidQuoteLinesRequestException,
    MTInvalidQuoteRescheduleRequestException,
    MTInvalidActiveUpdateRequestException,
    MTInvalidApplicationDecisionRequestException,
    MTInvalidCompanyRegistrationRequestException,
    MTInvalidPricingRulesResponseException,
    MTInvalidEmailDispatchResponseException,
    MTInvalidEmploymentUpdateRequestException,
    MTInvalidHcaApplicationRequestException,
    MTInvalidHcaProfileUpdateRequestException,
    MTInvalidHcaResponseException,
    MTInvalidWorkingDaysRequestException,
    MTInvalidHealthResponseException,
    MTInvalidLoginRequestException,
    MTInvalidPasswordChangeRequestException,
    MTInvalidPhotoConstraintsResponseException,
    MTInvalidPlanningCompletedRequestException,
    MTInvalidPlanningSettingsRequestException,
    MTInvalidReadinessResponseException,
    MTInvalidRegisterRequestException,
    MTInvalidCustomerFilterException,
    MTInvalidRoleUpdateRequestException,
    MTInvalidStaffAccountRequestException,
    MTInvalidStatusUpdateRequestException,
    MTInvalidTemporaryCredentialsResponseException,
    MTInvalidUserResponseException,
)
from models.settings.exceptions import MTInvalidPlanningSettingsException
from service.auth.exceptions import (
    MTAuthEmailAlreadyRegistered,
    MTAuthHcaLinkRequired,
    MTAuthInvalidCredentials,
    MTAuthInvalidToken,
    MTAuthLastAdmin,
    MTAuthMissingSecret,
    MTAuthPasswordChangeRequired,
    MTAuthSamePassword,
    MTAuthUnknownAccount,
    MTAuthUnknownHca,
    MTAuthUserInactive,
    MTInvalidAuthException,
)
from service.companies.exceptions import (
    MTCompanyLogoStorageUnavailable,
    MTCompanyNameTaken,
    MTCompanyNotAcceptingApplications,
    MTCompanyNotEmpty,
    MTCompanyNotFound,
    MTCompanyRegistrationDisabled,
    MTInvalidCompanyServiceException,
)
from service.certifications.exceptions import (
    MTCertificationTypeAlreadyExists,
    MTCertificationTypeInUse,
    MTCertificationTypeNotFound,
    MTCertificationTypeUnknownCode,
    MTInvalidCertificationCatalogException,
)
from service.skills.exceptions import (
    MTInvalidSkillCatalogException,
    MTSkillTypeAlreadyExists,
    MTSkillTypeInUse,
    MTSkillTypeNotFound,
    MTSkillTypeUnknownCode,
)
from service.customers.exceptions import (
    MTCustomerHasQuotes,
    MTCustomerNotFound,
    MTCustomerNotPromotable,
    MTInvalidCustomerServiceException,
)
from service.emails.exceptions import (
    MTEmailDeliveryFailed,
    MTEmailNoRecipient,
    MTEmailNotConfigured,
    MTInvalidEmailException,
)
from service.hcas.exceptions import (
    MTApplicationAlreadyDecided,
    MTApplicationForbidden,
    MTApplicationNotFound,
    MTAvailabilitySlotNotFound,
    MTSkillNotFound,
    MTDuplicateApplication,
    MTHcaForbidden,
    MTHcaHasAccount,
    MTHcaNotFound,
    MTInvalidHcaServiceException,
)
from service.intervention_types.exceptions import (
    MTInterventionTypeAlreadyExists,
    MTInterventionTypeNotFound,
    MTInvalidInterventionTypeCatalogException,
)
from service.messaging.exceptions import MTInvalidMessagingException
from service.planning.exceptions import (
    MTInvalidPlanningException,
    MTInterventionNotFound,
    MTInterventionNotQuoted,
    MTPlanningForbidden,
    MTPlanningInfeasible,
    MTPlanningPeriodTooLong,
    MTPlanningRunNotFound,
    MTPlanningSettingsUnavailable,
)
from service.quotes.exceptions import (
    MTInvalidPricingException,
    MTPricingUnknownInterventionType,
    MTQuoteForbidden,
    MTQuoteLineNotFound,
    MTQuoteNotEditable,
    MTQuoteNotFound,
    MTQuoteNotPriced,
)
from storage.db.exceptions import MTInvalidDatabaseConnectionException
from storage.mappers.exceptions import MTInvalidMapperException
from storage.s3.exceptions import (
    MTInvalidS3StorageException,
    MTS3BucketUnavailable,
    MTS3EmptyPayload,
    MTS3PayloadTooLarge,
    MTS3UnsupportedContentType,
    MTS3UploadFailed,
)


class ExceptionHandlers:
    """Turns every domain exception into the HTTP answer it deserves.

    Attributes:
        STATUS_BY_EXCEPTION (ClassVar[Dict[Type[Exception], int]]): The status
            each exception answers with.
        DETAIL_BY_EXCEPTION (ClassVar[Dict[Type[Exception], str]]): Replacement
            messages for the failures whose own text must not reach a client.
        HEADERS_BY_EXCEPTION (ClassVar[Dict[Type[Exception], Dict[str, str]]]):
            Extra response headers a given failure must carry.
        UNEXPECTED_DETAIL (ClassVar[str]): The message an unforeseen failure
            answers with.
        logger (Logger): Logger for rejected requests.

    Notes:
        - The endpoints raise nothing themselves: a service raises its own
          ``MT*`` exception and it travels untouched to here. That is what this
          class is for — the same failure used to be caught, logged and
          translated once per endpoint, so ``MTQuoteNotFound`` was written out
          six times and could disagree with itself in any one of them.
        - The table is the contract. Adding a service exception without adding
          a row here answers ``500``, which is the loud failure mode rather
          than the silent one.
        - Lookup walks the exception's ancestry, so registering a family's base
          class covers every future member of it, and a subclass may override
          its parent's status by having its own row.
        - Two failures answer with a message that is not their own: a missing
          signing secret and an unreachable bucket both name infrastructure,
          and telling a caller which piece is down invites them to probe it.
          Both are logged in full.
        - This is **not** the middleware's exception handling. Authentication
          runs above the router, outside the stack these handlers live in, so
          :class:`~api.middleware.auth_middleware.AuthMiddleware` answers its
          own failures and cannot delegate them here.
    """

    STATUS_BY_EXCEPTION: ClassVar[Dict[Type[Exception], int]] = {
        # Authentication and accounts
        MTAuthInvalidCredentials: status.HTTP_401_UNAUTHORIZED,
        MTAuthInvalidToken: status.HTTP_401_UNAUTHORIZED,
        MTAuthUserInactive: status.HTTP_403_FORBIDDEN,
        MTAuthEmailAlreadyRegistered: status.HTTP_409_CONFLICT,
        MTAuthLastAdmin: status.HTTP_409_CONFLICT,
        MTAuthUnknownAccount: status.HTTP_404_NOT_FOUND,
        MTAuthHcaLinkRequired: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTAuthUnknownHca: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTAuthMissingSecret: status.HTTP_503_SERVICE_UNAVAILABLE,
        # Request payloads that fail their own model's validators
        MTInvalidActiveUpdateRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidLoginRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidRegisterRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidAccountUpdateRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidCompanyProfileUpdateRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        # A 500, not a 422, for the same reason as the pricing-rules family
        # below: this guards a *projection of an agency already stored*, so a
        # caller cannot cause one and has nothing to correct.
        MTInvalidCompanyViewException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidInterventionTypeUpdateRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidCertificationTypeUpdateRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidCertificationTypeException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidSkillTypeUpdateRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidSkillCreateRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidSkillTypeException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidQuoteInterruptionRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidQuoteCreateRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidQuoteHeaderRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidQuoteLinesRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidQuoteRescheduleRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        # A 500, not a 422. This family guards a *response* built from the
        # running configuration, so a caller cannot cause one and has nothing
        # to correct: it fires only when the deployment's own pricing rules
        # are unusable, which is the server's fault to report as its own.
        MTInvalidPricingRulesResponseException: (status.HTTP_500_INTERNAL_SERVER_ERROR),
        MTInvalidCompanyRegistrationRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidRoleUpdateRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidHcaApplicationRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidStaffAccountRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidPasswordChangeRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidApplicationDecisionRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidPlanningSettingsRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidWorkingDaysRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidInterventionTypeChangeRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidPlanningCompletedRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidEmploymentUpdateRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidHcaProfileUpdateRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidCustomerFilterException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        # Every list screen's filter, in one row. The concrete families
        # below it exist so a rejected filter names its own screen; what
        # they all mean is the same — the caller narrowed by something the
        # server cannot narrow by, which is theirs to correct.
        MTInvalidEntityFilterException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidStatusUpdateRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        # People
        MTHcaNotFound: status.HTTP_404_NOT_FOUND,
        MTAvailabilitySlotNotFound: status.HTTP_404_NOT_FOUND,
        MTSkillNotFound: status.HTTP_404_NOT_FOUND,
        MTCustomerNotFound: status.HTTP_404_NOT_FOUND,
        MTCustomerHasQuotes: status.HTTP_409_CONFLICT,
        # A conflict rather than a 422: the request is well formed and the
        # customer exists — they are simply not in the one state this act
        # applies to, and the caller's own screen may be showing stale data.
        MTCustomerNotPromotable: status.HTTP_409_CONFLICT,
        MTHcaForbidden: status.HTTP_403_FORBIDDEN,
        # Companies and applications
        MTCompanyNotFound: status.HTTP_404_NOT_FOUND,
        MTCompanyNameTaken: status.HTTP_409_CONFLICT,
        MTCompanyNotEmpty: status.HTTP_409_CONFLICT,
        MTCompanyNotAcceptingApplications: status.HTTP_409_CONFLICT,
        # 503, not 400: this describes the deployment rather than the request.
        # The same call works once an object store is configured, and there is
        # nothing about the payload the caller could change to help.
        MTCompanyLogoStorageUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
        # 404, not 403: a deployment that has not opted in should be
        # indistinguishable from one without the route at all.
        MTCompanyRegistrationDisabled: status.HTTP_404_NOT_FOUND,
        MTApplicationNotFound: status.HTTP_404_NOT_FOUND,
        MTApplicationForbidden: status.HTTP_403_FORBIDDEN,
        MTApplicationAlreadyDecided: status.HTTP_409_CONFLICT,
        MTDuplicateApplication: status.HTTP_409_CONFLICT,
        MTAuthPasswordChangeRequired: status.HTTP_403_FORBIDDEN,
        MTAuthSamePassword: status.HTTP_409_CONFLICT,
        MTHcaHasAccount: status.HTTP_409_CONFLICT,
        # Intervention-type catalog
        MTInterventionTypeNotFound: status.HTTP_404_NOT_FOUND,
        MTInterventionTypeAlreadyExists: status.HTTP_409_CONFLICT,
        # Certification catalogue
        MTCertificationTypeNotFound: status.HTTP_404_NOT_FOUND,
        MTCertificationTypeAlreadyExists: status.HTTP_409_CONFLICT,
        MTCertificationTypeInUse: status.HTTP_409_CONFLICT,
        # A 422, not a 404: the request named a code that does not exist, but
        # the resource being addressed is the service or the quote line, and
        # that one is there. A 404 would read as "no such service".
        MTCertificationTypeUnknownCode: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # Skill catalogue, answering exactly as its certification twin does.
        MTSkillTypeNotFound: status.HTTP_404_NOT_FOUND,
        MTSkillTypeAlreadyExists: status.HTTP_409_CONFLICT,
        MTSkillTypeInUse: status.HTTP_409_CONFLICT,
        MTSkillTypeUnknownCode: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # Quotes and pricing
        MTQuoteNotFound: status.HTTP_404_NOT_FOUND,
        # 404 too, and separate from the quote's own. The offered slots a
        # screen shows were computed when the planner last ran, so a line
        # edited away since is an ordinary stale-offer case rather than a
        # caller pointing at a quote that does not exist.
        MTQuoteLineNotFound: status.HTTP_404_NOT_FOUND,
        MTQuoteNotEditable: status.HTTP_409_CONFLICT,
        MTQuoteForbidden: status.HTTP_403_FORBIDDEN,
        MTQuoteNotPriced: status.HTTP_409_CONFLICT,
        MTPricingUnknownInterventionType: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # Planning
        MTPlanningRunNotFound: status.HTTP_404_NOT_FOUND,
        MTInterventionNotFound: status.HTTP_404_NOT_FOUND,
        MTInterventionNotQuoted: status.HTTP_409_CONFLICT,
        MTPlanningForbidden: status.HTTP_403_FORBIDDEN,
        MTPlanningPeriodTooLong: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTPlanningInfeasible: status.HTTP_409_CONFLICT,
        MTPlanningSettingsUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
        # Outbound email
        MTEmailNoRecipient: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTEmailNotConfigured: status.HTTP_503_SERVICE_UNAVAILABLE,
        MTEmailDeliveryFailed: status.HTTP_502_BAD_GATEWAY,
        # Object store
        MTS3PayloadTooLarge: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        MTS3UnsupportedContentType: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        MTS3EmptyPayload: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTS3UploadFailed: status.HTTP_500_INTERNAL_SERVER_ERROR,
        # A broker misuse — binding a queue before connecting — is this
        # process's fault, not the caller's. It is raised by the worker and
        # should never reach an HTTP response at all; the row exists so that
        # if it ever does, it is answered honestly rather than as a 422
        # blaming the request.
        MTInvalidMessagingException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTS3BucketUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
        # ------------------------------------------------------------------
        # Family defaults. Every MT* exception in the codebase descends from
        # one of these, and the lookup walks an exception's ancestry, so a new
        # member of a family is answered correctly the day it is written. The
        # rows above override their family where the meaning is more specific.
        # ------------------------------------------------------------------
        # A domain model refusing a value is a malformed payload: the caller's
        # fault, and the field name is in the message.
        MTInvalidEnumException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidUserException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidAccessTokenException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # The root the three people families share. Registered as well as
        # them, not instead of them: the lookup walks the MRO and takes the
        # first match, so a customer's own class is still what answers a
        # customer's failure. This row covers the generic ``MTPerson*``
        # exceptions, which are what a people model raises before somebody
        # gives it one of its own.
        MTInvalidPersonException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidCustomerException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidHcaException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidHcaApplicationException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidAvailabilitySlotException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidNotificationException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # A malformed broker message never reaches a client — the consumer
        # dead-letters it. The row exists so the family is covered rather than
        # answering an opaque 500 if one ever surfaces through an endpoint.
        MTInvalidEventEnvelopeException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidCertificationException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidSkillException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidDrivingLicenseException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidCompanyException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidInterventionTypeException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidQuoteException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidQuoteLineException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidQuoteTypeWeekAggregateException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidGeoPointException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidPostalAddressException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidPlanningRunException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidHcaPlanningException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidInterventionException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidInterventionRequirementException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidSuggestedSlotException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidUnplacedQuoteException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidUnplacedRequirementException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidPlanningSettingsException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # A service refusing an operation. The concrete members carry their own
        # meaning above; a new one defaults to "refused", never to a 500, which
        # would blame this deployment for the caller's request.
        MTInvalidAuthException: status.HTTP_400_BAD_REQUEST,
        MTInvalidHcaServiceException: status.HTTP_400_BAD_REQUEST,
        MTInvalidCustomerServiceException: status.HTTP_400_BAD_REQUEST,
        MTInvalidCompanyServiceException: status.HTTP_400_BAD_REQUEST,
        MTInvalidInterventionTypeCatalogException: status.HTTP_400_BAD_REQUEST,
        MTInvalidCertificationCatalogException: status.HTTP_400_BAD_REQUEST,
        MTInvalidSkillCatalogException: status.HTTP_400_BAD_REQUEST,
        MTInvalidPricingException: status.HTTP_400_BAD_REQUEST,
        MTInvalidPlanningException: status.HTTP_400_BAD_REQUEST,
        # A response model that will not build is **our** bug: the caller asked
        # for something reasonable and we could not describe the answer.
        MTInvalidUserResponseException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidHcaResponseException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidHealthResponseException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidReadinessResponseException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidPhotoConstraintsResponseException: (
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ),
        MTInvalidTemporaryCredentialsResponseException: (
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ),
        MTInvalidEmailDispatchResponseException: (
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ),
        # A misconfigured deployment. Nothing the caller can do about it, and
        # the message is replaced below rather than published.
        MTInvalidAppConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidAuthConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidDatabaseConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidEmailConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidWebhookConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidGeocodingConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidObservabilityConfigException: (status.HTTP_500_INTERNAL_SERVER_ERROR),
        MTInvalidPlanningConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidPricingConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidHolidaySurchargeException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidS3ConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidRabbitMqConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidServerConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        # Storage. A store that cannot be reached is temporary; a row that will
        # not map is not.
        MTInvalidDatabaseConnectionException: status.HTTP_503_SERVICE_UNAVAILABLE,
        MTInvalidS3StorageException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidMapperException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidEmailException: status.HTTP_502_BAD_GATEWAY,
    }

    DETAIL_BY_EXCEPTION: ClassVar[Dict[Type[Exception], str]] = {
        MTAuthMissingSecret: "Authentication is not configured.",
        MTEmailNotConfigured: "Outbound email is not configured.",
        MTS3BucketUnavailable: "The photograph store is unavailable.",
    }

    HEADERS_BY_EXCEPTION: ClassVar[Dict[Type[Exception], Dict[str, str]]] = {
        MTAuthInvalidCredentials: {"WWW-Authenticate": "Bearer"},
    }

    UNEXPECTED_DETAIL: ClassVar[str] = "The request could not be completed."

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the handlers.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug(
            "ExceptionHandlers created for %d domain exception(s).",
            len(self.STATUS_BY_EXCEPTION),
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _status_for(self, exc: Exception) -> int:
        """Return the status an exception answers with.

        Args:
            exc (Exception): The exception that reached the boundary.

        Returns:
            int: Its mapped status, or ``500`` when it is not in the table.

        Notes:
            The ancestry is walked rather than the exact type looked up, so a
            new member of an already-mapped family answers correctly the day it
            is written, without a second edit here.
        """
        for ancestor in type(exc).__mro__:
            mapped = self.STATUS_BY_EXCEPTION.get(ancestor)
            if mapped is not None:
                return mapped
        # The loud failure the class docstring promises. Without this the 500
        # says nothing about which exception produced it, and the table is only
        # discovered to be incomplete by reading a stack trace.
        self.logger.error(
            "%s is not mapped to a status; answering 500. Add it to "
            "STATUS_BY_EXCEPTION.",
            type(exc).__name__,
        )
        return status.HTTP_500_INTERNAL_SERVER_ERROR

    def _detail_for(self, exc: Exception) -> str:
        """Return the message a client is shown for an exception.

        Args:
            exc (Exception): The exception that reached the boundary.

        Returns:
            str: The replacement message when one is configured, the
            exception's own text otherwise.
        """
        for ancestor in type(exc).__mro__:
            replacement = self.DETAIL_BY_EXCEPTION.get(ancestor)
            if replacement is not None:
                return replacement
        return str(exc)

    def _headers_for(self, exc: Exception) -> Optional[Dict[str, str]]:
        """Return the extra headers an exception's response must carry.

        Args:
            exc (Exception): The exception that reached the boundary.

        Returns:
            Optional[Dict[str, str]]: The headers, or ``None`` when there are
            none.

        Notes:
            A 401 must name the scheme it expects. Without
            ``WWW-Authenticate``, the answer is not a valid challenge and a
            client cannot tell a rejected credential from a missing one.
        """
        for ancestor in type(exc).__mro__:
            headers = self.HEADERS_BY_EXCEPTION.get(ancestor)
            if headers is not None:
                return dict(headers)
        return None

    def _log(self, request: Request, status_code: int, exc: Exception) -> None:
        """Record a rejected request at a level matching its status.

        Args:
            request (Request): The request that failed.
            status_code (int): The status being answered.
            exc (Exception): The exception that caused it.

        Notes:
            A ``5xx`` is this deployment's fault and is logged at ``ERROR``
            with the exception's own text, whatever the client is shown. A
            ``4xx`` is the caller's and is a ``WARNING``: a wall of stack
            traces for clients sending bad input would bury the failures that
            are actually ours.
        """
        if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            self.logger.error(
                "%s %s failed with %d: %s (%s).",
                request.method,
                request.url.path,
                status_code,
                exc,
                type(exc).__name__,
            )
            return
        self.logger.warning(
            "%s %s rejected with %d: %s.",
            request.method,
            request.url.path,
            status_code,
            exc,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def handle_domain_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Answer a mapped domain exception.

        Args:
            request (Request): The request that failed.
            exc (Exception): The domain exception raised beneath the endpoint.

        Returns:
            JSONResponse: The mapped status, carrying ``detail``.
        """
        status_code = self._status_for(exc)
        self._log(request, status_code, exc)
        return JSONResponse(
            status_code=status_code,
            content={"detail": self._detail_for(exc)},
            headers=self._headers_for(exc),
        )

    async def handle_unexpected_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Answer anything that reached the boundary unmapped.

        Args:
            request (Request): The request that failed.
            exc (Exception): The exception nobody planned for.

        Returns:
            JSONResponse: A ``500`` carrying a fixed message.

        Notes:
            The client is told nothing beyond "it failed". The endpoints used
            to interpolate ``str(exc)`` into the body, which publishes whatever
            a driver, a bucket or an ORM decided to say — table names and
            connection strings included. The full text goes to the log instead,
            where it is useful and not readable by the caller.
        """
        self._log(request, status.HTTP_500_INTERNAL_SERVER_ERROR, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": self.UNEXPECTED_DETAIL},
        )

    def register(self, app: FastAPI) -> None:
        """Attach every handler to an application.

        Args:
            app (FastAPI): The application to attach them to.

        Notes:
            Called once at start-up, and again by any test that mounts a router
            on an application of its own — a router alone answers ``500`` for
            everything until these are installed.
        """
        for exception_class in self.STATUS_BY_EXCEPTION:
            app.add_exception_handler(exception_class, self.handle_domain_exception)
        app.add_exception_handler(Exception, self.handle_unexpected_exception)
        self.logger.info(
            "Registered %d domain exception handler(s) and the catch-all.",
            len(self.STATUS_BY_EXCEPTION),
        )
