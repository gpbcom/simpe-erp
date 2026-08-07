from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional

try:  # pragma: no cover - exercised by whether the package is installed
    # Third-party imports
    from opentelemetry import propagate
except ImportError:  # pragma: no cover - the ordinary case until tracing lands
    propagate = None


class TraceContext:
    """Reads and restores W3C trace context across the broker.

    Attributes:
        HEADER (ClassVar[str]): The context's name in the W3C specification.

    Notes:
        - **Every instrumentation library propagates trace context over HTTP
          and none of them does it over a broker.** A trace therefore stops at
          ``POST /api/v1/planning/runs`` unless something carries it across, and
          the thirty seconds that actually matter — the solve — are attributed
          to nothing. This is that something; the field it travels in is
          :attr:`~models.messaging.event_envelope.EventEnvelope.traceparent`.
        - **OpenTelemetry is optional and imported once, at module level.**
          Without it every method here is a no-op returning ``None``, which is
          exactly the behaviour of a deployment that has not turned tracing on:
          messages carry no context, handlers start their own spans, nothing
          fails. Installing the package is what makes it live, with no call site
          changing.
        - Deliberately *not* a check of ``tracing_enabled``. That switch decides
          whether spans are **exported**; whether context is **propagated** is
          decided by whether there is any to propagate. A process with tracing
          off has no active span, so :meth:`current` returns ``None`` on its
          own — and a message it publishes to a process that *does* trace still
          leaves that process free to start a clean trace rather than a
          fragmentary one.
    """

    HEADER: ClassVar[str] = "traceparent"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the helper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def current(self) -> Optional[str]:
        """Return the trace context of whatever is running now.

        Returns:
            Optional[str]: A W3C ``traceparent``, or ``None`` when nothing is
            being traced.

        Notes:
            ``None`` is the ordinary answer, not a failure: it means this
            process is not tracing, or is not inside a span. The publisher puts
            it on the envelope as-is, and the field is nullable for that reason.
        """
        if propagate is None:
            return None
        carrier: Dict[str, str] = {}
        propagate.inject(carrier)
        context = carrier.get(self.HEADER)
        if context is None:
            self.logger.debug("Nothing is being traced; publishing without context.")  # noqa: E501
            return None
        return context

    def restore(self, traceparent: Optional[str]) -> Optional[object]:
        """Rebuild the context a message was published under.

        Args:
            traceparent (Optional[str]): The context carried on the envelope.

        Returns:
            Optional[object]: An OpenTelemetry context to attach a span to, or
            ``None`` when there is nothing to restore.

        Notes:
            The envelope has already refused a malformed ``traceparent``, so
            anything arriving here is either absent or well-formed. That matters
            more than it looks: a malformed one extracted leniently starts a
            *new* trace, and a solve that appears to have begun on its own with
            no request behind it reads as a complete picture while being the
            wrong one.
        """
        if propagate is None or not traceparent:
            return None
        return propagate.extract({self.HEADER: traceparent})
