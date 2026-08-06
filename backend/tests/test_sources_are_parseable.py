from __future__ import annotations

# Standard library imports
import ast
from pathlib import Path
from typing import List

# Third-party imports
import pytest

#: Directories that hold no source of ours.
EXCLUDED: frozenset[str] = frozenset(
    {".venv", "__pycache__", "node_modules", ".git", ".ruff_cache", ".pytest_cache"}
)


def _sources() -> List[Path]:
    """Return every Python file in the workspace.

    Returns:
        List[Path]: The files to parse, workspace-relative.

    Notes:
        Walked from the backend root rather than listed per package, so a new
        workspace member is covered the day it is added rather than the day
        somebody remembers to add it here.
    """
    root = Path(__file__).resolve().parent.parent
    return sorted(
        path
        for path in root.rglob("*.py")
        if not EXCLUDED.intersection(path.relative_to(root).parts)
    )


class TestEverySourceFileParses:
    """A syntax check over the whole workspace."""

    @pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
    def test_a_source_file_parses(self, path: Path) -> None:
        """Every file compiles as Python.

        Args:
            path (Path): The file under test.

        Notes:
            **This test exists because a formatter corrupted nine files and the
            suite stayed green.** ``ruff format`` 0.16.1 rewrites
            ``except (A, B):`` into ``except A, B:``, which is not valid Python
            3 — and CPython went on importing the modules from the ``.pyc``
            files it had already compiled from the *previous*, correct source.
            Every test passed. The damage would have surfaced on the next clean
            checkout, in CI or on a colleague's machine, with nothing pointing
            back at the formatter run that caused it.

            Parsing from the file's own bytes is what makes this immune to that:
            :func:`ast.parse` never consults the bytecode cache, so a file that
            has been corrupted fails here even while the rest of the suite is
            happily running yesterday's compiled copy.

            Parametrised one file per case rather than looping inside a single
            test, so a failure names the file in its own report line instead of
            stopping at the first one.
        """
        source = path.read_text(encoding="utf-8")

        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as error:
            pytest.fail(
                f"{path} does not parse: {error.msg} (line {error.lineno}). "
                "If this followed a `ruff format` run, check for an "
                "`except (A, B):` that has lost its parentheses."
            )
