from __future__ import annotations

# Third-party imports
from pydantic import BaseModel, Field


class CompanyChoice(BaseModel):
    """A company as it appears on the public list an applicant chooses from.

    Attributes:
        id (str): The identifier to submit with an application.
        name (str): The trading name to show.

    Notes:
        Deliberately two fields. This is the only company data served without a
        credential, and its shape is what stops the rest leaking — a response
        model that could carry an address would eventually be given one.
    """

    id: str = Field(description="The identifier to submit with an application.")
    name: str = Field(description="The trading name to show.")
