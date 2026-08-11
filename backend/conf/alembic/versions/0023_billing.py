"""Invoice what the agency has delivered, and track it through to payment.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-11

Notes:
    The application could quote work, plan it and email the quote, but it could
    not invoice any of it. Four tables land together because none of them is
    useful alone: the rules an agency invoices under, the record of asking for a
    period to be billed, the invoices themselves, and the visits each one
    charges for.

    **Three unique indexes on ``bills``, and each prevents a different
    accident.** ``(customer_id, period_start, period_end)`` is what actually
    stops a customer being billed twice for one month when two runs race past
    the service's own check. ``number`` and
    ``(company_id, sequence_year, sequence)`` guard the legal series, which
    French invoicing requires to be unbroken and chronological — two runs
    allocating the same position must fail loudly rather than leave a gap
    nobody can explain.

    **Nothing is backfilled, and there is nothing to backfill.** An agency
    starts invoicing from its first run; there is no historic invoice to
    reconstruct, and inventing one would put a document into a legal series
    that never issued it. ``billing_settings`` is deliberately left empty too —
    the row is seeded from ``app.yaml`` the first time it is read, exactly as
    the planning rules are.

    ``companies.sap_declaration_number`` is nullable for the reason 0018's
    columns were: there is no safe value to invent. An agency that has not
    filled it in prints an invoice without the *services à la personne*
    mention, which is a document missing an optional line rather than one
    carrying a false declaration.

    The downgrade drops issued invoices. It exists so the migration is
    reversible in development and should not be reached for in anger: the
    correct undo for a mistaken invoice is a credit note, because a number
    withdrawn from the series is the gap the series forbids.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

#: Width of every identifier column, matching ``Base.ID_LENGTH``.
ID_LENGTH = 36


def upgrade() -> None:
    """Create the billing tables and the agency's SAP declaration number."""
    op.create_table(
        "billing_settings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("periodicity", sa.String(length=16), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("late_penalty_multiplier", sa.Integer(), nullable=False),
        sa.Column(
            "recovery_indemnity_eur",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column("escompte_offered", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "billing_runs",
        sa.Column("id", sa.String(length=ID_LENGTH), primary_key=True),
        sa.Column("company_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("requested_by", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("periodicity", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "bill_ids",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "failed_customer_ids",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_billing_runs_status", "billing_runs", ["status"])
    op.create_index("ix_billing_runs_company", "billing_runs", ["company_id", "status"])
    op.create_index(
        "ix_billing_runs_period",
        "billing_runs",
        ["period_start", "period_end"],
    )

    op.create_table(
        "bills",
        sa.Column("id", sa.String(length=ID_LENGTH), primary_key=True),
        sa.Column("company_id", sa.String(length=ID_LENGTH), nullable=False),
        # RESTRICT, like the quote's: deleting a billed customer would erase
        # accounting history, and that is an operator's deliberate decision.
        sa.Column(
            "customer_id",
            sa.String(length=ID_LENGTH),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Not a foreign key: purging old runs must never take an invoice.
        sa.Column("billing_run_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("sequence_year", sa.Integer(), nullable=False),
        sa.Column("periodicity", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        # The customer's name and address are copies, taken when the invoice
        # was issued. A customer who moves must not retroactively change where
        # last quarter's invoice was addressed.
        sa.Column("customer_full_name", sa.String(length=255), nullable=False),
        sa.Column("street", sa.String(length=255), nullable=False),
        sa.Column("postal_code", sa.String(length=16), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("geocoding_error", sa.String(length=64), nullable=True),
        sa.Column("total_ht", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_vat", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_ttc", sa.Numeric(precision=12, scale=2), nullable=False),
        # The object key, never a public URL: these documents are private and
        # are only ever read back server-side.
        sa.Column("document_key", sa.String(length=1024), nullable=True),
        # Audit strings rather than foreign keys, so "who approved this?"
        # outlives the account of whoever left the agency.
        sa.Column("generated_by", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("validated_by", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bills_number_unique", "bills", ["number"], unique=True)
    op.create_index(
        "ix_bills_sequence_unique",
        "bills",
        ["company_id", "sequence_year", "sequence"],
        unique=True,
    )
    op.create_index(
        "ix_bills_customer_period_unique",
        "bills",
        ["customer_id", "period_start", "period_end"],
        unique=True,
    )
    op.create_index("ix_bills_company_status", "bills", ["company_id", "status"])
    op.create_index("ix_bills_period", "bills", ["period_start", "period_end"])
    op.create_index("ix_bills_run", "bills", ["billing_run_id"])

    op.create_table(
        "bill_lines",
        sa.Column("id", sa.String(length=ID_LENGTH), primary_key=True),
        sa.Column(
            "bill_id",
            sa.String(length=ID_LENGTH),
            sa.ForeignKey("bills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        # Neither of the next two is a foreign key. A quote line may be edited
        # after the invoice was issued, and an intervention *will* be deleted:
        # re-planning a period rewrites every visit in it, so a real key would
        # either cascade the invoice line away or block the replan.
        sa.Column("quote_line_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("intervention_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("service_category", sa.String(length=16), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("day", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("hca_full_name", sa.String(length=255), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        # Not nullable, unlike a quote line's. An invoice with a blank amount
        # column is a legal defect, so the table says so.
        sa.Column("hourly_rate_ht", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_ht", sa.Numeric(precision=12, scale=2), nullable=False),
        # Four decimals, where the money carries two: 5.5% is 0.0550, and
        # rounding it to the cent would make every reduced-rate line tax-free.
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("vat_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_ttc", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bill_lines_bill_id", "bill_lines", ["bill_id"])
    op.create_index("ix_bill_lines_service_date", "bill_lines", ["service_date"])
    op.create_index("ix_bill_lines_quote_line", "bill_lines", ["quote_line_id"])

    op.add_column(
        "companies",
        sa.Column("sap_declaration_number", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Drop the billing tables and the SAP declaration number."""
    op.drop_column("companies", "sap_declaration_number")

    op.drop_index("ix_bill_lines_quote_line", table_name="bill_lines")
    op.drop_index("ix_bill_lines_service_date", table_name="bill_lines")
    op.drop_index("ix_bill_lines_bill_id", table_name="bill_lines")
    op.drop_table("bill_lines")

    op.drop_index("ix_bills_run", table_name="bills")
    op.drop_index("ix_bills_period", table_name="bills")
    op.drop_index("ix_bills_company_status", table_name="bills")
    op.drop_index("ix_bills_customer_period_unique", table_name="bills")
    op.drop_index("ix_bills_sequence_unique", table_name="bills")
    op.drop_index("ix_bills_number_unique", table_name="bills")
    op.drop_table("bills")

    op.drop_index("ix_billing_runs_period", table_name="billing_runs")
    op.drop_index("ix_billing_runs_company", table_name="billing_runs")
    op.drop_index("ix_billing_runs_status", table_name="billing_runs")
    op.drop_table("billing_runs")

    op.drop_table("billing_settings")
