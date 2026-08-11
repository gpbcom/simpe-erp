from __future__ import annotations

# Standard library imports
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.messaging.event_envelope import EventEnvelope
from models.messaging.exceptions import MTEventEnvelopeInvalidTraceparent

#: A well-formed W3C context, from the specification's own example.
VALID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class TestEnvelopeCarriesTraceContext:
    """Tests for the field that makes a trace survive the broker.

    Notes:
        **Every instrumentation library propagates trace context over HTTP and
        none of them does it over a broker.** Without this field a trace stops
        at ``POST /api/v1/planning/runs``, and the thirty seconds that actually
        matter — the solve — are attributed to nothing at all.
    """

    # ------------------------------------------------------------------ #
    #  Nullable, and why
    # ------------------------------------------------------------------ #

    def test_a_message_may_carry_no_context(self) -> None:
        """**Nullable, so an older message still parses.**

        Notes:
            A queue is not drained the instant a deployment lands. Messages
            written by the previous version are still in it, and a required
            field here would dead-letter every one of them — losing exactly the
            work a careful rollout was trying not to lose.
        """
        assert EventEnvelope(routing_key="quote.submitted").traceparent is None

    def test_a_context_is_carried_verbatim(self) -> None:
        """It is opaque to this application; only the collector reads it."""
        envelope = EventEnvelope(routing_key="quote.submitted", traceparent=VALID)

        assert envelope.traceparent == VALID

    def test_it_survives_the_round_trip_through_json(self) -> None:
        """The broker carries JSON, so the field has to make the crossing."""
        published = EventEnvelope(routing_key="quote.submitted", traceparent=VALID)

        received = EventEnvelope(**published.model_dump(mode="json"))

        assert received.traceparent == VALID

    # ------------------------------------------------------------------ #
    #  Refused rather than dropped
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "malformed",
        [
            pytest.param("nonsense", id="Invalid - not hyphenated"),
            pytest.param("00-abc-def-01", id="Invalid - fields too short"),
            pytest.param(f"00-{'a' * 32}-{'b' * 16}", id="Invalid - three fields"),
            pytest.param(
                "00-4BF92F3577B34DA6A3CE929D0E0E4736-00f067aa0ba902b7-01",
                id="Invalid - upper case",
            ),
            pytest.param(
                f"00-{'z' * 32}-00f067aa0ba902b7-01", id="Invalid - not hexadecimal"
            ),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_a_malformed_context_is_refused(self, malformed: Any) -> None:
        """**A malformed context is not inert.**

        Notes:
            Extracted leniently it would be ignored and a *new* trace begun, so
            the solve appears to have started on its own with no request behind
            it. That reads as a complete picture, which is why it is worse than
            no trace at all — and why this is refused at the envelope rather
            than tolerated at the extractor.
        """
        with pytest.raises(MTEventEnvelopeInvalidTraceparent):
            EventEnvelope(routing_key="quote.submitted", traceparent=malformed)

    @pytest.mark.parametrize(
        "all_zero",
        [
            pytest.param(f"00-{'0' * 32}-00f067aa0ba902b7-01", id="Invalid - trace id"),
            pytest.param(
                f"00-4bf92f3577b34da6a3ce929d0e0e4736-{'0' * 16}-01",
                id="Invalid - span id",
            ),
        ],
    )
    def test_an_all_zero_identifier_is_refused(self, all_zero: str) -> None:
        """The specification calls both invalid, and a collector drops them.

        Notes:
            Silently — which is the failure mode this whole field exists to
            avoid, arrived at by a different route.
        """
        with pytest.raises(MTEventEnvelopeInvalidTraceparent):
            EventEnvelope(routing_key="quote.submitted", traceparent=all_zero)

    def test_surrounding_whitespace_is_removed(self) -> None:
        """A header read off the wire may arrive padded."""
        envelope = EventEnvelope(
            routing_key="quote.submitted", traceparent=f" {VALID} "
        )

        assert envelope.traceparent == VALID
