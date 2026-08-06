from __future__ import annotations

# Standard library imports
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.configuration.auth_config import AuthConfig
from models.configuration.database_config import DatabaseConfig
from models.configuration.exceptions import (
    MTAuthConfigInvalidJwtAlgorithm,
    MTAuthConfigInvalidJwtSecretEnv,
    MTAuthConfigInvalidTokenExpiry,
    MTAuthConfigMissingSecret,
    MTDatabaseConfigInvalidDatabase,
    MTDatabaseConfigInvalidHost,
    MTDatabaseConfigInvalidPasswordEnv,
    MTDatabaseConfigInvalidPoolSize,
    MTDatabaseConfigInvalidPort,
    MTDatabaseConfigInvalidUsername,
    MTDatabaseConfigMissingPassword,
    MTInvalidAuthConfigException,
    MTInvalidDatabaseConfigException,
    MTInvalidServerConfigException,
    MTServerConfigInvalidCorsOrigins,
    MTServerConfigInvalidHost,
    MTServerConfigInvalidPort,
)
from models.configuration.server_config import ServerConfig


class TestDatabaseConfig:
    """Tests for the DatabaseConfig model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_defaults_target_a_local_postgres(self) -> None:
        """The defaults describe a local development database."""
        config = DatabaseConfig()
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.echo_sql is False

    def test_the_driver_is_the_async_postgres_dialect(self) -> None:
        """The URL is built for asyncpg, matching the async engine."""
        assert DatabaseConfig.DRIVER == "postgresql+asyncpg"

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("field", "invalid_value", "expected_exception"),
        [
            pytest.param(
                "host", "", MTDatabaseConfigInvalidHost, id="Invalid - empty host"
            ),
            pytest.param(
                "host", None, MTDatabaseConfigInvalidHost, id="Invalid - None host"
            ),
            pytest.param(
                "port", 0, MTDatabaseConfigInvalidPort, id="Invalid - zero port"
            ),
            pytest.param(
                "port", 65536, MTDatabaseConfigInvalidPort, id="Invalid - port too high"
            ),
            pytest.param(
                "port", "5432", MTDatabaseConfigInvalidPort, id="Invalid - string port"
            ),
            pytest.param(
                "database",
                "  ",
                MTDatabaseConfigInvalidDatabase,
                id="Invalid - blank database",
            ),
            pytest.param(
                "username",
                None,
                MTDatabaseConfigInvalidUsername,
                id="Invalid - None username",
            ),
            pytest.param(
                "password_env",
                "",
                MTDatabaseConfigInvalidPasswordEnv,
                id="Invalid - empty password_env",
            ),
            pytest.param(
                "pool_size",
                -1,
                MTDatabaseConfigInvalidPoolSize,
                id="Invalid - negative pool",
            ),
            pytest.param(
                "max_overflow",
                1.5,
                MTDatabaseConfigInvalidPoolSize,
                id="Invalid - float overflow",
            ),
            pytest.param(
                "pool_timeout_seconds",
                0,
                MTDatabaseConfigInvalidPoolSize,
                id="Invalid - zero timeout",
            ),
        ],
    )
    def test_invalid_fields_raise(
        self, field: str, invalid_value: Any, expected_exception: type
    ) -> None:
        """Each field rejects its own invalid values with its own exception."""
        with pytest.raises(expected_exception):
            DatabaseConfig(**{field: invalid_value})

    # ------------------------------------------------------------------ #
    #  Secret resolution
    # ------------------------------------------------------------------ #

    def test_get_password_reads_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The password comes from the named environment variable."""
        monkeypatch.setenv("TEST_PG_PASSWORD", "s3cret")
        config = DatabaseConfig(password_env="TEST_PG_PASSWORD")
        assert config.get_password() == "s3cret"

    def test_get_password_raises_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing secret fails loudly rather than connecting anonymously."""
        monkeypatch.delenv("TEST_PG_PASSWORD", raising=False)
        config = DatabaseConfig(password_env="TEST_PG_PASSWORD")
        with pytest.raises(MTDatabaseConfigMissingPassword):
            config.get_password()

    def test_get_password_raises_when_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty secret is treated as missing."""
        monkeypatch.setenv("TEST_PG_PASSWORD", "")
        with pytest.raises(MTDatabaseConfigMissingPassword):
            DatabaseConfig(password_env="TEST_PG_PASSWORD").get_password()

    # ------------------------------------------------------------------ #
    #  DSN building
    # ------------------------------------------------------------------ #

    def test_dsn_without_password_omits_the_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The loggable URL never carries the password.

        Notes:
            This is the form that goes into log lines; leaking the credential
            into a log file is exactly what it exists to prevent.
        """
        monkeypatch.setenv("TEST_PG_PASSWORD", "s3cret")
        config = DatabaseConfig(password_env="TEST_PG_PASSWORD")
        assert "s3cret" not in config.dsn_without_password
        assert config.dsn_without_password == (
            "postgresql+asyncpg://simple_erp@localhost:5432/simple_erp"
        )

    def test_build_dsn_includes_the_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The real URL carries the resolved credential."""
        monkeypatch.setenv("TEST_PG_PASSWORD", "s3cret")
        config = DatabaseConfig(password_env="TEST_PG_PASSWORD")
        assert config.build_dsn() == (
            "postgresql+asyncpg://simple_erp:s3cret@localhost:5432/simple_erp"
        )

    def test_build_dsn_raises_without_a_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No secret means no connection string."""
        monkeypatch.delenv("TEST_PG_PASSWORD", raising=False)
        with pytest.raises(MTDatabaseConfigMissingPassword):
            DatabaseConfig(password_env="TEST_PG_PASSWORD").build_dsn()

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTDatabaseConfigInvalidDatabase,
            MTDatabaseConfigInvalidHost,
            MTDatabaseConfigInvalidPasswordEnv,
            MTDatabaseConfigInvalidPoolSize,
            MTDatabaseConfigInvalidPort,
            MTDatabaseConfigInvalidUsername,
            MTDatabaseConfigMissingPassword,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidDatabaseConfigException."""
        assert issubclass(exception_class, MTInvalidDatabaseConfigException)


