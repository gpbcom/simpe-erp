class MTInvalidCustomerPlanningException(Exception):
    """Exception raised when an invalid CustomerPlanning field is provided."""


class MTCustomerPlanningInvalidCustomerId(MTInvalidCustomerPlanningException):
    """Exception raised when an invalid ``customer_id`` value is provided."""


class MTCustomerPlanningInvalidCustomerName(MTInvalidCustomerPlanningException):
    """Exception raised when an invalid ``customer_full_name`` is provided.

    Notes:
        The name is what a rail of households is read by. Falling back to the
        identifier would print a UUID beside a week of care, which is not
        something anybody can act on.
    """


class MTCustomerPlanningInvalidPeriod(MTInvalidCustomerPlanningException):
    """Exception raised when the period is malformed or runs backwards."""


class MTCustomerPlanningInvalidInterventions(MTInvalidCustomerPlanningException):
    """Exception raised when ``interventions`` is not a list of visits."""
