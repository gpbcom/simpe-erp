from __future__ import annotations

# Standard library imports
from typing import Iterator

# Third-party imports
import pytest

# First-party imports
from models.geo.postal_address import PostalAddress


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
