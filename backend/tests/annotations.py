from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Union

# Third-party imports
from pydantic import BaseModel, JsonValue

#: What a test hands to a model constructor, a fixture, or a validator.
#:
#: The suite's job is largely to feed models values they should refuse, so these
#: annotations describe a deliberately wide set — but a *named* wide set rather
#: than ``Any`` or ``object``, both of which say only "we gave up". This one
#: says what is actually passed: JSON-shaped data as it arrives from a request
#: body, the richer Python types the fields are declared as, and the enums and
#: nested models a constructor accepts directly.
#:
#: ``JsonValue`` carries the recursive half — ``None``, strings, numbers,
#: booleans, and lists and mappings of those — which is also the whole
#: vocabulary of the wrong values the rejection tests pass in. The rest are the
#: types that appear in the valid fixtures: dates and times on interventions,
#: ``Decimal`` on every amount, an ``Enum`` member where a field is an
#: enumeration, and a ``BaseModel`` where a field is a nested model.
ModelInput = Union[JsonValue, date, datetime, time, Decimal, Enum, BaseModel]