class TestAuthConfig:
    """Tests for the AuthConfig model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_defaults(self) -> None:
        """The defaults sign with HS256 for twelve hours."""
        config = AuthConfig()
        assert config.jwt_algorithm == "HS256"
        assert config.access_token_expire_minutes == 720

    # ------------------------------------------------------------------ #
    #  jwt_algorithm validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512"])
    def test_supported_algorithms_are_accepted(self, algorithm: str) -> None:
        """Every supported HMAC algorithm is accepted."""
        assert AuthConfig(jwt_algorithm=algorithm).jwt_algorithm == algorithm

    @pytest.mark.parametrize(
        "invalid_algorithm",
        [
            pytest.param("RS256", id="Invalid - asymmetric"),
            pytest.param("none", id="Invalid - none algorithm"),
            pytest.param("hs256", id="Invalid - wrong case"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_unsupported_algorithm_raises(self, invalid_algorithm: Any) -> None:
        """Only symmetric HMAC algorithms are accepted.

        Notes:
            Accepting an asymmetric algorithm alongside a shared secret is how
            the ``alg`` confusion attack gets in.
        """
        with pytest.raises(MTAuthConfigInvalidJwtAlgorithm):
            AuthConfig(jwt_algorithm=invalid_algorithm)

    # ------------------------------------------------------------------ #
    #  Other field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_env",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_invalid_jwt_secret_env_raises(self, invalid_env: Any) -> None:
        """The secret env-var name must be a non-empty string."""
        with pytest.raises(MTAuthConfigInvalidJwtSecretEnv):
            AuthConfig(jwt_secret_env=invalid_env)

    @pytest.mark.parametrize(
        "invalid_expiry",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(365 * 24 * 60 + 1, id="Invalid - beyond a year"),
            pytest.param("720", id="Invalid - string"),
            pytest.param(720.0, id="Invalid - float"),
        ],
    )
    def test_invalid_token_expiry_raises(self, invalid_expiry: Any) -> None:
        """A token lifetime outside 1 minute to 1 year is rejected."""
        with pytest.raises(MTAuthConfigInvalidTokenExpiry):
            AuthConfig(access_token_expire_minutes=invalid_expiry)

    # ------------------------------------------------------------------ #
    #  Secret resolution
    # ------------------------------------------------------------------ #

    def test_get_jwt_secret_reads_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The signing secret comes from the named environment variable."""
        monkeypatch.setenv("TEST_JWT_SECRET", "signing-key")
        assert AuthConfig(jwt_secret_env="TEST_JWT_SECRET").get_jwt_secret() == (
            "signing-key"
        )

    def test_get_jwt_secret_raises_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """There is no default secret; a missing one refuses to sign.

        Notes:
            A fallback would let the service boot in production with a signing
            key that is public knowledge.
        """
        monkeypatch.delenv("TEST_JWT_SECRET", raising=False)
        with pytest.raises(MTAuthConfigMissingSecret):
            AuthConfig(jwt_secret_env="TEST_JWT_SECRET").get_jwt_secret()

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTAuthConfigInvalidJwtAlgorithm,
            MTAuthConfigInvalidJwtSecretEnv,
            MTAuthConfigInvalidTokenExpiry,
            MTAuthConfigMissingSecret,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidAuthConfigException."""
        assert issubclass(exception_class, MTInvalidAuthConfigException)


class TestServerConfig:
    """Tests for the ServerConfig model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_defaults(self) -> None:
        """The server binds every interface on port 8000 by default."""
        config = ServerConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000

    def test_cors_origins_default_to_empty_not_wildcard(self) -> None:
        """No origin is allowed until the deployment names one.

        Notes:
            A wildcard default combined with credentialed requests would let
            any site drive the API with a logged-in user's token.
        """
        assert ServerConfig().cors_origins == []

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", ["host", "title", "version"])
    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(8000, id="Invalid - int"),
        ],
    )
    def test_invalid_text_fields_raise(self, field: str, invalid_value: Any) -> None:
        """Text fields must be non-empty strings."""
        with pytest.raises(MTServerConfigInvalidHost):
            ServerConfig(**{field: invalid_value})

    @pytest.mark.parametrize(
        "invalid_port",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(65536, id="Invalid - too high"),
            pytest.param("8000", id="Invalid - string"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_port_raises(self, invalid_port: Any) -> None:
        """A port outside 1..65535 is rejected."""
        with pytest.raises(MTServerConfigInvalidPort):
            ServerConfig(port=invalid_port)

    def test_cors_origins_are_stripped(self) -> None:
        """Whitespace around a configured origin is removed."""
        config = ServerConfig(cors_origins=["  http://localhost:5173  "])
        assert config.cors_origins == ["http://localhost:5173"]

    def test_none_cors_origins_yields_an_empty_list(self) -> None:
        """An absent section is an empty list, not an error."""
        assert ServerConfig(cors_origins=None).cors_origins == []

    @pytest.mark.parametrize(
        "invalid_origins",
        [
            pytest.param("http://localhost", id="Invalid - string not list"),
            pytest.param([""], id="Invalid - empty entry"),
            pytest.param([None], id="Invalid - None entry"),
            pytest.param([8000], id="Invalid - int entry"),
        ],
    )
    def test_invalid_cors_origins_raise(self, invalid_origins: Any) -> None:
        """The origins must be a list of non-empty strings."""
        with pytest.raises(MTServerConfigInvalidCorsOrigins):
            ServerConfig(cors_origins=invalid_origins)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTServerConfigInvalidCorsOrigins,
            MTServerConfigInvalidHost,
            MTServerConfigInvalidPort,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidServerConfigException."""
        assert issubclass(exception_class, MTInvalidServerConfigException)
