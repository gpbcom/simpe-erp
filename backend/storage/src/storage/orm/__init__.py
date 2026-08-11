"""Every table the application declares, gathered for the metadata.

The rows themselves live in packages named after the domain they belong
to. They are re-exported here because Alembic and the test schema builder
need one import that reaches every table: a row that no module imports is
a table ``create_all`` silently omits, and the failure surfaces as a
missing relation long after the migration that should have made it.
"""

from .base import Base
from .auth.user_row import UserRow
from .billing.bill_line_row import BillLineRow
from .billing.bill_row import BillRow
from .billing.billing_run_row import BillingRunRow
from .billing.billing_settings_row import BillingSettingsRow
from .catalog.certification_type_row import CertificationTypeRow
from .catalog.intervention_type_row import InterventionTypeRow
from .catalog.skill_type_row import SkillTypeRow
from .companies.company_row import CompanyRow
from .notifications.notification_row import NotificationRow
from .people.availability_row import AvailabilityRow
from .people.certification_row import CertificationRow
from .people.customer_row import CustomerRow
from .people.hca_application_row import HcaApplicationRow
from .people.hca_row import HcaRow
from .people.skill_row import SkillRow
from .planning.intervention_row import InterventionRow
from .planning.planning_run_row import PlanningRunRow
from .planning.planning_settings_row import PlanningSettingsRow
from .quoting.quote_aggregate_row import QuoteAggregateRow
from .quoting.quote_line_row import QuoteLineRow
from .quoting.quote_row import QuoteRow

__all__ = [
    "AvailabilityRow",
    "Base",
    "BillLineRow",
    "BillRow",
    "BillingRunRow",
    "BillingSettingsRow",
    "CertificationRow",
    "CertificationTypeRow",
    "CompanyRow",
    "CustomerRow",
    "HcaApplicationRow",
    "HcaRow",
    "InterventionRow",
    "InterventionTypeRow",
    "NotificationRow",
    "PlanningRunRow",
    "PlanningSettingsRow",
    "QuoteAggregateRow",
    "QuoteLineRow",
    "QuoteRow",
    "SkillRow",
    "SkillTypeRow",
    "UserRow",
]
