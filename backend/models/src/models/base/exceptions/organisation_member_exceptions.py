class MTInvalidOrganisationMemberException(Exception):
    """Exception raised when a membership row is invalid."""


class MTOrganisationMemberInvalidKind(MTInvalidOrganisationMemberException):
    """Exception raised when the member kind is not a :class:`MemberKind`.

    Notes:
        A default, and one a concrete membership model is expected to override.
        It exists so a model that has not declared its own still raises
        something typed rather than reaching the API's catch-all as a 500.
    """


class MTOrganisationMemberInvalidId(MTInvalidOrganisationMemberException):
    """Exception raised when the member identifier is not a non-empty string.

    Notes:
        The same default, for the identifier half. See
        :class:`MTOrganisationMemberInvalidKind`.
    """
