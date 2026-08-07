from __future__ import annotations

# Third-party imports
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# First-party imports
from api.dependencies import get_metrics
from api.middleware.auth_middleware import AuthMiddleware
from api.observability import router as observability_router
from service.observability.metrics import ApplicationMetrics


@pytest.fixture
def registry() -> ApplicationMetrics:
    """Return a registry of this instance's own.

    Returns:
        ApplicationMetrics: A fresh registry.
    """
    return ApplicationMetrics()


@pytest.fixture
def client(registry: ApplicationMetrics) -> TestClient:
    """Return a client over the observability router alone.

    Args:
        registry (ApplicationMetrics): The registry the endpoint renders.

    Returns:
        TestClient: The client under test.
    """
    app = FastAPI()
    app.include_router(observability_router)
    app.dependency_overrides[get_metrics] = lambda: registry
    return TestClient(app)


class TestMetricsEndpoint:
    """Tests for the figures a scraper reads off an API instance."""

    def test_it_serves_the_exposition_format(self, client: TestClient) -> None:
        """The content type is what Prometheus negotiates on.

        Notes:
            Served as ``text/plain`` it parses as a single malformed sample, and
            the scrape succeeds while collecting nothing.
        """
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "openmetrics-text" in response.headers["content-type"]

    def test_it_carries_the_application_s_own_figures(
        self, client: TestClient, registry: ApplicationMetrics
    ) -> None:
        """What is recorded is what is served."""
        registry.record_run("succeeded", 12.5, scheduled=42)

        body = client.get("/metrics").text

        assert 'planning_run_duration_seconds_count{outcome="succeeded"} 1.0' in body

    def test_it_is_absent_from_the_openapi_document(self, client: TestClient) -> None:
        """**Not part of the API a client programs against.**

        Notes:
            Included, it would put a non-JSON endpoint in a schema every client
            generator reads — and the drift job would then treat a metrics
            change as an API change.
        """
        assert "/metrics" not in client.get("/openapi.json").json()["paths"]

    def test_no_label_identifies_a_person(self, client: TestClient) -> None:
        """**This is what makes serving it unauthenticated defensible.**

        Notes:
            A scraper has no account to sign in with, so the endpoint is exempt
            from the bearer-token middleware. What that exemption is safe
            against is the body carrying nothing about anybody — counts and
            durations, and labels drawn from enums.
        """
        body = client.get("/metrics").text

        for identifier in ("@", "hca_id=", "customer_id=", "company_id="):
            assert identifier not in body


class TestMetricsIsReachableWithoutACredential:
    """Tests for the middleware exemption a scraper depends on."""

    def test_it_is_exempt_from_authentication(self) -> None:
        """A scraper carries no bearer token and never will.

        Notes:
            Asserted against the middleware's own list rather than by driving a
            request, because the exemption is the thing being pinned: an
            endpoint that answered 401 would leave a target permanently down
            and the figures permanently absent, which reads as a service that
            is not running.
        """
        assert "/metrics" in AuthMiddleware.EXEMPT_PATHS

    def test_the_probes_are_exempt_too(self) -> None:
        """The three of them travel together, and for the same reason."""
        for path in ("/health", "/ready", "/metrics"):
            assert path in AuthMiddleware.EXEMPT_PATHS
