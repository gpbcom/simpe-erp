from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import ProbeStatus
from models.schemas.exceptions import MTHealthResponseInvalidStatus


class HealthResponse(BaseModel):
    """What the liveness probe reports.

    Attributes:
        status (ProbeStatus): Always :attr:`~models.enums.ProbeStatus.OK`.

    Notes:
        The probe deliberately checks nothing, so this model can only ever
        carry ``ok``. It exists so the answer is a declared shape rather than a
        dictionary literal: an orchestrator's probe is a contract, and a typo
        in a key name would be a rolling restart nobody asked for.
    """

    status: ProbeStatus = Field(
        default=ProbeStatus.OK,
        description="Whether the process is alive.",
    )

    @field_validator("status", mode="before")
    def validate_status(cls, value: Union[str, ProbeStatus, None]) -> ProbeStatus:
        """Validates that ``status`` is a known probe status.

        Args:
            value (Union[str, ProbeStatus, None]): Raw ``status`` value.
                ``None`` falls back to :attr:`~models.enums.ProbeStatus.OK`.

        Returns:
            ProbeStatus: The coerced status.

        Raises:
            MTHealthResponseInvalidStatus: If ``value`` is not a known status.
        """
        if value is None:
            return ProbeStatus.OK
        if isinstance(value, ProbeStatus):
            return value
        try:
            return ProbeStatus(value)
        except ValueError:
            raise MTHealthResponseInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(ProbeStatus.values())}."
            ) from None
