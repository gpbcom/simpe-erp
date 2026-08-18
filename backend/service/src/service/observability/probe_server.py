from __future__ import annotations

# Standard library imports
import asyncio
from logging import Logger, getLogger
from typing import Callable, ClassVar, Optional, Tuple

# First-party imports
from models.configuration.observability_config import ObservabilityConfig
from service.observability.metrics import ApplicationMetrics


class ProbeServer:
    """The small HTTP surface a worker needs in order to be scheduled.

    Attributes:
        READY (ClassVar[bytes]): The body a healthy probe answers with.
        NOT_READY (ClassVar[bytes]): The body an unready probe answers with.
        ROUTES (ClassVar[Tuple[str, ...]]): The paths served.
        REQUEST_TIMEOUT (ClassVar[float]): How long to wait for a request line.

    Notes:
        - **The worker had no port at all**, which is why this exists. Without
          one there is no readiness probe, so Kubernetes reports a worker Ready
          the instant its process starts — before it has a database, a broker
          connection or a single queue bound — and a rolling update replaces the
          last working replica with one that cannot consume. Nothing surfaces
          until a queue stops draining.
        - **Liveness and readiness are different questions**, and answering both
          with one endpoint is how a broker outage becomes a crash loop.
          ``/health`` asks whether the process is alive and answers from memory;
          ``/ready`` asks whether it can do its job. A worker that has lost its
          broker is *not ready* — though it serves no traffic to be taken out
          of — and is very much alive, and restarting it will not bring the
          broker back.
        - Written on :mod:`asyncio` streams rather than a web framework. The
          worker deliberately does not depend on ``api``; pulling FastAPI and
          uvicorn into it to serve three fixed paths would put the whole HTTP
          layer behind a background consumer. Three paths and no routing is
          about forty lines.
        - Metrics are served rather than pushed. A push gateway would need the
          worker to know where to push, and would go on reporting the metrics of
          a pod that has since been deleted.
    """

    READY: ClassVar[bytes] = b'{"status":"ok"}'
    NOT_READY: ClassVar[bytes] = b'{"status":"unavailable"}'
    ROUTES: ClassVar[Tuple[str, ...]] = ("/health", "/ready", "/metrics")
    REQUEST_TIMEOUT: ClassVar[float] = 5.0

    def __init__(
        self,
        config: ObservabilityConfig,
        metrics: ApplicationMetrics,
        is_ready: Callable[[], bool],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the server.

        Args:
            config (ObservabilityConfig): What to serve, and where.
            metrics (ApplicationMetrics): The figures ``/metrics`` renders.
            is_ready (Callable[[], bool]): Answers whether this process can do
                its job right now.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            Readiness is a callable supplied by the caller rather than something
            this class works out. What "ready" means belongs to the process
            being probed — for a worker, a live broker connection — and a server
            deciding for itself would be answering a question it cannot see.
        """
        self.config = config
        self.metrics = metrics
        self.is_ready = is_ready
        self.logger = logger if logger else getLogger(__name__)
        self.server: Optional[asyncio.AbstractServer] = None

    ############################
    # Internal Helpers Methods #
    ############################

    def _answer(self, path: str) -> Tuple[int, bytes, str]:
        """Work out the response to one path.

        Args:
            path (str): The requested path, without its query string.

        Returns:
            Tuple[int, bytes, str]: Status, body and content type.
        """
        if path == "/health":
            return 200, self.READY, "application/json"
        if path == "/ready":
            if self.is_ready():
                return 200, self.READY, "application/json"
            self.logger.warning(
                "Answering /ready with 503: this worker cannot consume."
            )
            return 503, self.NOT_READY, "application/json"
        if path == "/metrics":
            body, content_type = self.metrics.render()
            return 200, body, content_type
        self.logger.debug("No probe route serves %s.", path)
        return 404, b'{"detail":"Not Found"}', "application/json"

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Serve one connection, then close it.

        Args:
            reader (asyncio.StreamReader): The request stream.
            writer (asyncio.StreamWriter): The response stream.

        Notes:
            - Only the request line is read. The rest of the request is discarded
              unread. A probe sends no body, and a server that waited for one
              would hang on every check.
            - Every failure is caught. This endpoint exists to report on the
              worker, so an exception escaping it would be an observability
              problem that took the process down — which is the wrong way round.
        """
        try:
            request_line = await asyncio.wait(
                reader.readline(), timeout=self.REQUEST_TIMEOUT
            )
            parts = request_line.decode("latin-1").split()
            path = parts[1].split("?")[0] if len(parts) >= 2 else "/"
            status, body, content_type = self._answer(path)
            head = (
                f"HTTP/1.1 {status} \r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("latin-1")
            writer.write(head + body)
            await writer.drain()
        except (TimeoutError, OSError, UnicodeDecodeError, ValueError) as exc:
            self.logger.warning("A probe request could not be served: %s.", exc)  # noqa: E501
        finally:
            writer.close()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start(self) -> None:
        """Begin serving, unless metrics are switched off.

        Notes:
            A failure to bind is logged at ``ERROR`` and swallowed. The port
            being taken must not stop a worker consuming: losing the metrics is
            bad, refusing to do the work because of it is worse — the same trade
            the logging setup makes.
        """
        if not self.config.metrics_enabled:
            self.logger.info("Metrics are disabled; serving no probe endpoints.")
            return
        try:
            self.server = await asyncio.start_server(
                self._handle, host="0.0.0.0", port=self.config.metrics_port
            )
        except OSError as exc:
            self.logger.error(
                "Could not serve probes on port %d: %s. The worker consumes "
                "regardless, but it has no readiness probe.",
                self.config.metrics_port,
                exc,
            )
            return
        self.logger.info(
            "Serving %s on port %d.",
            ", ".join(self.ROUTES),
            self.config.metrics_port,
        )

    async def close(self) -> None:
        """Stop serving.

        Notes:
            Best-effort, like every other shutdown here: a process on its way
            out must not hang on a socket.
        """
        if self.server is None:
            self.logger.debug("No probe server to close.")
            return
        self.server.close()
        try:
            await self.server.wait_closed()
        except OSError as exc:
            self.logger.warning("The probe server did not close cleanly: %s.", exc)  # noqa: E501
        self.server = None
        self.logger.debug("The probe server is closed.")
