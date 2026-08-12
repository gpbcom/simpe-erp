"""A team, the people on it, and the files they share.

The aggregate: the team itself, its membership rows, and the documents in
its shared space. They live together because none of the satellites means
anything without the team it belongs to — a membership pointing at no team
is not a record anybody keeps, and neither is a document.
"""

from .team import Team
from .team_document import TeamDocument
from .team_member import TeamMember

__all__ = [
    "Team",
    "TeamDocument",
    "TeamMember",
]
