from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Type, Union

# Third-party imports
from pydantic import BaseModel

# First-party imports
from models.base.exceptions import (
    MTEntityFilterInvalidFlag,
    MTEntityFilterInvalidFragment,
    MTInvalidEntityFilterException,
)


class EntityFilter(BaseModel):
    """What every list screen's filter has in common.

    Attributes:
        INVALID_FRAGMENT (ClassVar[Type[MTInvalidEntityFilterException]]):
            Exception the subclass raises for an unusable text filter.
        INVALID_FLAG (ClassVar[Type[MTInvalidEntityFilterException]]):
            Exception the subclass raises for an unusable three-state flag.

    Notes:
        - **A base, not a mixin, and it holds no fields.** Each screen filters
          on different columns, so there is nothing to inherit but the rules —
          and those rules are identical everywhere: a blank box is not a filter,
          a flag has three states, and an unset filter narrows nothing.
        - **Every field is optional and ``None`` means "not applied".** That is
          the difference between a filter and a search form: a caller sends the
          two boxes they filled in, not eight, and the ones they left alone must
          not silently narrow anything.
        - The exceptions are :class:`ClassVar` types rather than fixed classes,
          the same arrangement
          :class:`~models.base.portrait_holder.PortraitHolder` uses. The API's
          exception-to-status map is keyed on the class, and a rejected
          assistant filter reporting itself as a customer one would send whoever
          is debugging it to the wrong screen.
        - Subclasses call :meth:`validate_fragment` and :meth:`validate_flag`
          from their own ``field_validator``s rather than inheriting a
          validator wholesale: which of their fields are text and which are
          flags is theirs to declare, and a base that guessed would silently
          stop validating a field somebody renamed.
    """

    INVALID_FRAGMENT: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTEntityFilterInvalidFragment
    )
    INVALID_FLAG: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTEntityFilterInvalidFlag
    )

    ############################
    # Publicly Exposed Methods #
    ############################

    @classmethod
    def validate_fragment(cls, value: Optional[str]) -> Optional[str]:
        """Return a text filter as the repository should see it.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when it is empty.

        Raises:
            MTInvalidEntityFilterException: The subclass's
                :attr:`INVALID_FRAGMENT`, if ``value`` is neither ``None`` nor a
                string.

        Notes:
            Stripped and emptied to ``None`` so the repository never has to ask
            whether a filter is present *and* whether it is meaningful. An input
            box somebody typed in and then cleared sends ``""``, and reading
            that as "match the empty string" would answer nobody.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise cls.INVALID_FRAGMENT(
                f"Invalid filter fragment: {value!r}. Must be a string or None."
            )
        return value.strip() or None

    @classmethod
    def validate_flag(cls, value: Union[bool, str, int, None]) -> Optional[bool]:  # noqa: E501
        """Return a three-state flag as the repository should see it.

        Args:
            value (Union[bool, str, int, None]): Raw flag value.

        Returns:
            Optional[bool]: The flag, or ``None`` when the filter is unset.

        Raises:
            MTInvalidEntityFilterException: The subclass's :attr:`INVALID_FLAG`,
                if ``value`` is neither ``None`` nor a boolean.

        Notes:
            **Three states, not two.** ``None`` is "do not filter on this",
            ``False`` is "only those where it is false" — and conflating them
            would make an unticked box hide every record that *has* the thing.
        """
        if value is None:
            return None
        if not isinstance(value, bool):
            raise cls.INVALID_FLAG(
                f"Invalid filter flag: {value!r}. Must be true, false or None."
            )
        return value

    def is_empty(self) -> bool:
        """Return whether the filter narrows anything at all.

        Returns:
            bool: ``True`` when every field is unset.

        Notes:
            Lets a caller log "listing everything" rather than "listing what
            matches nothing", which are opposite readings of the same empty
            filter.
        """
        return all(value is None for value in self.model_dump().values())
