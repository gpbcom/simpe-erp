from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.configuration.app_config import AppConfig
from models.configuration.auth_config import AuthConfig
from models.configuration.exceptions import (
    MTAppConfigInvalidAuth,
    MTAppConfigInvalidDatabase,
    MTAppConfigInvalidPlanning,
    MTAppConfigInvalidPricing,
    MTAppConfigInvalidServer,
    MTAppConfigNotFound,
    MTAppConfigUnreadable,
    MTInvalidAppConfigException,
)
from models.configuration.planning_config import PlanningConfig

BACKEND_ROOT = Path(__file__).resolve().parents[3]


class TestAppConfig:
    """Tests for the AppConfig model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_every_section_defaults(self) -> None:
        """A bare config yields the documented defaults for every section."""
        config = AppConfig()
        assert config.server.port == 8000
        assert config.database.port == 5432
        assert config.auth.jwt_algorithm == "HS256"
        assert config.pricing.base_hourly_rate_ht == Decimal("31.905")
        assert config.planning.lunch_break_minutes == 60

    def test_an_absent_section_falls_back_to_defaults(self) -> None:
        """An explicit None section is filled in rather than rejected."""
        config = AppConfig(server=None, planning=None)
        assert config.server.port == 8000
        assert config.planning.day_start_minute == 9 * 60

    def test_already_built_sections_are_accepted(self) -> None:
        """A section may be handed in as a built model."""
        config = AppConfig(
            auth=AuthConfig(access_token_expire_minutes=30),
            planning=PlanningConfig(lunch_break_minutes=90),
        )
        assert config.auth.access_token_expire_minutes == 30
        assert config.planning.lunch_break_minutes == 90

    # ------------------------------------------------------------------ #
    #  Section validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("section", "expected_exception"),
        [
            pytest.param("server", MTAppConfigInvalidServer, id="server"),
            pytest.param("database", MTAppConfigInvalidDatabase, id="database"),
            pytest.param("auth", MTAppConfigInvalidAuth, id="auth"),
            pytest.param("pricing", MTAppConfigInvalidPricing, id="pricing"),
            pytest.param("planning", MTAppConfigInvalidPlanning, id="planning"),
        ],
    )
    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("not-a-mapping", id="Invalid - string"),
            pytest.param([1, 2], id="Invalid - list"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_a_non_mapping_section_raises(
        self, section: str, expected_exception: type, invalid_value: Any
    ) -> None:
        """Each section rejects a non-mapping payload with its own exception."""
        with pytest.raises(expected_exception):
            AppConfig(**{section: invalid_value})

    # ------------------------------------------------------------------ #
    #  Loading
    # ------------------------------------------------------------------ #

    def test_loads_the_shipped_configuration(self) -> None:
        """The configuration committed to the repository is valid."""
        config = AppConfig.load(BACKEND_ROOT / "conf" / "app.yaml")
        assert config.pricing.base_hourly_rate_ht == Decimal("31.905")

    def test_the_shipped_configuration_encodes_the_business_rules(self) -> None:
        """conf/app.yaml carries the contractual surcharges.

        Notes:
            The rules live in configuration, so this asserts the shipped file
            actually says what the contract says — a code-level test of the
            resolver would pass even with an empty rule set.
        """
        config = AppConfig.load(BACKEND_ROOT / "conf" / "app.yaml")
        # 9 August 2026 is a Sunday.
        assert config.pricing.multiplier_for(date(2026, 8, 9)) == Decimal("1.25")
        assert config.pricing.multiplier_for(date(2026, 12, 25)) == Decimal("1.50")
        assert config.pricing.multiplier_for(date(2027, 1, 1)) == Decimal("1.50")
        # 1 January 2034 is a Sunday: the surcharges must not stack.
        assert config.pricing.multiplier_for(date(2034, 1, 1)) == Decimal("1.50")

    def test_the_shipped_configuration_keeps_secrets_out(self) -> None:
        """No literal secret is committed; only env-var names."""
        raw = (BACKEND_ROOT / "conf" / "app.yaml").read_text(encoding="utf-8")
        assert "password_env:" in raw
        assert "jwt_secret_env:" in raw
        assert "password:" not in raw.replace("password_env:", "")

    def test_a_missing_file_raises(self, tmp_path: Path) -> None:
        """A path that resolves nowhere is reported, not silently defaulted."""
        with pytest.raises(MTAppConfigNotFound):
            AppConfig.load(tmp_path / "does-not-exist.yaml")

    def test_an_empty_file_yields_defaults(self, tmp_path: Path) -> None:
        """An empty document is a valid, all-defaults configuration."""
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        assert AppConfig.load(empty).server.port == 8000

    def test_a_non_mapping_document_raises(self, tmp_path: Path) -> None:
        """A YAML list at the top level is not a configuration."""
        listy = tmp_path / "list.yaml"
        listy.write_text("- one\n- two\n", encoding="utf-8")
        with pytest.raises(MTAppConfigUnreadable):
            AppConfig.load(listy)

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        """A parse failure is reported as an unreadable configuration."""
        broken = tmp_path / "broken.yaml"
        broken.write_text("server: {port: 8000\n", encoding="utf-8")
        with pytest.raises(MTAppConfigUnreadable):
            AppConfig.load(broken)

    def test_a_relative_path_resolves_against_the_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The loader falls back to the project root when the cwd differs.

        Notes:
            The test suite and the container run from different directories.
            Without the fallback the configuration would load in one and not
            the other.
        """
        monkeypatch.chdir(tmp_path)
        assert AppConfig.load("conf/app.yaml").pricing.base_hourly_rate_ht == Decimal(
            "31.905"
        )

    def test_a_partial_file_only_overrides_what_it_states(self, tmp_path: Path) -> None:
        """Sections absent from the file keep their defaults."""
        partial = tmp_path / "partial.yaml"
        partial.write_text("planning:\n  lunch_break_minutes: 90\n", encoding="utf-8")
        config = AppConfig.load(partial)
        assert config.planning.lunch_break_minutes == 90
        assert config.planning.day_start_minute == 9 * 60
        assert config.server.port == 8000

    def test_an_invalid_value_in_the_file_raises_the_field_exception(
        self, tmp_path: Path
    ) -> None:
        """A bad value surfaces the specific field exception, not a generic one."""
        # First-party imports
        from models.configuration.exceptions import MTPlanningConfigInvalidLunchBreak

        bad = tmp_path / "bad.yaml"
        bad.write_text("planning:\n  lunch_break_minutes: -5\n", encoding="utf-8")
        with pytest.raises(MTPlanningConfigInvalidLunchBreak):
            AppConfig.load(bad)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTAppConfigInvalidAuth,
            MTAppConfigInvalidDatabase,
            MTAppConfigInvalidPlanning,
            MTAppConfigInvalidPricing,
            MTAppConfigInvalidServer,
            MTAppConfigNotFound,
            MTAppConfigUnreadable,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidAppConfigException."""
        assert issubclass(exception_class, MTInvalidAppConfigException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self) -> None:
        """A config survives a dump-and-rebuild unchanged."""
        config = AppConfig.load(BACKEND_ROOT / "conf" / "app.yaml")
        assert AppConfig(**config.model_dump()) == config

    def test_default_config_path_is_not_a_field(self) -> None:
        """The ClassVar stays out of the serialised payload."""
        assert "DEFAULT_CONFIG_PATH" not in AppConfig().model_dump()
