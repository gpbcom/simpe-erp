from __future__ import annotations

# Standard library imports
import json
import logging
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.configuration.observability_config import ObservabilityConfig
from models.enums import UnplacedReason
from service.observability.json_formatter import JsonLogFormatter
from service.observability.metrics import ApplicationMetrics
from service.observability.probe_server import ProbeServer
from service.observability.trace_context import TraceContext


def _record(**extra: Any) -> logging.LogRecord:
    """Build a log record the way ``logging`` does.

    Args:
        **extra: Fields a caller attached with ``extra=``.

    Returns:
        logging.LogRecord: The record.
    """
    record = logging.LogRecord(
        name="service.planning",
        level=logging.INFO,
        pathname="/app/service/planning/plannings.py",
        lineno=412,
        msg="Planning run %s wrote %d visit(s).",
        args=("run-1", 42),
        exc_info=None,
        func="_store",
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _rendered(formatter: JsonLogFormatter, record: logging.LogRecord) -> Dict[str, Any]:
    """Render a record and parse it back.

    Args:
        formatter (JsonLogFormatter): The formatter under test.
        record (logging.LogRecord): The record to render.

    Returns:
        Dict[str, Any]: The parsed object.
    """
    return json.loads(formatter.format(record))


class TestJsonLogFormatter:
    """Tests for the formatter a container's stdout is read through."""

    def test_a_record_renders_as_one_line(self) -> None:
        """**A pipeline splits on newlines, so a second line is a second entry.**"""
        rendered = JsonLogFormatter().format(_record())

        assert "\n" not in rendered

    def test_the_message_is_interpolated(self) -> None:
        """``%s`` arguments are resolved, as the house logging style relies on."""
        assert _rendered(JsonLogFormatter(), _record())["message"] == (
            "Planning run run-1 wrote 42 visit(s)."
        )

    def test_the_record_carries_where_it_came_from(self) -> None:
        """Logger, level, function and line, under stable names."""
        payload = _rendered(JsonLogFormatter(), _record())

        assert payload["logger"] == "service.planning"
        assert payload["level"] == "INFO"
        assert payload["function"] == "_store"
        assert payload["line"] == 412

    def test_the_timestamp_carries_an_offset(self) -> None:
        """A naive timestamp is one nobody can line up against another service."""
        assert _rendered(JsonLogFormatter(), _record())["timestamp"].endswith("+00:00")

    def test_context_becomes_queryable_fields(self) -> None:
        """**This is what the formatter is for.**

        Notes:
            ``company_id`` as a field is something a query can group by;
            interpolated into the sentence it is something to grep for, and the
            grep is wrong the first time somebody rewords the message.
        """
        payload = _rendered(
            JsonLogFormatter(), _record(company_id="company-1", run_id="run-1")
        )

        assert payload["company_id"] == "company-1"
        assert payload["run_id"] == "run-1"

    def test_the_machinery_s_own_attributes_are_not_context(self) -> None:
        """Every record carries these; none of them is something a caller added."""
        payload = _rendered(JsonLogFormatter(), _record())

        for noise in ("msg", "args", "pathname", "levelno", "relativeCreated"):
            assert noise not in payload

    def test_a_traceback_stays_one_record(self) -> None:
        """Eight lines of stack must not become eight entries.

        Notes:
            Appended to the message it would also be the seven unparseable ones
            that are *not* the entry carrying the error.
        """
        try:
            raise RuntimeError("relation does not exist")
        except RuntimeError:
            record = _record()
            record.exc_info = __import__("sys").exc_info()

        rendered = JsonLogFormatter().format(record)
        payload = json.loads(rendered)

        assert "\n" not in rendered
        assert "RuntimeError" in payload["exception"]

    def test_the_service_is_named_only_when_asked(self) -> None:
        """Two sources disagreeing about the service name is worse than one.

        Notes:
            The collector may be adding it from the pod's labels, so the
            formatter writes one only when it has been given one.
        """
        assert "service" not in _rendered(JsonLogFormatter(), _record())
        assert (
            _rendered(JsonLogFormatter("simple-erp-api"), _record())["service"]
            == "simple-erp-api"
        )

    def test_an_unserialisable_value_does_not_lose_the_record(self) -> None:
        """A log line is not worth an exception in the logging machinery."""
        payload = _rendered(JsonLogFormatter(), _record(period=object()))

        assert "object object at" in payload["period"]


class TestApplicationMetrics:
    """Tests for the figures only this application knows."""

    def test_two_instances_do_not_collide(self) -> None:
        """**Its own registry, not the global default.**

        Notes:
            On the default registry the second instance raises a
            duplicate-timeseries error at construction — which in a suite means
            a test failing at a distance, naming neither itself nor the test
            that registered first.
        """
        ApplicationMetrics()
        ApplicationMetrics()

    def test_every_unplaced_reason_starts_at_zero(self) -> None:
        """**A counter that has never fired is absent, not zero.**

        Notes:
            An absent series makes `rate()` return nothing rather than zero, so
            an alert on "visits are being dropped for want of a qualification"
            would stay silent on exactly the deployment where it has never yet
            happened — which is the one it exists for.
        """
        body, _ = ApplicationMetrics().render()
        rendered = body.decode()

        for reason in UnplacedReason:
            assert f'planning_run_unplaced_total{{reason="{reason.value}"}} 0.0' in (
                rendered
            )

    def test_a_missing_certification_is_counted(self) -> None:
        """The reason the certification feature is watched by."""
        metrics = ApplicationMetrics()

        metrics.record_unplaced(UnplacedReason.MISSING_CERTIFICATION.value)

        body, _ = metrics.render()
        assert (
            'planning_run_unplaced_total{reason="missing-certification"} 1.0'
            in body.decode()
        )

    def test_a_run_records_its_duration_and_its_size(self) -> None:
        """Both, because a fast run that placed nothing is not a good run."""
        metrics = ApplicationMetrics()

        metrics.record_run("succeeded", 12.5, scheduled=42)

        rendered = ApplicationMetrics.render(metrics)[0].decode()
        assert 'planning_run_duration_seconds_count{outcome="succeeded"} 1.0' in rendered
        assert "planning_run_scheduled_visits_sum 42.0" in rendered

    def test_a_failed_run_records_no_size(self) -> None:
        """It wrote nothing, and zero would be indistinguishable from an empty week."""
        metrics = ApplicationMetrics()

        metrics.record_run("failed", 3.0)

        assert "planning_run_scheduled_visits_count 0.0" in metrics.render()[0].decode()

    def test_a_handled_message_is_counted_by_role_and_topic(self) -> None:
        """Which role is slow, and on which topic, is the question asked of this."""
        metrics = ApplicationMetrics()

        metrics.record_message(
            "planning", "planning.run.requested", "handled", 12.6
        )

        rendered = metrics.render()[0].decode()
        assert 'role="planning"' in rendered
        assert 'routing_key="planning.run.requested"' in rendered

    def test_no_metric_is_labelled_by_a_person(self) -> None:
        """**A label whose values grow with the workforce is a series per person.**

        Notes:
            That is the usual way a metrics store is taken down by the
            application it is watching. Asserted on the declared label *names*
            rather than on the rendered text: ``no-assistant-available`` is a
            reason a visit went unplaced, and a text search would read it as a
            per-assistant label and fail for the wrong reason.
        """
        metrics = ApplicationMetrics()
        declared = {
            name
            for metric in (
                metrics.planning_run_duration,
                metrics.planning_run_unplaced,
                metrics.messages_handled,
                metrics.message_duration,
            )
            for name in metric._labelnames
        }

        assert declared.isdisjoint(
            {"hca_id", "customer_id", "company_id", "user_id", "email", "quote_id"}
        )

    def test_the_labels_that_are_declared_are_bounded(self) -> None:
        """Every label's values come from a fixed set, not from the data.

        Notes:
            Roles and reasons are enums; outcomes and topics are a handful of
            constants. That is what keeps the series count a property of the
            code rather than of how many agencies signed up.
        """
        metrics = ApplicationMetrics()

        assert set(metrics.planning_run_unplaced._labelnames) == {"reason"}
        assert set(metrics.messages_handled._labelnames) == {
            "role",
            "routing_key",
            "outcome",
        }

    def test_the_content_type_comes_back_with_the_body(self) -> None:
        """Prometheus content-negotiates; text/plain parses as one bad sample."""
        _, content_type = ApplicationMetrics().render()

        assert "openmetrics-text" in content_type


class TestProbeServer:
    """Tests for the port that makes a worker schedulable."""

    def _server(self, ready: bool, **overrides: Any) -> ProbeServer:
        """Build a probe server over a fixed readiness answer.

        Args:
            ready (bool): What readiness reports.
            **overrides: Configuration overrides.

        Returns:
            ProbeServer: The server under test.
        """
        return ProbeServer(
            config=ObservabilityConfig(**overrides),
            metrics=ApplicationMetrics(),
            is_ready=lambda: ready,
        )

    def test_health_answers_from_memory(self) -> None:
        """**Liveness asks whether the process is alive, and nothing else.**

        Notes:
            A liveness probe that consulted the broker would restart every
            worker during a broker outage — which does not bring the broker
            back, and loses every in-flight solve on the way.
        """
        status, _, _ = self._server(ready=False)._answer("/health")

        assert status == 200

    def test_ready_answers_for_the_broker(self) -> None:
        """Readiness is whether this worker can actually consume."""
        assert self._server(ready=True)._answer("/ready")[0] == 200
        assert self._server(ready=False)._answer("/ready")[0] == 503

    def test_metrics_are_served_with_their_own_content_type(self) -> None:
        """The exposition format, not JSON."""
        status, body, content_type = self._server(ready=True)._answer("/metrics")

        assert status == 200
        assert b"planning_run_unplaced_total" in body
        assert "openmetrics-text" in content_type

    def test_an_unknown_path_is_a_404(self) -> None:
        """There is no routing here, and no catch-all either."""
        assert self._server(ready=True)._answer("/admin")[0] == 404

    @pytest.mark.asyncio
    async def test_nothing_is_served_when_metrics_are_off(self) -> None:
        """The switch is honoured rather than merely hiding ``/metrics``."""
        server = self._server(ready=True, metrics_enabled=False)

        await server.start()

        assert server.server is None

    @pytest.mark.asyncio
    async def test_a_port_that_cannot_be_bound_does_not_stop_the_worker(self) -> None:
        """**Losing the metrics is bad; refusing to do the work is worse.**

        Notes:
            Port 1 needs privileges this process does not have, which is the
            same shape as the port already being taken by a sidecar.
        """
        server = self._server(ready=True, metrics_port=1)

        await server.start()

        assert server.server is None

    @pytest.mark.asyncio
    async def test_it_serves_and_stops(self) -> None:
        """The ordinary lifecycle, on a port the kernel chooses."""
        server = self._server(ready=True, metrics_port=18321)

        await server.start()
        assert server.server is not None

        await server.close()
        assert server.server is None

    @pytest.mark.asyncio
    async def test_closing_a_server_that_never_started_is_safe(self) -> None:
        """A worker that failed to bind still runs its shutdown path."""
        await self._server(ready=True, metrics_enabled=False).close()


class TestTraceContext:
    """Tests for carrying a trace across the broker."""

    def test_nothing_is_carried_when_nothing_is_traced(self) -> None:
        """**``None`` is the ordinary answer, not a failure.**

        Notes:
            OpenTelemetry is an optional dependency. Without it — which is every
            deployment until tracing is turned on — this is a no-op, messages
            carry no context, handlers start their own spans, and nothing fails.
        """
        assert TraceContext().current() is None

    def test_nothing_is_restored_from_an_absent_context(self) -> None:
        """A message from before the field existed restores to nothing."""
        assert TraceContext().restore(None) is None
        assert TraceContext().restore("") is None

    def test_the_header_is_the_one_the_specification_names(self) -> None:
        """A different spelling propagates to nothing, silently."""
        assert TraceContext.HEADER == "traceparent"
