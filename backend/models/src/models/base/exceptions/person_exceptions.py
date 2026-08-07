class MTInvalidPersonException(Exception):
    """Exception raised when an invalid field of a person is provided.

    Notes:
        The root of every people-model exception:
        :class:`MTInvalidHcaException`,
        :class:`MTInvalidCustomerException` and
        :class:`MTInvalidHcaApplicationException` all descend from it.

        It exists so :class:`~models.people.person.Person` can *type* the
        per-model exception classes its subclasses supply. The base holds the
        validation rule once; each subclass says which exception that rule
        raises, and this is the bound those declarations are checked against.

        Nothing raises it directly. Catching it means "some person model
        refused a field", which is a coarser question than any call site in the
        application asks — every handler catches the per-model class, and the
        exception-to-status map is keyed on those.
    """


class MTPersonInvalidId(MTInvalidPersonException):
    """Exception raised when an invalid ``id`` value is provided.

    Notes:
        A fallback, used only by a subclass that declares no identifier
        exception of its own. Every model in the application declares one, so
        this is what a *new* people model raises before somebody gives it the
        exception the API layer knows how to answer.
    """


class MTPersonInvalidFirstName(MTInvalidPersonException):
    """Exception raised when an invalid ``first_name`` value is provided."""


class MTPersonInvalidLastName(MTInvalidPersonException):
    """Exception raised when an invalid ``last_name`` value is provided."""


class MTPersonInvalidPhoneNumber(MTInvalidPersonException):
    """Exception raised when an invalid ``phone_number`` value is provided."""


class MTPersonInvalidEmail(MTInvalidPersonException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTPersonInvalidAddress(MTInvalidPersonException):
    """Exception raised when an invalid ``address`` value is provided."""


class MTPersonInvalidDate(MTInvalidPersonException):
    """Exception raised when an invalid timestamp value is provided."""


class MTPersonInvalidPhotoUrl(MTInvalidPersonException):
    """Exception raised when a portrait URL was not issued by this store.

    Notes:
        The fallback for :class:`~models.base.portrait_holder.PortraitHolder`,
        used only by a model that declares no portrait exception of its own.
        Both models that hold one — an assistant and an account — declare
        theirs, because the API answers each family differently.
    """
