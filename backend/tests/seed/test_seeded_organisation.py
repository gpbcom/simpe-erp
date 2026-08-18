from __future__ import annotations

# Standard library imports
from typing import List, Tuple

# Third-party imports
import pytest

# First-party imports
from models.enums import AgencyType
from models.geo.postal_address import PostalAddress
from models.organisation.agency.agency import Agency
from seed.dataset import Dataset


class TestTheSeededSites:
    """Tests that the seeded company has exactly one head office.

    Notes:
        **This is the guard on a fixture nothing downstream would question.**
        The seeder attaches every seeded person to whichever site it finds
        flagged as the head office, and forms the one seeded team there. With no
        head office it attaches nobody, forms no team, and then every quote it
        writes names a team that does not exist — a database that comes up, a
        stack that starts, and a planning run that silently schedules nothing.

        With *two*, the partial unique index refuses the second insert and the
        seed aborts halfway through, which is loud but no less broken.
    """

    @pytest.fixture
    def sites(self) -> Tuple[Tuple, ...]:
        """Return the seeded sites.

        Returns:
            Tuple[Tuple, ...]: The rows of :attr:`Dataset.AGENCIES`.
        """
        return Dataset.AGENCIES

    def test_exactly_one_site_is_the_head_office(
        self, sites: Tuple[Tuple, ...]
    ) -> None:
        """One, and only one.

        Args:
            sites (Tuple[Tuple, ...]): The seeded sites.
        """
        head_offices = [row for row in sites if row[1] is AgencyType.HQ]

        assert len(head_offices) == 1

    def test_more_than_one_site_is_seeded(self, sites: Tuple[Tuple, ...]) -> None:
        """A company that is only its head office demonstrates nothing.

        Notes:
            The second site is the whole reason the sites screen has anything to
            show: with one row a reviewer cannot tell whether the screen lists
            sites or simply restates the company.
        """
        assert len(sites) > 1

    def test_every_site_carries_its_coordinates(self, sites: Tuple[Tuple, ...]) -> None:
        """Nothing in the seeder may geocode.

        Args:
            sites (Tuple[Tuple, ...]): The seeded sites.

        Notes:
            :class:`~models.geo.postal_address.PostalAddress` resolves during
            validation, so a site row missing its latitude and longitude would
            fire a live request at Nominatim's public instance on every
            ``compose up``.
        """
        assert all(
            isinstance(row[5], float) and isinstance(row[6], float) for row in sites
        )

    def test_the_names_are_distinct(self, sites: Tuple[Tuple, ...]) -> None:
        """A company may not hold two sites of one name.

        Notes:
            The unique index says so too. This says it before a developer sees
            an opaque integrity error halfway through a seed.
        """
        names = [row[0] for row in sites]

        assert len(set(names)) == len(names)

    def test_a_branch_may_carry_no_legal_identity(
        self, sites: Tuple[Tuple, ...]
    ) -> None:
        """Every seeded branch is buildable as the model insists it be.

        Args:
            sites (Tuple[Tuple, ...]): The seeded sites.

        Notes:
            An :class:`~models.organisation.agency.agency.Agency` *is* a
            :class:`~models.organisation.companies.company.Company`, and the
            model refuses a branch carrying the SIRET or the bank account. This
            builds each seeded row to prove the dataset can actually be stored,
            rather than discovering it when the seeder is halfway through.
        """
        for name, agency_type, street, postal_code, city, lat, lon in sites:
            agency = Agency(
                company_id="company-1",
                name=name,
                agency_type=agency_type,
                address=PostalAddress(
                    street=street,
                    postal_code=postal_code,
                    city=city,
                    country="France",
                    latitude=lat,
                    longitude=lon,
                ),
            )
            assert agency.holds_legal_identity() is False


class TestTheSeededTeam:
    """Tests that the one seeded team can actually be formed."""

    @pytest.fixture
    def staff_emails(self) -> List[str]:
        """Return the addresses the seeder creates staff accounts for.

        Returns:
            List[str]: The three back-office addresses.

        Notes:
            Restated here rather than imported, because the seeder builds them
            inline. That duplication is the point: if the seeder's list changes
            and this one does not, the test below fails and says which.
        """
        return [
            "admin@simple-erp.fr",
            "manager@simple-erp.fr",
            "manager2@simple-erp.fr",
        ]

    def test_the_team_manager_is_an_account_the_seeder_creates(
        self, staff_emails: List[str]
    ) -> None:
        """The team names a manager, and that account must exist by then.

        Args:
            staff_emails (List[str]): The seeded staff addresses.

        Notes:
            **Nothing downstream reports this.** The seeder logs an error and
            returns without forming the team, and every quote it then writes
            names a team identifier no row carries — so the stack comes up, the
            screens render, and no planning run ever finds any work.
        """
        assert Dataset.TEAM_MANAGER_EMAIL in staff_emails

    def test_the_team_has_a_name(self) -> None:
        """An unnamed team is an unlabelled row in every picker."""
        assert Dataset.TEAM_NAME.strip()
