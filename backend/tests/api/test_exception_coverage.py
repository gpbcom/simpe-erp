from __future__ import annotations

# Standard library imports
import pathlib
import re
from typing import Dict, List, Set, Tuple

# Third-party imports
import pytest

# First-party imports
from api.exception_handlers import ExceptionHandlers

BACKEND = pathlib.Path(__file__).resolve().parents[2]
PACKAGES: Tuple[str, ...] = ("models", "service", "storage", "api")
BUILTIN_RAISES = re.compile(
    r"raise (ValueError|KeyError|TypeError|RuntimeError|NotImplementedError"
    r"|Exception|OSError|AssertionError|IndexError|AttributeError)\b"
)


def _sources() -> List[pathlib.Path]:
    """Return every first-party module, tests excluded.

    Returns:
        List[pathlib.Path]: The modules that ship.
    """
    return [
        path
        for package in PACKAGES
        for path in (BACKEND / package / "src").rglob("*.py")
        if "__pycache__" not in str(path)
    ]


def _declared() -> Dict[str, str]:
    """Return every ``MT*`` exception and the base it inherits from.

    Returns:
        Dict[str, str]: Exception name to the name of its base class.
    """
    declared: Dict[str, str] = {}
    for path in _sources():
        for match in re.finditer(
            r"^class (MT\w+)\(([\w.]+)\)",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        ):
            declared[match.group(1)] = match.group(2)
    return declared


class TestOnlyCustomExceptionsAreRaised:
    """Tests that nothing in the backend raises a built-in exception."""

    def test_no_module_raises_a_builtin(self) -> None:
        """Every failure is an ``MT*`` the API boundary knows how to answer.

        Notes:
            A built-in raised anywhere beneath an endpoint reaches the
            catch-all and becomes an opaque 500. Worse, it carries no family,
            so it cannot be mapped without naming that one call site.

            ``raise`` on its own — re-raising what was just caught — is fine
            and is not matched here.
        """
        offenders = [
            f"{path.relative_to(BACKEND)}:{number}: {line.strip()}"
            for path in _sources()
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            )
            if BUILTIN_RAISES.search(line)
        ]
        assert offenders == []


class TestEveryExceptionIsRegistered:
    """Tests that the API can answer every exception the backend defines."""

    def test_every_family_base_has_a_row(self) -> None:
        """A family without a row answers 500 for every member it will ever have.

        Notes:
            The base classes are what matter: the handler walks an exception's
            ancestry, so registering a family covers the members added to it
            later without a second edit.
        """
        registered = {cls.__name__ for cls in ExceptionHandlers.STATUS_BY_EXCEPTION}
        declared = _declared()
        families = {name for name, base in declared.items() if base == "Exception"}
        assert sorted(families - registered) == []

    def test_every_exception_is_reachable_from_a_row(self) -> None:
        """Walking any exception's ancestry reaches a mapped class."""
        registered = {cls.__name__ for cls in ExceptionHandlers.STATUS_BY_EXCEPTION}
        declared = _declared()
        unreachable: Set[str] = set()
        for name in declared:
            ancestry = [name]
            while ancestry[-1] in declared and declared[ancestry[-1]].startswith("MT"):
                ancestry.append(declared[ancestry[-1]])
            if not registered.intersection(ancestry):
                unreachable.add(name)
        assert sorted(unreachable) == []

    def test_no_row_names_a_deleted_exception(self) -> None:
        """A row for a class nobody raises any more is dead weight."""
        declared = set(_declared())
        registered = {cls.__name__ for cls in ExceptionHandlers.STATUS_BY_EXCEPTION}
        assert sorted(registered - declared) == []

    @pytest.mark.parametrize(
        ("status_code", "least"),
        [
            pytest.param(400, 400, id="no status below 400"),
            pytest.param(599, 599, id="no status above 599"),
        ],
    )
    def test_every_row_maps_to_an_error_status(
        self, status_code: int, least: int
    ) -> None:
        """An exception can only ever answer a 4xx or a 5xx."""
        values = set(ExceptionHandlers.STATUS_BY_EXCEPTION.values())
        assert all(400 <= value <= 599 for value in values)
