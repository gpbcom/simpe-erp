from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.enums import AvailabilityKind, ContractType
from models.geo.postal_address import PostalAddress
from models.people.availability_slot import AvailabilitySlot
from models.people.certification import Certification
from models.people.driving_license import DrivingLicense
from models.people.hca import Hca
from models.schemas.exceptions import (
    MTHcaResponseInvalidContractType,
    MTHcaResponseInvalidDate,
    MTHcaResponseInvalidId,
    MTHcaResponseInvalidName,
    MTInvalidHcaResponseException,
)
from models.schemas.responses.hca_response import HcaResponse


@pytest.fixture
def address() -> PostalAddress:
    """Return a resolved home address.

    Returns:
        PostalAddress: An address carrying a coordinate.
    """
    return PostalAddress(
        street="12 rue de Rivoli",
        postal_code="75004",
        city="Paris",
        latitude=48.8566,
        longitude=2.3522,
    )


@pytest.fixture
def valid_response_kwargs(address: PostalAddress) -> Dict[str, Any]:
    """Return the minimal keyword arguments for a valid response.

    Args:
        address (PostalAddress): The home address to attach.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "id": "hca-1",
        "first_name": "Marie",
        "last_name": "Durand",
        "phone_number": "+33612345678",
        "email": "marie.durand@example.com",
        "address": address,
        "contract_type": ContractType.CDI,
    }


class TestHcaResponse:
    """Tests for the HcaResponse schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """An assistant publishes its identity, address and contract."""
        response = HcaResponse(**valid_response_kwargs)
        assert response.id == "hca-1"
        assert response.contract_type is ContractType.CDI
        assert response.address.city == "Paris"

    def test_collections_default_to_empty(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A new assistant holds no qualification and declares no absence."""
        response = HcaResponse(**valid_response_kwargs)
        assert response.certifications == []
        assert response.availability == []
        assert response.driving_license is None
        assert response.photo_url is None

    def test_names_are_stripped(self, valid_response_kwargs: Dict[str, Any]) -> None:
        """Surrounding whitespace never reaches a client."""
        response = HcaResponse(
            **{
                **valid_response_kwargs,
                "first_name": "  Marie ",
                "last_name": " Durand ",
            }
        )
        assert response.first_name == "Marie"
        assert response.last_name == "Durand"

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - blank"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_an_invalid_id_raises(
        self, valid_response_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """An identifier that is neither None nor a real string is rejected."""
        with pytest.raises(MTHcaResponseInvalidId):
            HcaResponse(**{**valid_response_kwargs, "id": invalid_value})

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param("first_name", id="first_name"),
            pytest.param("last_name", id="last_name"),
        ],
    )
    def test_an_empty_name_raises(
        self, valid_response_kwargs: Dict[str, Any], field: str
    ) -> None:
        """A name that is not a non-empty string is rejected."""
        with pytest.raises(MTHcaResponseInvalidName):
            HcaResponse(**{**valid_response_kwargs, field: "   "})

    def test_an_unknown_contract_type_raises(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A contract the stack does not know is rejected."""
        with pytest.raises(MTHcaResponseInvalidContractType):
            HcaResponse(**{**valid_response_kwargs, "contract_type": "freelance"})

    def test_a_contract_string_is_coerced(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A stored contract value rebuilds into its enum."""
        response = HcaResponse(**{**valid_response_kwargs, "contract_type": "cdd"})
        assert response.contract_type is ContractType.CDD

    def test_an_unparseable_timestamp_raises(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A timestamp that is not ISO-8601 is rejected."""
        with pytest.raises(MTHcaResponseInvalidDate):
            HcaResponse(**{**valid_response_kwargs, "updated_at": "yesterday"})

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTHcaResponseInvalidContractType,
            MTHcaResponseInvalidDate,
            MTHcaResponseInvalidId,
            MTHcaResponseInvalidName,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidHcaResponseException."""
        assert issubclass(exception_class, MTInvalidHcaResponseException)

    # ------------------------------------------------------------------ #
    #  Building from the domain model
    # ------------------------------------------------------------------ #

    def test_from_hca_carries_every_published_field(
        self, address: PostalAddress
    ) -> None:
        """The whole assistant crosses the boundary, children included."""
        hca = Hca(
            id="hca-1",
            first_name="Marie",
            last_name="Durand",
            phone_number="+33612345678",
            email="marie.durand@example.com",
            address=address,
            contract_type=ContractType.CDI,
            certifications=[
                Certification(
                    name="Diplôme d'État d'Aide-Soignant",
                    issuer="Ministère de la Santé",
                    obtained_on=date(2020, 6, 1),
                )
            ],
            driving_license=DrivingLicense(categories=["B"], number="12AB34567"),
            photo_url="https://example.com/hca-photos/hca-1.jpg",
            availability=[
                AvailabilitySlot(
                    hca_id="hca-1",
                    start_date=date(2026, 8, 10),
                    end_date=date(2026, 8, 20),
                    kind=AvailabilityKind.HOLIDAY,
                )
            ],
            created_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 5, 13, 0, tzinfo=UTC),
        )
        response = HcaResponse.from_hca(hca)
        assert response.id == "hca-1"
        assert len(response.certifications) == 1
        assert len(response.availability) == 1
        assert response.driving_license is not None
        assert response.driving_license.categories == ["B"]
        assert response.address.latitude == pytest.approx(48.8566)

    def test_from_hca_serializes_to_json(self, address: PostalAddress) -> None:
        """The published shape is JSON, not Python objects."""
        hca = Hca(
            id="hca-1",
            first_name="Marie",
            last_name="Durand",
            phone_number="+33612345678",
            email="marie.durand@example.com",
            address=address,
            contract_type=ContractType.CDI,
            photo_url="https://example.com/hca-photos/hca-1.jpg",
            updated_at=datetime(2026, 8, 5, 13, 0, tzinfo=UTC),
        )
        published = HcaResponse.from_hca(hca).model_dump(mode="json")
        assert published["contract_type"] == "cdi"
        assert published["updated_at"] == "2026-08-05T13:00:00+00:00"
        assert published["photo_url"] == "https://example.com/hca-photos/hca-1.jpg"
