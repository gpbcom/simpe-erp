class MTInvalidObservabilityConfigException(Exception):
    """Exception raised when the observability configuration is invalid."""


class MTObservabilityConfigInvalidFlag(MTInvalidObservabilityConfigException):
    """Exception raised when a switch is not a boolean.

    Notes:
        A quoted ``"false"`` is truthy, so reading one leniently would turn
        instrumentation off in a file that says it is on — or, worse, on in one
        that says it is off, exporting spans to a collector that is not there
        and adding a failed connection to every request.
    """


class MTObservabilityConfigInvalidServiceName(MTInvalidObservabilityConfigException):
    """Exception raised when the service name is missing or blank.

    Notes:
        It is the label every metric, log line and span is grouped by. A blank
        one does not fail: it produces a dashboard where the API's latency and
        the planning worker's are the same series.
    """


class MTObservabilityConfigInvalidEndpoint(MTInvalidObservabilityConfigException):
    """Exception raised when the OTLP endpoint is not an absolute URL.

    Notes:
        A relative endpoint is accepted by the exporter and then never resolves,
        so traces stop arriving with nothing in the logs to say why.
    """


class MTObservabilityConfigInvalidPort(MTInvalidObservabilityConfigException):
    """Exception raised when the metrics port is not a usable TCP port."""


class MTObservabilityConfigInvalidTimeout(MTInvalidObservabilityConfigException):
    """Exception raised when the export timeout is not strictly positive."""
