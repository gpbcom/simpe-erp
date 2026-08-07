from __future__ import annotations

# Standard library imports
from typing import List

# Third-party imports
import pytest

# First-party imports
from seed.dataset import Dataset


class TestTheSeededManagerWhoCoversRounds:
    """Tests that the promotion in :attr:`Dataset.ASSISTANT_MANAGERS` lands.

    Notes:
        **This is the guard on a fixture that silently promotes nobody.** The
        seeder matches a promoted name against ``Hca.full_name()``, so a name
        spelled differently here than in ``ASSISTANTS`` — a missing accent, a
        surname that changed on one list and not the other — matches nothing
        and seeds every assistant with the assistant role, which is exactly
        what the promotion exists to stop. Nothing downstream notices: the
        seeder reports success, the stack comes up, and the only symptom is a
        screen that renders locked for everybody.

        That screen is the employment section of the account page. It renders
        from an assistant record and unlocks on a manager's role, so it needs
        one account holding both. Before the promotion, no seeded account did:
        the three staff accounts carry no assistant record, and every
        assistant account carries the assistant role.
    """

    @pytest.fixture
    def assistant_names(self) -> List[str]:
        """Return every seeded assistant's full name.

        Returns:
            List[str]: ``"First Last"`` for each row of ``ASSISTANTS``.
        """
        return [f"{row[0]} {row[1]}" for row in Dataset.ASSISTANTS]

    def test_somebody_is_promoted(self) -> None:
        """An empty list leaves the editable half of the screen unreachable."""
        assert Dataset.ASSISTANT_MANAGERS

    @pytest.mark.parametrize("name", list(Dataset.ASSISTANT_MANAGERS))
    def test_a_promoted_name_is_a_seeded_assistant(
        self, name: str, assistant_names: List[str]
    ) -> None:
        """A name matching no assistant promotes nobody, and says nothing.

        Args:
            name (str): The promoted assistant's full name.
            assistant_names (List[str]): Every seeded assistant's full name.
        """
        assert name in assistant_names

    def test_the_promoted_are_not_the_whole_workforce(
        self, assistant_names: List[str]
    ) -> None:
        """Somebody must still hold the assistant role.

        Args:
            assistant_names (List[str]): Every seeded assistant's full name.

        Notes:
            The locked half of the same screen needs an assistant to sign in
            as, and the access-control checks need somebody the manager-gated
            routes refuse. Promoting everybody would leave both untestable.
        """
        assert set(Dataset.ASSISTANT_MANAGERS) != set(assistant_names)
