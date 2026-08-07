from __future__ import annotations

# Standard library imports
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.enums import DatabaseStatus, ProbeStatus
from models.schemas.exceptions import (
    MTHealthResponseInvalidStatus,
    MTInvalidHealthResponseException,
    MTInvalidReadinessResponseException,
    MTReadinessResponseInvalidDatabase,
    MTReadinessResponseInvalidStatus,
)
from models.schemas.responses.observability.health_response import HealthResponse
from models.schemas.responses.observability.readiness_response import ReadinessResponse


class TestHealthResponse:
    """Tests for the HealthResponse schema."""

    def test_it_defaults_to_ok(self) -> None:
        """A liveness probe that answers at all is alive."""
        assert HealthResponse().status is ProbeStatus.OK

    def test_it_serializes_to_the_documented_body(self) -> None:
        """The probe body is exactly what an orchestrator is configured for."""
        assert HealthResponse().model_dump(mode="json") == {"status": "ok"}

    def test_a_status_string_is_coerced(self) -> None:
        """The enum value rebuilds into its enum."""
        assert HealthResponse(status="ok").status is ProbeStatus.OK

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("alive", id="Invalid - unknown"),
            pytest.param(1, id="Invalid - int"),
            pytest.param("", id="Invalid - empty"),
        ],
    )
    def test_an_unknown_status_raises(self, invalid_value: Any) -> None:
        """A status outside the enumeration is rejected."""
        with pytest.raises(MTHealthResponseInvalidStatus):
            HealthResponse(status=invalid_value)

    def test_the_exception_inherits_the_base_class(self) -> None:
        """The field exception belongs to the model's own family."""
        assert issubclass(
            MTHealthResponseInvalidStatus, MTInvalidHealthResponseException
        )


class TestReadinessResponse:
    """Tests for the ReadinessResponse schema."""

    def test_a_ready_instance_reports_both_halves(self) -> None:
        """Readiness names the store's state, not just the verdict."""
        response = ReadinessResponse(
            status=ProbeStatus.OK, database=DatabaseStatus.REACHABLE
        )
        assert response.model_dump(mode="json") == {
            "status": "ok",
            "database": "reachable",
        }

    def test_an_unready_instance_names_the_database(self) -> None:
        """A 503 that names the database saves an operator a log search."""
        response = ReadinessResponse(
            status=ProbeStatus.UNAVAILABLE, database=DatabaseStatus.UNREACHABLE
        )
        assert response.model_dump(mode="json") == {
            "status": "unavailable",
            "database": "unreachable",
        }

    def test_status_strings_are_coerced(self) -> None:
        """Both halves rebuild from their stored values."""
        response = ReadinessResponse(status="ok", database="reachable")
        assert response.status is ProbeStatus.OK
        assert response.database is DatabaseStatus.REACHABLE

    def test_an_unknown_status_raises(self) -> None:
        """A status outside the enumeration is rejected."""
        with pytest.raises(MTReadinessResponseInvalidStatus):
            ReadinessResponse(status="degraded", database="reachable")

    def test_an_unknown_database_state_raises(self) -> None:
        """A database state outside the enumeration is rejected."""
        with pytest.raises(MTReadinessResponseInvalidDatabase):
            ReadinessResponse(status="ok", database="slow")

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTReadinessResponseInvalidDatabase,
            MTReadinessResponseInvalidStatus,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the model's own family."""
        assert issubclass(exception_class, MTInvalidReadinessResponseException)
