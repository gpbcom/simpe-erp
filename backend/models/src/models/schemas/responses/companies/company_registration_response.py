from __future__ import annotations

# Third-party imports
from pydantic import BaseModel, Field

# First-party imports
from models.organisation.companies.company import Company
from models.schemas.responses.auth.user_response import UserResponse


class CompanyRegistrationResponse(BaseModel):
    """What founding an agency hands back: the agency and its administrator.

    Attributes:
        company (Company): The agency that was created.
        administrator (UserResponse): The founder's account, without its
            password hash.

    Notes:
        - No token. Founding an agency and holding a session are separate
          things, and issuing one here would mean a second place that mints
          credentials — which is a second place to get token expiry, scope and
          revocation wrong. The founder signs in with the password they just
          chose, through the same route everybody else uses.
        - The administrator is a :class:`UserResponse` rather than a
          :class:`~models.auth.user.User` so the hash cannot escape by
          accident. That is the whole reason the response model exists.
    """

    company: Company = Field(description="The agency that was created.")
    administrator: UserResponse = Field(description="The founder's account.")
