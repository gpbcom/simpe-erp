"""Name the party that owes an invoice, and what the invoice covers.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-11

Notes:
    An invoice knew one party: the person cared for. That is true of a household
    paying its own bills and false of every funded arrangement — an APA share
    billed to a conseil départemental, a mutuelle, an employer — and the
    electronic-invoicing reform makes the distinction load-bearing rather than
    cosmetic. The buyer's identifier is what a structured invoice is *routed*
    on, and the regime itself follows the buyer: a professional is transmitted
    through a platform, a private individual is reported.

    **Everything is backfilled, and losslessly.** Every invoice that exists
    today was billed to the household it was delivered to, so the recipient
    block is filled from the customer columns beside it and
    ``recipient_kind`` is ``individual`` for all of them. That is not a default
    standing in for missing data — it is what those rows have always meant.

    ``operation_nature`` is backfilled to ``services``, which is everything this
    agency sells. It decides when the VAT falls due, so backfilling it to goods
    would move the exigibility of every historical invoice by a month.

    **The coordinate columns are the surprising part.** Nothing routes to a
    billing address, and they exist anyway: ``PostalAddress`` geocodes while it
    validates and skips the lookup only when a coordinate or a failure code is
    already present. Without them, reading any invoice would fire a blocking
    request to Nominatim.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

#: Name, type, nullability. The recipient block mirrors the customer block
#: already on the table, plus the identifiers only a professional carries.
COLUMNS = (
    ("recipient_kind", sa.String(length=16), False),
    ("recipient_name", sa.String(length=255), False),
    ("recipient_street", sa.String(length=255), False),
    ("recipient_postal_code", sa.String(length=16), False),
    ("recipient_city", sa.String(length=128), False),
    ("recipient_country", sa.String(length=128), False),
    ("recipient_latitude", sa.Float(), True),
    ("recipient_longitude", sa.Float(), True),
    ("recipient_geocoding_error", sa.String(length=64), True),
    ("recipient_siren", sa.String(length=9), True),
    ("recipient_vat_number", sa.String(length=20), True),
    ("recipient_service_code", sa.String(length=64), True),
    ("recipient_share_ttc", sa.Numeric(precision=12, scale=2), True),
    ("operation_nature", sa.String(length=16), False),
)

#: What an existing row means, expressed as a copy from the columns beside it.
BACKFILL = """
    UPDATE bills SET
        recipient_kind = 'individual',
        recipient_name = customer_full_name,
        recipient_street = street,
        recipient_postal_code = postal_code,
        recipient_city = city,
        recipient_country = country,
        recipient_latitude = latitude,
        recipient_longitude = longitude,
        recipient_geocoding_error = geocoding_error,
        operation_nature = 'services'
"""


def upgrade() -> None:
    """Add the recipient block and the operation nature, then backfill both.

    Notes:
        The mandatory columns are added nullable, filled, and only then made
        ``NOT NULL``. Adding them non-nullable in one step fails on any table
        that already holds an invoice, which is every deployment that has issued
        one — and the correct value for those rows is knowable, so there is no
        reason to leave the constraint off.
    """
    for name, column_type, _nullable in COLUMNS:
        op.add_column("bills", sa.Column(name, column_type, nullable=True))
    op.execute(BACKFILL)
    # Batch mode, because the migration test runs against SQLite and SQLite has
    # no ALTER COLUMN. On PostgreSQL this emits the plain ALTER; on SQLite
    # Alembic rebuilds the table around the new constraints. One batch rather
    # than seven, so the table is rebuilt once. The bare op would pass in
    # production and fail the one test that checks the migrations and the ORM
    # still agree — migration 0008 hit exactly this.
    with op.batch_alter_table("bills") as batch:
        for name, column_type, nullable in COLUMNS:
            if not nullable:
                batch.alter_column(name, existing_type=column_type, nullable=False)


def downgrade() -> None:
    """Drop the recipient block and the operation nature.

    Notes:
        Lossy in one direction only, and it is worth naming: an invoice billed
        to a département goes back to naming the household, which is not what
        the document said. The invoices themselves survive — their documents are
        already rendered and stored — but the record of who was asked to pay
        does not.
    """
    for name, _column_type, _nullable in reversed(COLUMNS):
        op.drop_column("bills", name)
