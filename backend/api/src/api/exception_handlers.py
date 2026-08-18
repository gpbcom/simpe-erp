from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Type

# Third-party imports
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from integrations.exceptions import (
    MTConnectorNotImplemented,
    MTConnectorRejected,
    MTConnectorUnauthorised,
    MTConnectorUnavailable,
    MTConnectorUnsupported,
    MTInvoicingConnectorException,
)
from models.auth.exceptions import (
    MTInvalidAccessTokenException,
    MTInvalidUserException,
)

# First-party imports
from models.base.exceptions import (
    MTInvalidEntityFilterException,
    MTInvalidPersonException,
)
from models.base.exceptions.organisation_member_exceptions import (
    MTInvalidOrganisationMemberException,
)
from models.billing.exceptions import (
    MTInvalidBillException,
    MTInvalidBillingRunException,
    MTInvalidBillLineException,
    MTInvalidBillRecipientException,
)
from models.catalog.exceptions import (
    MTInvalidCertificationTypeException,
    MTInvalidInterventionTypeException,
    MTInvalidSkillTypeException,
)
from models.configuration.exceptions import (
    MTInvalidAppConfigException,
    MTInvalidAuthConfigException,
    MTInvalidBillingConfigException,
    MTInvalidDatabaseConfigException,
    MTInvalidEmailConfigException,
    MTInvalidGeocodingConfigException,
    MTInvalidHolidaySurchargeException,
    MTInvalidIntegrationConfigException,
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
from models.integrations.exceptions import (
    MTInvalidEInvoicingIntegrationException,
    MTInvalidIntegrationCredentialsException,
    MTInvalidProviderDescriptorException,
    MTInvalidTransmissionReceiptException,
)
from models.messaging.exceptions import MTInvalidEventEnvelopeException
from models.notifications.exceptions import MTInvalidNotificationException
from models.organisation.agency.exceptions import (
    MTInvalidAgencyException,
)
from models.organisation.companies.exceptions import MTInvalidCompanyException
from models.organisation.team.exceptions import (
    MTInvalidTeamDocumentException,
    MTInvalidTeamException,
    MTInvalidTeamMemberException,
)
from models.people.customer.exceptions import MTInvalidCustomerException
from models.people.hca.exceptions import (
    MTInvalidAvailabilitySlotException,
    MTInvalidCertificationException,
    MTInvalidDrivingLicenseException,
    MTInvalidHcaException,
    MTInvalidSkillException,
)
from models.people.hca_application.exceptions import MTInvalidHcaApplicationException
from models.planning.customer_planning.exceptions import (
    MTInvalidCustomerPlanningException,
)
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
    MTInvalidAccountUpdateRequestException,
    MTInvalidActiveUpdateRequestException,
    MTInvalidAgencyCreateRequestException,
    MTInvalidAgencyUpdateRequestException,
    MTInvalidAgencyViewException,
    MTInvalidApplicationDecisionRequestException,
    MTInvalidBillAcceptedRequestException,
    MTInvalidBillDispatchResponseException,
    MTInvalidBillFilterException,
    MTInvalidBillGenerationRequestException,
    MTInvalidBillingPeriodicityRequestException,
    MTInvalidBillingSettingsRequestException,
    MTInvalidBillPaidRequestException,
    MTInvalidBillStatusRequestException,
    MTInvalidCertificationTypeUpdateRequestException,
    MTInvalidCompanyProfileUpdateRequestException,
    MTInvalidCompanyRegistrationRequestException,
    MTInvalidCompanyViewException,
    MTInvalidCustomerAccountRequestException,
    MTInvalidCustomerFilterException,
    MTInvalidCustomerProfileUpdateRequestException,
    MTInvalidEmailDispatchResponseException,
    MTInvalidEmploymentUpdateRequestException,
    MTInvalidHcaApplicationRequestException,
    MTInvalidHcaProfileUpdateRequestException,
    MTInvalidHcaResponseException,
    MTInvalidHealthResponseException,
    MTInvalidIntegrationSchemaException,
    MTInvalidInterventionRescheduleRequestException,
    MTInvalidInterventionTypeChangeRequestException,
    MTInvalidInterventionTypeUpdateRequestException,
    MTInvalidLoginRequestException,
    MTInvalidPasswordChangeRequestException,
    MTInvalidPhotoConstraintsResponseException,
    MTInvalidPlanningCompletedRequestException,
    MTInvalidPlanningSettingsRequestException,
    MTInvalidPricingRulesResponseException,
    MTInvalidQuoteCreateRequestException,
    MTInvalidQuoteHeaderRequestException,
    MTInvalidQuoteInterruptionRequestException,
    MTInvalidQuoteLinesRequestException,
    MTInvalidQuoteRescheduleRequestException,
    MTInvalidQuoteTeamRequestException,
    MTInvalidReadinessResponseException,
    MTInvalidRegisterRequestException,
    MTInvalidRoleUpdateRequestException,
    MTInvalidSkillCreateRequestException,
    MTInvalidSkillTypeUpdateRequestException,
    MTInvalidStaffAccountRequestException,
    MTInvalidStatusUpdateRequestException,
    MTInvalidTeamCreateRequestException,
    MTInvalidTeamDocumentConstraintsResponseException,
    MTInvalidTeamUpdateRequestException,
    MTInvalidTeamViewException,
    MTInvalidTemporaryCredentialsResponseException,
    MTInvalidUserResponseException,
    MTInvalidWorkingDaysRequestException,
)
from models.settings.exceptions import (
    MTInvalidBillingSettingsException,
    MTInvalidPlanningSettingsException,
)
from service.auth.exceptions import (
    MTAuthCustomerAlreadyHasAccount,
    MTAuthEmailAlreadyRegistered,
    MTAuthHcaLinkRequired,
    MTAuthInvalidCredentials,
    MTAuthInvalidToken,
    MTAuthLastAdmin,
    MTAuthMissingSecret,
    MTAuthPasswordChangeRequired,
    MTAuthSamePassword,
    MTAuthUnknownAccount,
    MTAuthUnknownCustomer,
    MTAuthUnknownHca,
    MTAuthUserInactive,
    MTInvalidAuthException,
)
from service.billing.exceptions import (
    MTBillAlreadyIssued,
    MTBillDocumentStorageUnavailable,
    MTBillDocumentUnavailable,
    MTBillingForbidden,
    MTBillingPeriodInFuture,
    MTBillingRunNotFound,
    MTBillingSettingsUnavailable,
    MTBillNotFound,
    MTBillNothingToBill,
    MTBillTransitionNotAllowed,
    MTInvalidBillingServiceException,
)
from service.certifications.exceptions import (
    MTCertificationTypeAlreadyExists,
    MTCertificationTypeInUse,
    MTCertificationTypeNotFound,
    MTCertificationTypeUnknownCode,
    MTInvalidCertificationCatalogException,
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
    MTDuplicateApplication,
    MTHcaForbidden,
    MTHcaHasAccount,
    MTHcaNotFound,
    MTInvalidHcaServiceException,
    MTSkillNotFound,
)
from service.integrations.exceptions import (
    MTIntegrationCredentialsRefused,
    MTIntegrationNotConfigured,
    MTInvoicingServiceException,
    MTNoActivePlatform,
)
from service.integrations.utils.exceptions import (
    MTInvalidCiiInvoiceException,
    MTInvalidFacturXException,
)
from service.intervention_types.exceptions import (
    MTInterventionTypeAlreadyExists,
    MTInterventionTypeNotFound,
    MTInvalidInterventionTypeCatalogException,
)
from service.messaging.exceptions import MTInvalidMessagingException
from service.organisation.exceptions import (
    MTAgencyForbidden,
    MTAgencyHeadquartersProtected,
    MTAgencyMemberOutsideCompany,
    MTAgencyMemberRunsATeam,
    MTAgencyNameTaken,
    MTAgencyNotEmpty,
    MTAgencyNotFound,
    MTInvalidAgencyServiceException,
    MTInvalidTeamDocumentServiceException,
    MTInvalidTeamServiceException,
    MTTeamDocumentForbidden,
    MTTeamDocumentNotFound,
    MTTeamDocumentStorageUnavailable,
    MTTeamForbidden,
    MTTeamHasWork,
    MTTeamManagerRequired,
    MTTeamMemberManagesAnother,
    MTTeamMemberOutsideAgency,
    MTTeamNameTaken,
    MTTeamNotFound,
)
from service.planning.exceptions import (
    MTInterventionNotFound,
    MTInterventionNotQuoted,
    MTInvalidPlanningException,
    MTPlanningCustomerNotFound,
    MTPlanningForbidden,
    MTPlanningInfeasible,
    MTPlanningPeriodTooLong,
    MTPlanningRunNotFound,
    MTPlanningScopeForbidden,
    MTPlanningSettingsUnavailable,
    MTPlanningTeamForbidden,
)
from service.quotes.exceptions import (
    MTInvalidPricingException,
    MTPricingUnknownInterventionType,
    MTQuoteForbidden,
    MTQuoteLineNotFound,
    MTQuoteNotEditable,
    MTQuoteNotFound,
    MTQuoteNotPriced,
    MTQuoteTeamForbidden,
    MTQuoteUnassignable,
)
from service.security.exceptions import (
    MTCredentialCipherException,
    MTCredentialCipherKeyUnusable,
    MTCredentialCipherUnreadable,
)
from service.skills.exceptions import (
    MTInvalidSkillCatalogException,
    MTSkillTypeAlreadyExists,
    MTSkillTypeInUse,
    MTSkillTypeNotFound,
    MTSkillTypeUnknownCode,
)
from service.utils.exceptions import (
    MTInvalidInvoiceRendererException,
    MTInvalidQuoteRendererException,
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
        MTAuthUnknownCustomer: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # 409, not 422: the request is well formed and the caller may make
        # it — what refuses is that the household already has access.
        MTAuthCustomerAlreadyHasAccount: status.HTTP_409_CONFLICT,
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
        MTInvalidCustomerAccountRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidCustomerProfileUpdateRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidInterventionRescheduleRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
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
        # Billing payloads. The filter family is registered on its own even
        # though it also descends from MTInvalidEntityFilterException below,
        # so a rejected bill filter names the screen it came from.
        MTInvalidBillFilterException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidBillGenerationRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidBillStatusRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidBillingSettingsRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidBillAcceptedRequestException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        # One customer's own granularity, refused for the same reason: a
        # periodicity nobody can bill on is the caller's to correct. Clearing
        # the override is not a refusal — a null periodicity is a valid payload.
        MTInvalidBillingPeriodicityRequestException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
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
        # Billing
        MTBillNotFound: status.HTTP_404_NOT_FOUND,
        MTBillingRunNotFound: status.HTTP_404_NOT_FOUND,
        # Conflicts rather than 422s: the request is well formed and the
        # invoice or the period exists — it is simply not in the state the
        # act applies to, and the caller's screen may be showing stale data.
        MTBillAlreadyIssued: status.HTTP_409_CONFLICT,
        MTBillNothingToBill: status.HTTP_409_CONFLICT,
        MTBillTransitionNotAllowed: status.HTTP_409_CONFLICT,
        # A period that has not finished is the caller's to correct: care
        # that has not happened cannot be invoiced.
        MTBillingPeriodInFuture: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTBillingForbidden: status.HTTP_403_FORBIDDEN,
        # 503, not 500: these describe the deployment rather than the
        # request. The same call works once the rules are seeded or the
        # object store answers, and there is nothing the caller can change.
        MTBillingSettingsUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
        MTBillDocumentUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
        MTBillDocumentStorageUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
        # Quotes and pricing
        MTQuoteNotFound: status.HTTP_404_NOT_FOUND,
        # 404 too, and separate from the quote's own. The offered slots a
        # screen shows were computed when the planner last ran, so a line
        # edited away since is an ordinary stale-offer case rather than a
        # caller pointing at a quote that does not exist.
        MTQuoteLineNotFound: status.HTTP_404_NOT_FOUND,
        MTQuoteNotEditable: status.HTTP_409_CONFLICT,
        MTQuoteForbidden: status.HTTP_403_FORBIDDEN,
        # A quote nothing can be attributed to is refused rather than stored
        # unattributed: 422, because the caller can fix it — by correcting the
        # household or by forming a team — and the message says which.
        MTQuoteUnassignable: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # 403 rather than 404, unlike the agency and team refusals. The caller
        # is a manager of this company and already reads the quote. The teams
        # they may move it between are not a secret from them, so pretending
        # the quote vanished would read as a bug.
        MTQuoteTeamForbidden: status.HTTP_403_FORBIDDEN,
        MTQuoteNotPriced: status.HTTP_409_CONFLICT,
        MTPricingUnknownInterventionType: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # Planning
        MTPlanningRunNotFound: status.HTTP_404_NOT_FOUND,
        # A household outside an assistant's portfolio answers 404, not 403.
        # Saying "not yours" would confirm the household exists, which is what
        # lets somebody enumerate the agency's customers one identifier at a
        # time.
        MTPlanningCustomerNotFound: status.HTTP_404_NOT_FOUND,
        MTInterventionNotFound: status.HTTP_404_NOT_FOUND,
        MTInterventionNotQuoted: status.HTTP_409_CONFLICT,
        MTPlanningForbidden: status.HTTP_403_FORBIDDEN,
        # Both refusals are 403 and neither may fall through to the family
        # base, which is a 400: "bad request" would tell a manager their
        # button is broken when what happened is that the team, or the whole
        # company, is not theirs to rebuild.
        MTPlanningTeamForbidden: status.HTTP_403_FORBIDDEN,
        MTPlanningScopeForbidden: status.HTTP_403_FORBIDDEN,
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
        # should never reach an HTTP response at all. The row exists so that
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
        # How the company is organised: its sites, its teams, and the files a
        # team shares. Five families rather than one, and the split is the
        # same one this map is built on — a refusal has to say *which* thing
        # was malformed, because "the site has no name" and "the team names no
        # manager" send a reader to two different forms.
        MTInvalidAgencyException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidTeamException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidTeamDocumentException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # The membership families. The shared base's defaults are here too:
        # a concrete membership model declares its own, so this row only
        # catches one that has not — which must still be a typed 422 rather
        # than reaching the catch-all as a 500.
        MTInvalidOrganisationMemberException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidTeamMemberException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # The payloads and projections of those same two aggregates. Separate
        # families from the models they build, because a malformed *request* is
        # the caller's to fix while a malformed *projection* is ours — and only
        # the first should ever reach a user as an instruction.
        MTInvalidQuoteTeamRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,  # noqa: E501
        MTInvalidAgencyCreateRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,  # noqa: E501
        MTInvalidAgencyUpdateRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,  # noqa: E501
        MTInvalidTeamCreateRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,  # noqa: E501
        MTInvalidTeamUpdateRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,  # noqa: E501
        MTInvalidAgencyViewException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidTeamViewException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidTeamDocumentConstraintsResponseException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        # Operations on the organisation. The family bases answer 422 so a
        # subclass added without a row of its own is still a typed refusal. The
        # rows below say where each genuinely differs.
        MTInvalidAgencyServiceException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidTeamServiceException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidTeamDocumentServiceException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTAgencyNotFound: status.HTTP_404_NOT_FOUND,
        # 404, not 403. Distinguishing "does not exist" from "not yours" lets a
        # caller walk the identifier space and count how many places a
        # competitor operates from, which is most of what a site list is worth.
        MTAgencyForbidden: status.HTTP_404_NOT_FOUND,
        MTAgencyNameTaken: status.HTTP_409_CONFLICT,
        # 409 rather than 422: the payload is well formed, and what refuses it
        # is the state of other rows — a head office that already exists, or
        # teams still working from the site.
        MTAgencyHeadquartersProtected: status.HTTP_409_CONFLICT,
        MTAgencyNotEmpty: status.HTTP_409_CONFLICT,
        # 409: the request is well formed and the caller may act, but the
        # company is in a state that refuses it. Naming a new manager for the
        # team is what unblocks it.
        MTAgencyMemberRunsATeam: status.HTTP_409_CONFLICT,
        MTAgencyMemberOutsideCompany: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTTeamNotFound: status.HTTP_404_NOT_FOUND,
        MTTeamForbidden: status.HTTP_404_NOT_FOUND,
        MTTeamNameTaken: status.HTTP_409_CONFLICT,
        # 422: the request names somebody who cannot run a team, which is a
        # payload the caller can correct.
        MTTeamManagerRequired: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTTeamMemberManagesAnother: status.HTTP_409_CONFLICT,
        MTTeamMemberOutsideAgency: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTTeamHasWork: status.HTTP_409_CONFLICT,
        MTTeamDocumentNotFound: status.HTTP_404_NOT_FOUND,
        # 403 here, unlike everywhere else, and deliberately: every member may
        # read every document in their team's space, so its existence is not a
        # secret from them. What is refused is deleting a colleague's file, and
        # "no such document" for something plainly on screen reads as a bug.
        MTTeamDocumentForbidden: status.HTTP_403_FORBIDDEN,
        MTTeamDocumentStorageUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
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
        # The same diary read on the other axis. A separate family because the
        # two carry different identifiers and different names, so a refusal
        # says which of the two was malformed rather than "a planning".
        MTInvalidCustomerPlanningException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidInterventionException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidInterventionRequirementException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidSuggestedSlotException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidUnplacedQuoteException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidUnplacedRequirementException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidPlanningSettingsException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidBillingSettingsException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidBillException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidBillLineException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidBillRecipientException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # E-invoicing integrations. The split here is between what a caller
        # can fix, what a *platform* did, and what is a fault in this
        # deployment — three audiences that must not share a status code.
        MTIntegrationNotConfigured: status.HTTP_404_NOT_FOUND,
        # 409, not 422: connecting nothing is a well-formed request against an
        # agency that has not done a prerequisite. The screen's answer is
        # "connect a platform", not "fix this field".
        MTNoActivePlatform: status.HTTP_409_CONFLICT,
        # 502 and 503: a certified platform is a third party. Its refusal of a
        # key, or its being down, is not this API's fault and not the caller's,
        # and a 500 would send an operator looking in the wrong logs.
        MTIntegrationCredentialsRefused: status.HTTP_502_BAD_GATEWAY,
        MTConnectorUnauthorised: status.HTTP_502_BAD_GATEWAY,
        MTConnectorRejected: status.HTTP_502_BAD_GATEWAY,
        MTConnectorUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
        # A platform that documents no route to public bodies is a procurement
        # fact, not a malformed request: the agency must connect one that does.
        MTConnectorUnsupported: status.HTTP_409_CONFLICT,
        MTInvoicingConnectorException: status.HTTP_502_BAD_GATEWAY,
        MTInvoicingServiceException: status.HTTP_400_BAD_REQUEST,
        # Payloads a caller can correct. The credentials family's messages
        # never quote the key, which is what makes returning them safe.
        MTInvalidIntegrationCredentialsException: (
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        MTInvalidEInvoicingIntegrationException: (status.HTTP_422_UNPROCESSABLE_ENTITY),
        MTInvalidIntegrationSchemaException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        MTInvalidBillPaidRequestException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # 500s, all of them programming or deployment faults rather than
        # anything a request did: a platform in the enumeration with no
        # catalogue entry or no connector, a receipt a connector built wrong,
        # a credential key that is missing or will not open.
        MTConnectorNotImplemented: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidProviderDescriptorException: (status.HTTP_500_INTERNAL_SERVER_ERROR),
        MTInvalidTransmissionReceiptException: (status.HTTP_500_INTERNAL_SERVER_ERROR),
        MTCredentialCipherKeyUnusable: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTCredentialCipherUnreadable: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTCredentialCipherException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidIntegrationConfigException: (status.HTTP_500_INTERNAL_SERVER_ERROR),
        MTInvalidBillingRunException: status.HTTP_422_UNPROCESSABLE_ENTITY,
        # A service refusing an operation. The concrete members carry their own
        # meaning above. A new one defaults to "refused", never to a 500, which
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
        MTInvalidBillingServiceException: status.HTTP_400_BAD_REQUEST,
        # A response model that will not build is **our** bug: the caller asked
        # for something reasonable and we could not describe the answer.
        # A document that would not lay out is **our** bug, like a response
        # model that will not build: the caller asked for an invoice they
        # were entitled to and we could not produce it.
        MTInvalidInvoiceRendererException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        # The structured half of the invoice, and the container that carries
        # it. Both are 500s for the same reason the renderer is: the caller
        # asked for an invoice they were entitled to. Two families rather than
        # one, because they fail for unrelated reasons and the log line should
        # say which — a missing VAT number on the agency is somebody's record to
        # complete, and a container that would not assemble is our defect.
        MTInvalidCiiInvoiceException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidFacturXException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        # A render failure is a 500: the document could not be produced. An
        # *unpriced* quote is a 422 and is already registered under
        # MTInvalidPricingException — the offer is simply not ready yet, which
        # is the screen's problem to explain rather than a server error.
        MTInvalidQuoteRendererException: status.HTTP_500_INTERNAL_SERVER_ERROR,
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
        MTInvalidBillDispatchResponseException: (status.HTTP_500_INTERNAL_SERVER_ERROR),
        # A misconfigured deployment. Nothing the caller can do about it, and
        # the message is replaced below rather than published.
        MTInvalidAppConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
        MTInvalidBillingConfigException: status.HTTP_500_INTERNAL_SERVER_ERROR,
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
        # Storage. A store that cannot be reached is temporary. A row that will
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

    def _status(self, exc: Exception) -> int:
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
            "%s is not mapped to a status. Answering 500. Add it to "
            "STATUS_BY_EXCEPTION.",
            type(exc).__name__,
        )
        return status.HTTP_500_INTERNAL_SERVER_ERROR

    def _detail(self, exc: Exception) -> str:
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

    def _headers(self, exc: Exception) -> Optional[Dict[str, str]]:
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
        status_code = self._status(exc)
        self._log(request, status_code, exc)
        return JSONResponse(
            status_code=status_code,
            content={"detail": self._detail(exc)},
            headers=self._headers(exc),
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
