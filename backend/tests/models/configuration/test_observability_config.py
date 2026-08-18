from __future__ import annotations

# Standard library imports

# Third-party imports
import pytest

# First-party imports
from models.configuration.exceptions import (
    MTInvalidObservabilityConfigException,
    MTObservabilityConfigInvalidEndpoint,
    MTObservabilityConfigInvalidFlag,
    MTObservabilityConfigInvalidPort,
    MTObservabilityConfigInvalidServiceName,
    MTObservabilityConfigInvalidTimeout,
)
from models.configuration.observability_config import ObservabilityConfig
from tests.annotations import ModelInput


class TestObservabilityConfig:
    """Tests for what a process reports about itself."""

    # ------------------------------------------------------------------ #
    #  Defaults
    # ------------------------------------------------------------------ #

    def test_metrics_are_on_and_tracing_is_off_by_default(self) -> None:
        """**The two switch independently, and the defaults say why.**

        Notes:
            Metrics are cheap and need nothing to receive them, so they are on
            everywhere including a laptop. Tracing needs a collector, and a
            process exporting to one that is not there pays a failed connection
            on every request — so it is opted into by a deployment that has one.
        """
        config = ObservabilityConfig()

        assert config.metrics_enabled is True
        assert config.tracing_enabled is False

    def test_the_port_is_not_one_the_application_already_uses(self) -> None:
        """The worker has no HTTP surface of its own to share.

        Notes:
            The API serves its metrics on the port it already listens on. This
            is the worker's, which otherwise has no port at all and therefore no
            readiness probe either.
        """
        assert ObservabilityConfig().metrics_port not in (8000, 5432, 5672, 9000)

    # ------------------------------------------------------------------ #
    #  service_name
    # ------------------------------------------------------------------ #

    def test_the_service_name_is_stripped(self) -> None:
        """Surrounding whitespace is removed."""
        assert ObservabilityConfig(service_name="  simple-erp  ").service_name == (
            "simple-erp"
        )

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_unusable_service_name_is_refused(
        self, invalid_name: ModelInput
    ) -> None:
        """A blank name does not fail. It merges every process into one series.

        Notes:
            That is the quiet failure this refuses: a dashboard where the API's
            latency and the planning worker's are the same line, and nobody
            notices because the line looks plausible.
        """
        with pytest.raises(MTObservabilityConfigInvalidServiceName):
            ObservabilityConfig(service_name=invalid_name)

    def test_each_process_names_itself_from_the_shared_name(self) -> None:
        """Four processes share one image and one configuration file.

        Notes:
            The file carries the application's name and the entry point adds
            what it is. Naming each process in the file instead would mean four
            files, or one file each entry point had to ignore most of.
        """
        config = ObservabilityConfig(service_name="simple-erp")

        assert config.named("worker-planning").service_name == (
            "simple-erp-worker-planning"
        )

    def test_naming_a_process_leaves_the_original_alone(self) -> None:
        """A copy, not a mutation: the config is shared between entry points."""
        config = ObservabilityConfig(service_name="simple-erp")

        config.named("api")

        assert config.service_name == "simple-erp"

    # ------------------------------------------------------------------ #
    #  The switches
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", ["metrics_enabled", "tracing_enabled"])
    @pytest.mark.parametrize(
        "invalid_flag",
        [
            pytest.param("false", id="Invalid - string false"),
            pytest.param("true", id="Invalid - string true"),
            pytest.param(0, id="Invalid - int"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_a_switch_must_be_a_real_boolean(
        self, field: str, invalid_flag: ModelInput
    ) -> None:
        """``"false"`` is truthy, and reading it leniently is the whole risk."""
        with pytest.raises(MTObservabilityConfigInvalidFlag):
            ObservabilityConfig(**{field: invalid_flag})

    # ------------------------------------------------------------------ #
    #  otlp_endpoint
    # ------------------------------------------------------------------ #

    def test_an_absolute_endpoint_is_accepted(self) -> None:
        """The ordinary case."""
        config = ObservabilityConfig(otlp_endpoint="https://collector:4317")

        assert config.otlp_endpoint == "https://collector:4317"

    @pytest.mark.parametrize(
        "invalid_endpoint",
        [
            pytest.param("collector:4317", id="Invalid - no scheme"),
            pytest.param("/v1/traces", id="Invalid - relative"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_an_unusable_endpoint_is_refused(
        self, invalid_endpoint: ModelInput
    ) -> None:
        """A relative endpoint is accepted by the exporter and never resolves.

        Notes:
            The symptom is traces that stop arriving, with nothing in the logs.
        """
        with pytest.raises(MTObservabilityConfigInvalidEndpoint):
            ObservabilityConfig(otlp_endpoint=invalid_endpoint)

    def test_the_endpoint_is_checked_even_when_tracing_is_off(self) -> None:
        """Turning tracing on is one flag, not a flag and a debugging session."""
        with pytest.raises(MTObservabilityConfigInvalidEndpoint):
            ObservabilityConfig(tracing_enabled=False, otlp_endpoint="collector")

    # ------------------------------------------------------------------ #
    #  metrics_port
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_port",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(65536, id="Invalid - beyond the range"),
            pytest.param("9100", id="Invalid - string"),
            pytest.param(9100.0, id="Invalid - float"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_an_unusable_port_is_refused(self, invalid_port: ModelInput) -> None:
        """Zero is refused rather than read as "pick one".

        Notes:
            A port the process chose at random is one nothing can be configured
            to scrape.
        """
        with pytest.raises(MTObservabilityConfigInvalidPort):
            ObservabilityConfig(metrics_port=invalid_port)

    # ------------------------------------------------------------------ #
    #  export_timeout_seconds
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_timeout",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1.0, id="Invalid - negative"),
            pytest.param("10", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_unusable_timeout_is_refused(self, invalid_timeout: ModelInput) -> None:
        """Zero is not "wait forever". It fails every export immediately."""
        with pytest.raises(MTObservabilityConfigInvalidTimeout):
            ObservabilityConfig(export_timeout_seconds=invalid_timeout)

    # ------------------------------------------------------------------ #
    #  Shape
    # ------------------------------------------------------------------ #

    def test_the_port_ceiling_is_not_a_setting(self) -> None:
        """``MAX_PORT`` is a ``ClassVar``, so it is not part of the file.

        Notes:
            A bare annotation would make it a field, and it would then appear in
            every dumped configuration as though somebody were meant to choose
            it.
        """
        assert "MAX_PORT" not in ObservabilityConfig.model_fields

    def test_there_is_no_sampling_rate(self) -> None:
        """Sampling belongs to the collector, which sees every service.

        Notes:
            A rate set per process produces traces that are complete for one hop
            and missing the next, which is worse than no traces: it looks like
            the missing service never ran.
        """
        assert "sampling_rate" not in ObservabilityConfig.model_fields

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTObservabilityConfigInvalidEndpoint,
            MTObservabilityConfigInvalidFlag,
            MTObservabilityConfigInvalidPort,
            MTObservabilityConfigInvalidServiceName,
            MTObservabilityConfigInvalidTimeout,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the section's own family base."""
        assert issubclass(exception_class, MTInvalidObservabilityConfigException)
