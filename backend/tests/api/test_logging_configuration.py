from __future__ import annotations

# Standard library imports
import io
import logging
from pathlib import Path
from typing import Iterator

# Third-party imports
from colorlog import ColoredFormatter
import pytest
import yaml

# First-party imports
from api.main import setup_logging

CONFIG_PATH = Path(__file__).resolve().parents[2] / "conf" / "logger.yaml"


@pytest.fixture
def configured_logging() -> Iterator[logging.Logger]:
    """Apply the shipped configuration, then restore the previous handlers.

    Yields:
        logging.Logger: The configured root logger.

    Notes:
        ``dictConfig`` mutates global state, so the root logger's handlers and
        level are captured and put back. Without that, every test running after
        this one would log through whatever this one installed.
    """
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    setup_logging()
    yield root
    root.handlers = previous_handlers
    root.setLevel(previous_level)


class TestLoggerConfigurationFile:
    """Tests for the shipped conf/logger.yaml."""

    def test_the_file_ships_with_the_backend(self) -> None:
        """Logging is configured by a file, not in code."""
        assert CONFIG_PATH.is_file()

    def test_it_declares_both_formatters(self) -> None:
        """A colourised console and a plain file, as the other projects do."""
        document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        assert set(document["formatters"]) == {"colored", "detailed"}

    def test_the_console_formatter_is_colorlog(self) -> None:
        """The colour comes from colorlog, resolved by dictConfig.

        Notes:
            The key is the literal ``()``, which is how ``dictConfig`` is told
            to call something rather than look up a format string. Misspelling
            it produces a configuration error at start-up, not a monochrome
            console.
        """
        document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        assert document["formatters"]["colored"]["()"] == "colorlog.ColoredFormatter"

    def test_every_level_has_its_own_colour(self) -> None:
        """A wall of one colour would be no better than none."""
        document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        colours = document["formatters"]["colored"]["log_colors"]
        assert set(colours) == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        assert len(set(colours.values())) == len(colours)

    def test_the_file_handler_is_not_coloured(self) -> None:
        """Escape sequences belong in a terminal, not in a log file.

        Notes:
            A coloured file is one ``grep`` away from being useless: the codes
            sit between the timestamp and the message and break every pattern
            anchored on either.
        """
        document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        assert document["handlers"]["file"]["formatter"] == "detailed"

    def test_the_record_carries_its_origin(self) -> None:
        """Both formats name the function and line that logged."""
        document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        for name in ("colored", "detailed"):
            fmt = document["formatters"][name]["format"]
            assert "%(funcName)s" in fmt
            assert "%(lineno)d" in fmt


class TestAppliedLoggingConfiguration:
    """Tests for the configuration once dictConfig has applied it."""

    def test_the_console_handler_uses_the_colour_formatter(
        self, configured_logging: logging.Logger
    ) -> None:
        """Start-up installs the colourised formatter, not a fallback one.

        Notes:
            ``setup_logging`` falls back to ``basicConfig`` when the file
            cannot be read — which keeps the API serving, but silently drops
            the colours. This asserts the real path was taken.
        """
        console = next(
            handler
            for handler in configured_logging.handlers
            if isinstance(handler, logging.StreamHandler)
        )
        assert isinstance(console.formatter, ColoredFormatter)

    @pytest.mark.parametrize(
        ("level", "colour"),
        [
            pytest.param(logging.DEBUG, "\x1b[36m", id="DEBUG is cyan"),
            pytest.param(logging.INFO, "\x1b[32m", id="INFO is green"),
            pytest.param(logging.WARNING, "\x1b[33m", id="WARNING is yellow"),
            pytest.param(logging.ERROR, "\x1b[31m", id="ERROR is red"),
        ],
    )
    def test_each_level_renders_in_its_colour(
        self, configured_logging: logging.Logger, level: int, colour: str
    ) -> None:
        """A record reaches the console wrapped in its level's escape code."""
        console = next(
            handler
            for handler in configured_logging.handlers
            if isinstance(handler, logging.StreamHandler)
        )
        captured = io.StringIO()
        original_stream = console.stream
        console.stream = captured
        try:
            logging.getLogger("rt_erp.test").log(level, "a line")
        finally:
            console.stream = original_stream
        rendered = captured.getvalue()
        assert rendered.startswith(colour)
        assert "\x1b[0m" in rendered
