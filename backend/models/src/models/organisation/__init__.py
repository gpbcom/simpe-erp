"""How a company is organised: its sites, and the teams working from them.

Two aggregates, deliberate siblings of ``models.organisation.companies``. That package
holds the *legal entity* — the SIRET, the share capital, the account money
is paid into — and those belong to the business rather than to any of the
places it operates from. Folding sites into it would have put "who signs the
invoices" and "which building somebody works in" under one name.
"""
