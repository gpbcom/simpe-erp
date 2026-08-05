from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.enums import ContractType
from models.people.certification import Certification
from models.people.driving_license import DrivingLicense
from models.people.exceptions import (
    MTHcaInvalidAddress,
    MTHcaInvalidAvailability,
    MTHcaInvalidCertifications,
    MTHcaInvalidContractType,
    MTHcaInvalidDate,
    MTHcaInvalidDrivingLicense,
    MTHcaInvalidEmail,
    MTHcaInvalidFirstName,
    MTHcaInvalidId,
    MTHcaInvalidLastName,
    MTHcaInvalidPhoneNumber,
    MTHcaInvalidPhotoUrl,
    MTInvalidHcaException,
)
from models.people.hca import Hca


@pytest.fixture
def valid_hca_kwargs() -> Dict[str, Any]:
    """Return the keyword arguments for a valid assistant.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "first_name": "Luc",
        "last_name": "Martin",
        "phone_number": "+33612345678",
        "email": "luc.martin@example.com",
        "address": {
            "street": "5 avenue de la Gare",
            "postal_code": "75012",
            "city": "Paris",
        },
        "contract_type": ContractType.CDI,
    }


class TestHca:
    """Tests for the Hca model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(self, valid_hca_kwargs: Dict[str, Any]) -> None:
        """An assistant is a name, contact details, an address and a contract."""
        hca = Hca(**valid_hca_kwargs)
        assert hca.full_name() == "Luc Martin"
        assert hca.contract_type is ContractType.CDI

    def test_collections_default_to_empty(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A fresh assistant holds no certification and no absence."""
        hca = Hca(**valid_hca_kwargs)
        assert hca.certifications == []
        assert hca.availability == []
        assert hca.driving_license is None
        assert hca.photo_url is None

    def test_contract_type_is_coerced_from_a_string(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A string contract becomes a ContractType member."""
        hca = Hca(**{**valid_hca_kwargs, "contract_type": "cdd"})
        assert hca.contract_type is ContractType.CDD

    def test_nested_models_are_built_from_mappings(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """Certifications, licence and availability accept mappings."""
        hca = Hca(
            **{
                **valid_hca_kwargs,
                "certifications": [{"name": "DEAVS"}],
                "driving_license": {"categories": ["B"]},
                "availability": [
                    {
                        "hca_id": "hca-1",
                        "start_date": "2026-08-10",
                        "end_date": "2026-08-14",
                        "kind": "holiday",
                    }
                ],
            }
        )
        assert isinstance(hca.certifications[0], Certification)
        assert isinstance(hca.driving_license, DrivingLicense)
        assert hca.availability[0].kind.value == "holiday"

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("field", "invalid_value", "expected_exception"),
        [
            pytest.param("id", "", MTHcaInvalidId, id="Invalid - empty id"),
            pytest.param(
                "first_name", "", MTHcaInvalidFirstName, id="Invalid - empty first_name"
            ),
            pytest.param(
                "last_name", None, MTHcaInvalidLastName, id="Invalid - None last_name"
            ),
            pytest.param(
                "phone_number", "", MTHcaInvalidPhoneNumber, id="Invalid - empty phone"
            ),
            pytest.param("email", None, MTHcaInvalidEmail, id="Invalid - None email"),
            pytest.param(
                "address",
                "5 avenue",
                MTHcaInvalidAddress,
                id="Invalid - string address",
            ),
            pytest.param(
                "contract_type",
                "freelance",
                MTHcaInvalidContractType,
                id="Invalid - unknown contract",
            ),
            pytest.param(
                "certifications",
                "DEAVS",
                MTHcaInvalidCertifications,
                id="Invalid - string certifications",
            ),
            pytest.param(
                "driving_license",
                "B",
                MTHcaInvalidDrivingLicense,
                id="Invalid - string licence",
            ),
            pytest.param(
                "photo_url", 42, MTHcaInvalidPhotoUrl, id="Invalid - int photo_url"
            ),
            pytest.param(
                "availability",
                "holiday",
                MTHcaInvalidAvailability,
                id="Invalid - string availability",
            ),
            pytest.param(
                "created_at", 1234567890, MTHcaInvalidDate, id="Invalid - int timestamp"
            ),
        ],
    )
    def test_invalid_fields_raise(
        self,
        valid_hca_kwargs: Dict[str, Any],
        field: str,
        invalid_value: Any,
        expected_exception: type,
    ) -> None:
        """Each field rejects its own invalid values with its own exception."""
        with pytest.raises(expected_exception):
            Hca(**{**valid_hca_kwargs, field: invalid_value})

    def test_invalid_certification_entry_raises(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A list entry that is neither a mapping nor a model is rejected."""
        with pytest.raises(MTHcaInvalidCertifications):
            Hca(**{**valid_hca_kwargs, "certifications": ["DEAVS"]})

    def test_invalid_availability_entry_raises(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A list entry that is neither a mapping nor a model is rejected."""
        with pytest.raises(MTHcaInvalidAvailability):
            Hca(**{**valid_hca_kwargs, "availability": ["2026-08-10"]})

    def test_a_blank_photo_url_becomes_none(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """An empty form field reads as "no photo", not as an error.

        Notes:
            The portrait is optional by requirement, so a blank value must not
            block saving an assistant.
        """
        assert Hca(**{**valid_hca_kwargs, "photo_url": "   "}).photo_url is None

    # ------------------------------------------------------------------ #
    #  can_drive
    # ------------------------------------------------------------------ #

    def test_no_licence_means_no_driving(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """An assistant without a licence is routed at transit speed."""
        assert Hca(**valid_hca_kwargs).can_drive() is False

    def test_a_car_licence_means_driving(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A category B licence permits routing at driving speed."""
        hca = Hca(**{**valid_hca_kwargs, "driving_license": {"categories": ["B"]}})
        assert hca.can_drive() is True

    def test_a_motorcycle_licence_does_not_mean_driving(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A motorcycle-only licence is not a car licence."""
        hca = Hca(**{**valid_hca_kwargs, "driving_license": {"categories": ["A2"]}})
        assert hca.can_drive() is False

    # ------------------------------------------------------------------ #
    #  is_available_on / blocking_slots_on
    # ------------------------------------------------------------------ #

    def test_an_assistant_with_no_absences_is_always_available(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """Assistants are full-time; only exceptions are recorded."""
        assert Hca(**valid_hca_kwargs).is_available_on(date(2026, 8, 12)) is True

    def test_a_whole_day_absence_removes_the_day(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A whole-day slot makes the assistant unavailable."""
        hca = Hca(
            **{
                **valid_hca_kwargs,
                "availability": [
                    {
                        "hca_id": "hca-1",
                        "start_date": date(2026, 8, 10),
                        "end_date": date(2026, 8, 14),
                        "kind": "holiday",
                    }
                ],
            }
        )
        assert hca.is_available_on(date(2026, 8, 12)) is False
        assert hca.is_available_on(date(2026, 8, 17)) is True

    def test_a_partial_absence_leaves_the_day_workable(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A morning off does not remove the whole day.

        Notes:
            The solver models the window as a blocking interval rather than as
            an absence, so the afternoon is still schedulable.
        """
        hca = Hca(
            **{
                **valid_hca_kwargs,
                "availability": [
                    {
                        "hca_id": "hca-1",
                        "start_date": date(2026, 8, 12),
                        "end_date": date(2026, 8, 12),
                        "kind": "training",
                        "start_time": time(9, 0),
                        "end_time": time(12, 0),
                    }
                ],
            }
        )
        assert hca.is_available_on(date(2026, 8, 12)) is True
        blocking = hca.blocking_slots_on(date(2026, 8, 12))
        assert len(blocking) == 1
        assert blocking[0].start_time == time(9, 0)

    def test_blocking_slots_exclude_whole_day_absences(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A whole-day slot is an absence, not a blocking interval."""
        hca = Hca(
            **{
                **valid_hca_kwargs,
                "availability": [
                    {
                        "hca_id": "hca-1",
                        "start_date": date(2026, 8, 12),
                        "end_date": date(2026, 8, 12),
                        "kind": "holiday",
                    }
                ],
            }
        )
        assert hca.blocking_slots_on(date(2026, 8, 12)) == []

    def test_blocking_slots_ignore_other_days(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """Only slots covering the day in question are returned."""
        hca = Hca(
            **{
                **valid_hca_kwargs,
                "availability": [
                    {
                        "hca_id": "hca-1",
                        "start_date": date(2026, 8, 12),
                        "end_date": date(2026, 8, 12),
                        "kind": "training",
                        "start_time": time(9, 0),
                        "end_time": time(12, 0),
                    }
                ],
            }
        )
        assert hca.blocking_slots_on(date(2026, 8, 13)) == []

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTHcaInvalidAddress,
            MTHcaInvalidAvailability,
            MTHcaInvalidCertifications,
            MTHcaInvalidContractType,
            MTHcaInvalidDate,
            MTHcaInvalidDrivingLicense,
            MTHcaInvalidEmail,
            MTHcaInvalidFirstName,
            MTHcaInvalidId,
            MTHcaInvalidLastName,
            MTHcaInvalidPhoneNumber,
            MTHcaInvalidPhotoUrl,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidHcaException."""
        assert issubclass(exception_class, MTInvalidHcaException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_the_photo_url_serializes_to_a_string(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """The URL leaves the model as plain text, not as a URL object."""
        stored = "https://rt-erp.s3.fr-par.amazonaws.com/hca-photos/h1/a.jpg"
        hca = Hca(**{**valid_hca_kwargs, "photo_url": stored})
        assert hca.model_dump()["photo_url"] == stored

    def test_a_stored_photo_url_is_accepted(
        self, valid_hca_kwargs: Dict[str, Any]
    ) -> None:
        """A URL the object store issued is what the field is for."""
        stored = "https://minio.internal/rt-erp/hca-photos/h1/a.png"
        assert Hca(**{**valid_hca_kwargs, "photo_url": stored}).photo_url is not None

    @pytest.mark.parametrize(
        "foreign_url",
        [
            pytest.param(
                "https://evil.example.com/pic.jpg", id="Invalid - third party"
            ),
            pytest.param(
                "https://rt-erp.s3.amazonaws.com/backups/dump.sql",
                id="Invalid - wrong prefix",
            ),
            pytest.param("ftp://host/hca-photos/a.jpg", id="Invalid - wrong scheme"),
            pytest.param("/hca-photos/a.jpg", id="Invalid - relative"),
        ],
    )
    def test_a_url_outside_the_object_store_is_rejected(
        self, valid_hca_kwargs: Dict[str, Any], foreign_url: str
    ) -> None:
        """Only a photograph this application stored may be linked.

        Notes:
            Accepting an arbitrary URL would make the application render a
            remote image it does not control, and disclose every viewer's
            address to whoever hosts it.
        """
        with pytest.raises(MTHcaInvalidPhotoUrl):
            Hca(**{**valid_hca_kwargs, "photo_url": foreign_url})

    def test_model_dump_round_trip(self, valid_hca_kwargs: Dict[str, Any]) -> None:
        """An assistant survives a dump-and-rebuild unchanged."""
        hca = Hca(
            **{
                **valid_hca_kwargs,
                "certifications": [{"name": "DEAVS"}],
                "driving_license": {"categories": ["B"]},
            }
        )
        assert Hca(**hca.model_dump()) == hca
