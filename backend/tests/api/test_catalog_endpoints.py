from __future__ import annotations

# Standard library imports
from decimal import Decimal

# Standard library imports
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_app_config,
    get_intervention_type_service,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.intervention_types.intervention_types import router as catalog_router
from models.auth.user import User
from models.configuration.app_config import AppConfig
from models.configuration.pricing_config import PricingConfig
from models.catalog.intervention_type import InterventionType
from models.enums import ServiceCategory, UserRole


def _user(role: UserRole = UserRole.MANAGER) -> User:
    """Build an account.

    Args:
        role (UserRole): The role to grant.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id="user-1",
        email="manager@example.com",
        full_name="Nathalie Blanchard",
        hashed_password="$2b$12$abcdefghijklmnopqrstuv",
        role=role,
    )


def _entry() -> InterventionType:
    """Build a catalogue entry.

    Returns:
        InterventionType: The entry.
    """
    return InterventionType(
        id="type-1",
        name="Aide administrative",
        code="ADMIN",
        description="Aide administrative au domicile du beneficiaire.",
        service_category=ServiceCategory.COMFORT,
        base_hourly_rate_ht=Decimal("31.905"),
        is_active=True,
    )


def _catalogue_client(service: MagicMock) -> TestClient:
    """Build a client over the catalogue router with a service double.

    Args:
        service (MagicMock): The catalogue service double.

    Returns:
        TestClient: The client.
    """
    app = FastAPI()
    app.include_router(catalog_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_manager_user] = lambda: _user()
    app.dependency_overrides[get_app_config] = lambda: AppConfig()
    app.dependency_overrides[get_intervention_type_service] = lambda: service
    return TestClient(app)


def _client(config: AppConfig) -> TestClient:
    """Build a client over the catalogue router.

    Args:
        config (AppConfig): The configuration the routes read.

    Returns:
        TestClient: A client with the guards and services overridden.
    """
    app = FastAPI()
    app.include_router(catalog_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_manager_user] = lambda: _user()
    app.dependency_overrides[get_app_config] = lambda: config
    app.dependency_overrides[get_intervention_type_service] = lambda: None
    return TestClient(app)


class TestPricingRules:
    """Tests for the rules the catalogue screen prices against."""

    def test_the_running_rates_are_published(self) -> None:
        """The ordinary case: what this deployment actually charges."""
        config = AppConfig()

        body = _client(config).get("/api/v1/intervention-types/pricing-rules").json()

        assert (
            Decimal(body["base_hourly_rate_ht"]) == config.pricing.base_hourly_rate_ht
        )

    def test_every_service_category_carries_its_vat_rate(self) -> None:
        """The screen labels each entry with the VAT its category implies."""
        body = (
            _client(AppConfig()).get("/api/v1/intervention-types/pricing-rules").json()
        )

        assert set(body["vat_rates"]) == {c.value for c in ServiceCategory}
        for category in ServiceCategory:
            assert Decimal(body["vat_rates"][category.value]) == category.vat_rate()

    def test_the_path_is_not_read_as_an_identifier(self) -> None:
        """**The route-ordering trap this endpoint sits on.**

        Notes:
            ``/pricing-rules`` and ``/{type_id}`` match the same shape, and
            routes are tried in registration order. With the parameterised one
            first this request would be read as "fetch the intervention type
            called *pricing-rules*" and answered 404 — naming a type nobody
            asked for, which is a confusing way to learn about route ordering.
        """
        response = _client(AppConfig()).get("/api/v1/intervention-types/pricing-rules")

        assert response.status_code == 200
        assert "base_hourly_rate_ht" in response.json()

    def test_weekday_surcharges_are_named_not_numbered(self) -> None:
        """The screen prints the day, so it needs a name."""
        config = AppConfig()
        config.pricing = PricingConfig(weekday_surcharges={"sunday": "1.25"})

        body = _client(config).get("/api/v1/intervention-types/pricing-rules").json()

        assert body["weekday_surcharges"] == {"sunday": "1.25"}

    def test_an_agency_with_no_surcharges_is_served_empty_collections(self) -> None:
        """Not an error, and not a missing key: a real state.

        Notes:
            The screen renders these as "None" rather than as a blank area, so
            it needs the key present and empty rather than absent.
        """
        config = AppConfig()
        config.pricing = PricingConfig(weekday_surcharges={}, holiday_surcharges=[])

        body = _client(config).get("/api/v1/intervention-types/pricing-rules").json()

        assert body["weekday_surcharges"] == {}
        assert body["holiday_surcharges"] == []

    def test_the_route_is_manager_gated(self) -> None:
        """An assistant does not set what the agency charges.

        Notes:
            Read from the route's declared dependencies rather than by calling
            it as an assistant: the guard reads request state that only the
            middleware sets, so an unauthenticated call answers 500 and would
            pass this test for the wrong reason.
        """
        matching = [
            route
            for route in catalog_router.routes
            if getattr(route, "path", None)
            == "/api/v1/intervention-types/pricing-rules"
        ]
        assert matching, "The pricing-rules route is not registered."

        guards = {
            dependency.call
            for dependency in matching[0].dependant.dependencies
            if dependency.call is not None
        }
        assert get_manager_user in guards

    @pytest.mark.parametrize("rate", ["0", "-1"])
    def test_a_configuration_with_an_impossible_rate_never_reaches_the_screen(
        self, rate: str
    ) -> None:
        """A rate of zero would publish "everything inheriting is free".

        Args:
            rate (str): The impossible rate.

        Notes:
            The configuration refuses one at load. This asserts the refusal
            rather than assuming it: the catalogue screen shows this figure as
            the one a manager decides every other rate against.
        """
        with pytest.raises(Exception):
            PricingConfig(base_hourly_rate_ht=rate)


class TestPartialCatalogueUpdate:
    """Tests for changing part of a catalogue entry."""

    def _service(self) -> MagicMock:
        """Return a catalogue service that echoes what it is asked to store.

        Returns:
            MagicMock: The service double.
        """
        service = MagicMock()
        service.get = AsyncMock(return_value=_entry())
        service.update = AsyncMock(side_effect=lambda entry: entry)
        return service

    def test_a_body_without_a_code_is_accepted(self) -> None:
        """**The 422 this route used to answer.**

        Notes:
            The route was declared ``PATCH`` but took a whole
            ``InterventionType``, so a client sending everything it had on
            screen — and no ``code``, because the screen will not let anybody
            change one — was answered ``422: code Field required``. This is the
            exact body from that report.
        """
        service = self._service()

        response = _catalogue_client(service).patch(
            "/api/v1/intervention-types/type-1",
            json={
                "name": "Aide administrative",
                "description": "Aide administrative au domicile du beneficiaire.",
                "service_category": "comfort",
                "base_hourly_rate_ht": "31.905",
                "is_active": True,
            },
        )

        assert response.status_code == 200

    def test_one_field_can_be_changed_without_resending_the_rest(self) -> None:
        """What a PATCH is for."""
        service = self._service()

        body = (
            _catalogue_client(service)
            .patch(
                "/api/v1/intervention-types/type-1",
                json={"base_hourly_rate_ht": "42.50"},
            )
            .json()
        )

        assert Decimal(body["base_hourly_rate_ht"]) == Decimal("42.50")
        assert body["name"] == "Aide administrative"
        assert body["code"] == "ADMIN"

    def test_renaming_leaves_the_rate_alone(self) -> None:
        """**The silent data loss ``exclude_unset`` prevents.**

        Notes:
            ``base_hourly_rate_ht`` is optional, so an omitted one and a
            cleared one both arrive as ``None``. A merge that could not tell
            them apart would reset an entry's rate to the agency default every
            time somebody corrected its spelling — with no error anywhere, and
            the next quote priced differently.
        """
        service = self._service()

        body = (
            _catalogue_client(service)
            .patch("/api/v1/intervention-types/type-1", json={"name": "Aide admin."})
            .json()
        )

        assert Decimal(body["base_hourly_rate_ht"]) == Decimal("31.905")

    def test_clearing_the_rate_means_bill_at_the_agency_rate(self) -> None:
        """The other half: an explicit ``null`` does take effect."""
        service = self._service()

        body = (
            _catalogue_client(service)
            .patch(
                "/api/v1/intervention-types/type-1",
                json={"base_hourly_rate_ht": None},
            )
            .json()
        )

        assert body["base_hourly_rate_ht"] is None

    def test_the_code_cannot_be_changed_through_the_payload(self) -> None:
        """**Every quote line ever written against the entry refers to it.**

        Notes:
            The field is absent from the payload model, so a request naming one
            is parsed without it. The screen locks the input too, but that is a
            courtesy — this is the control.
        """
        service = self._service()

        body = (
            _catalogue_client(service)
            .patch("/api/v1/intervention-types/type-1", json={"code": "HIJACK"})
            .json()
        )

        assert body["code"] == "ADMIN"

    @pytest.mark.parametrize("rate", ["0", "-1", "not-a-number"])
    def test_an_impossible_rate_is_refused(self, rate: str) -> None:
        """A rate of nothing prices every line of the service at nothing.

        Args:
            rate (str): The rejected rate.

        Notes:
            Zero matters most: on screen it is indistinguishable from the empty
            box that means "use the agency rate", which is exactly the mistake
            somebody clearing the field would make.
        """
        service = self._service()

        response = _catalogue_client(service).patch(
            "/api/v1/intervention-types/type-1",
            json={"base_hourly_rate_ht": rate},
        )

        assert response.status_code == 422
        service.update.assert_not_awaited()

    def test_a_blank_name_is_refused(self) -> None:
        """An entry nobody can pick and no customer can read."""
        service = self._service()

        response = _catalogue_client(service).patch(
            "/api/v1/intervention-types/type-1", json={"name": "   "}
        )

        assert response.status_code == 422
        service.update.assert_not_awaited()

    def test_the_identifier_comes_from_the_path(self) -> None:
        """A body naming another entry cannot redirect the write."""
        service = self._service()

        _catalogue_client(service).patch(
            "/api/v1/intervention-types/type-1",
            json={"name": "Renamed", "id": "type-9"},
        )

        assert service.update.await_args.args[0].id == "type-1"
