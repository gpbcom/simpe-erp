from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import ClassVar, Optional, Tuple

# Third-party imports
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST

# First-party imports
from models.enums import UnplacedReason


class ApplicationMetrics:
    """The figures this application publishes about its own work.

    Attributes:
        SOLVE_BUCKETS (ClassVar[Tuple[float, ...]]): Histogram bounds for a
            planning solve, in seconds.
        HANDLE_BUCKETS (ClassVar[Tuple[float, ...]]): Histogram bounds for
            handling one broker message, in seconds.
        registry (CollectorRegistry): This instance's own registry.

    Notes:
        - **Its own registry, not the global default.** The default is process
          -wide and implicitly shared, so two instances of anything registering
          the same metric name raise at import time — which in a test suite
          means the second test to construct one fails, at a distance, with a
          duplicate-timeseries error naming neither test.
        - **Only figures nothing else already has.** Request rates and latencies
          come from the ingress, queue depths from the RabbitMQ exporter, CPU
          and memory from the kubelet. What is here is what only this
          application knows: how long a solve took, why a visit could not be
          placed, and whether the plan that came out was complete.
        - ``planning_run_unplaced_total`` is labelled by
          :class:`~models.enums.UnplacedReason` and **pre-seeded to zero for
          every reason**. A counter that has never fired is absent rather than
          zero, and an absent series makes `rate()` return nothing rather than
          zero — so an alert on "visits are being dropped for want of a
          qualification" would stay silent on precisely the deployment where it
          has never yet happened, which is the one it exists for.
        - Nothing here is labelled by assistant or customer. A label whose
          values grow with the workforce is a new time series per person, and
          the usual way a metrics store is taken down by its own application.
    """

    SOLVE_BUCKETS: ClassVar[Tuple[float, ...]] = (
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        20.0,
        30.0,
        45.0,
        60.0,
    )
    HANDLE_BUCKETS: ClassVar[Tuple[float, ...]] = (
        0.005,
        0.025,
        0.1,
        0.5,
        1.0,
        5.0,
        30.0,
        60.0,
    )

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build the registry and declare every metric on it.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.registry = CollectorRegistry()

        self.planning_run_duration = Histogram(
            "planning_run_duration_seconds",
            "How long a planning run took, end to end.",
            labelnames=("outcome",),
            buckets=self.SOLVE_BUCKETS,
            registry=self.registry,
        )
        self.planning_run_unplaced = Counter(
            "planning_run_unplaced_total",
            "Visits a planning run could not place, by why.",
            labelnames=("reason",),
            registry=self.registry,
        )
        self.planning_run_scheduled = Histogram(
            "planning_run_scheduled_visits",
            "How many visits a planning run wrote.",
            buckets=(0, 1, 10, 50, 100, 250, 500, 1000),
            registry=self.registry,
        )
        self.messages_handled = Counter(
            "worker_messages_total",
            "Broker messages handled, by role, topic and outcome.",
            labelnames=("role", "routing_key", "outcome"),
            registry=self.registry,
        )
        self.message_duration = Histogram(
            "worker_message_duration_seconds",
            "How long handling one broker message took.",
            labelnames=("role", "routing_key"),
            buckets=self.HANDLE_BUCKETS,
            registry=self.registry,
        )
        self.stream_clients = Gauge(
            "notification_stream_clients",
            "Server-sent-event readers this API instance is holding.",
            registry=self.registry,
        )
        for reason in UnplacedReason:
            self.planning_run_unplaced.labels(reason=reason.value)
        self.logger.debug("Application metrics registered.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def record_run(
        self, outcome: str, seconds: float, scheduled: Optional[int] = None
    ) -> None:
        """Record that a planning run finished.

        Args:
            outcome (str): ``succeeded`` or ``failed``.
            seconds (float): How long it took, end to end.
            scheduled (Optional[int]): How many visits it wrote, when it wrote
                any.

        Notes:
            The duration is of the whole run and not of the solve alone. The
            solve has a budget it is held to; what a manager waits for is this,
            and the difference between the two is the database work that is
            worth being able to see separately.
        """
        self.planning_run_duration.labels(outcome=outcome).observe(seconds)
        if scheduled is not None:
            self.planning_run_scheduled.observe(scheduled)
        self.logger.debug(
            "Recorded a %s planning run of %.2fs (%s visit(s)).",
            outcome,
            seconds,
            scheduled if scheduled is not None else "no",
        )

    def record_unplaced(self, reason: str) -> None:
        """Record one visit that could not be placed.

        Args:
            reason (str): An :class:`~models.enums.UnplacedReason` value.

        Notes:
            An unknown reason is counted under its own label rather than
            dropped. A reason added to the enum and not here would otherwise
            vanish from the one view that would have shown it arriving.
        """
        self.planning_run_unplaced.labels(reason=reason).inc()
        self.logger.warning("A visit could not be placed: %s.", reason)

    def record_message(
        self, role: str, routing_key: str, outcome: str, seconds: float
    ) -> None:
        """Record that a broker message was handled.

        Args:
            role (str): The worker role that handled it.
            routing_key (str): The topic it arrived on.
            outcome (str): ``handled``, ``failed`` or ``ignored``.
            seconds (float): How long the handler took.
        """
        self.messages_handled.labels(
            role=role, routing_key=routing_key, outcome=outcome
        ).inc()
        self.message_duration.labels(role=role, routing_key=routing_key).observe(  # noqa: E501
            seconds
        )
        self.logger.debug(
            "Handled %s as %s in %.3fs (%s).",
            routing_key,
            outcome,
            seconds,
            role,  # noqa: E501
        )

    def render(self) -> Tuple[bytes, str]:
        """Render every metric in the exposition format.

        Returns:
            Tuple[bytes, str]: The body and the content type to answer with.

        Notes:
            The content type is returned alongside the body rather than written
            at the call site. Prometheus content-negotiates on it, and a
            response served as ``text/plain`` is one it parses as a single
            malformed sample.
        """
        return generate_latest(self.registry), CONTENT_TYPE_LATEST
