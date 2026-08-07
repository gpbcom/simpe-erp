from __future__ import annotations

# Standard library imports
from typing import Iterator

# Third-party imports
import bcrypt
import pytest

# First-party imports
from models.geo.postal_address import PostalAddress

#: The bcrypt cost the suite hashes at. Production uses the library default of
#: 12, which is a deliberate ~250 ms per hash — the whole point of the algorithm.
#: Four is the library minimum and is roughly two hundred times cheaper.
TEST_BCRYPT_ROUNDS = 4


def _no_geocoding(self: PostalAddress) -> None:
    """Stand in for the Nominatim lookup, leaving the address untouched.

    Args:
        self (PostalAddress): The address that would have been resolved.
    """


@pytest.fixture(autouse=True)
def suppress_geocoding(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Stop every test from reaching Nominatim.

    Args:
        request (pytest.FixtureRequest): The running test, inspected for the
            ``geocoding`` marker.
        monkeypatch (pytest.MonkeyPatch): Used to neutralise the lookup.

    Yields:
        None: While the suite runs without geocoding.

    Notes:
        :class:`~models.geo.postal_address.PostalAddress` resolves its
        coordinate in ``model_post_init``, so without this every test that
        builds an address — most of the suite — would issue a real HTTP request
        to the public Nominatim instance. That would be slow, flaky, and
        abusive of a free service.

        ``_geocode`` is replaced with a no-op rather than the transport being
        made to fail. A failing transport would record ``geocoding_error``, and
        an address is meant to come out of an untouched construction with
        neither a coordinate nor an error; recording one would change what the
        model-level tests observe.

        The model has no kill switch of its own: nothing in the application
        needs one, because a stored address counts as already resolved and is
        never looked up again. Suppression is a testing concern, so it lives
        here rather than as a production affordance nothing in production uses.

        Applied automatically so a newly added test cannot forget it and
        quietly start calling out. The tests that exercise the lookup itself
        carry ``@pytest.mark.geocoding``, which leaves the real method in place
        for them to drive through a stubbed transport.
    """
    if "geocoding" in request.keywords:
        yield
        return
    monkeypatch.setattr(PostalAddress, "_geocode", _no_geocoding)
    yield


@pytest.fixture(autouse=True)
def cheap_password_hashing(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Hash at bcrypt's minimum cost for the duration of a test.

    Args:
        monkeypatch (pytest.MonkeyPatch): Used to lower the cost factor.

    Yields:
        None: While hashing is cheap.

    Notes:
        **Only the cost changes. Real bcrypt still runs.** ``gensalt`` is asked
        for four rounds instead of the library default of twelve, and
        ``hashpw``/``checkpw`` are untouched — so every test that hashes a
        password, verifies one, or asserts that a wrong one is refused still
        exercises the real algorithm end to end. What it no longer pays is the
        ~250 ms per hash that makes bcrypt worth using.

        That cost is the *point* in production and is deliberately not
        configurable: :meth:`~service.auth.auth.AuthService.hash` calls
        ``bcrypt.gensalt()`` with no argument, so there is no setting a
        deployment could get wrong. Which is precisely why this is a **test**
        fixture patching the library rather than a knob on ``AuthConfig``: a
        production cost factor that can be lowered is one that eventually is.

        Autouse, because four service modules build a real ``AuthService`` and
        it is not obvious from a test's name which ones hash. Measured: the
        four together fell from 7.5 s to well under two.

        The cost factor lives in the *hash*, so ``checkpw`` reads it back from
        whatever it is verifying — including
        :attr:`~service.auth.auth.AuthService.DUMMY_HASH`, which is a stored
        cost-12 string and keeps verifying correctly under this fixture.
    """
    original = bcrypt.gensalt
    monkeypatch.setattr(
        bcrypt,
        "gensalt",
        lambda rounds=TEST_BCRYPT_ROUNDS, prefix=b"2b": original(rounds, prefix),
    )
    yield
