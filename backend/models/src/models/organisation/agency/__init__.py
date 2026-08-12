"""One of a company's places, and the people attached to it.

The aggregate: the site itself, and the membership rows saying who works
there. They live together because a membership means nothing without the
site it points at — a person attached to no agency is the state this
feature exists to make impossible.
"""

from .agency import Agency
from .agency_member import AgencyMember

__all__ = [
    "Agency",
    "AgencyMember",
]
