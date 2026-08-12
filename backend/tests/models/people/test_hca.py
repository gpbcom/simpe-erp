from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.enums import ContractType, Weekday
from models.people.hca.certification import Certification
from models.people.hca.driving_license import DrivingLicense
from models.people.hca.exceptions import (
    MTHcaInvalidAddress,
    MTHcaInvalidAvailability,
    MTHcaInvalidCertifications,
    MTHcaInvalidContractType,
    MTHcaInvalidDate,
    MTHcaInvalidDrivingLicense,
    MTHcaInvalidEmail,
    MTHcaInvalidFieldEmployee,
    MTHcaInvalidFirstName,
    MTHcaInvalidId,
    MTHcaInvalidLastName,
    MTHcaInvalidPhoneNumber,
    MTHcaInvalidPhotoUrl,
    MTHcaInvalidWorkingWeekdays,
    MTInvalidHcaException,
)
from models.people.hca import Hca
from tests.annotations import ModelInput


@pytest.fixture
def valid_hca_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid assistant.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
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

    def test_minimal_valid_construction(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An assistant is a name, contact details, an address and a contract."""
        hca = Hca(company_id="company-1", **valid_hca_kwargs)
        assert hca.full_name() == "Luc Martin"
        assert hca.contract_type is ContractType.CDI

    def test_collections_default_to_empty(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A fresh assistant holds no certification and no absence."""
        hca = Hca(company_id="company-1", **valid_hca_kwargs)
        assert hca.certifications == []
        assert hca.availability == []
        assert hca.driving_license is None
        assert hca.photo_url is None

    def test_contract_type_is_coerced_from_a_string(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A string contract becomes a ContractType member."""
        hca = Hca(
            company_id="company-1", **{**valid_hca_kwargs, "contract_type": "cdd"}
        )
        assert hca.contract_type is ContractType.CDD

    def test_nested_models_are_built_from_mappings(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Certifications, licence and availability accept mappings."""
        hca = Hca(
            company_id="company-1",
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
            },
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
        valid_hca_kwargs: Dict[str, ModelInput],
        field: str,
        invalid_value: ModelInput,
        expected_exception: type,
    ) -> None:
        """Each field rejects its own invalid values with its own exception."""
        with pytest.raises(expected_exception):
            Hca(company_id="company-1", **{**valid_hca_kwargs, field: invalid_value})

    def test_invalid_certification_entry_raises(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A list entry that is neither a mapping nor a model is rejected."""
        with pytest.raises(MTHcaInvalidCertifications):
            Hca(
                company_id="company-1",
                **{**valid_hca_kwargs, "certifications": ["DEAVS"]},
            )

    def test_invalid_availability_entry_raises(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A list entry that is neither a mapping nor a model is rejected."""
        with pytest.raises(MTHcaInvalidAvailability):
            Hca(
                company_id="company-1",
                **{**valid_hca_kwargs, "availability": ["2026-08-10"]},
            )

    def test_a_blank_photo_url_becomes_none(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An empty form field reads as "no photo", not as an error.

        Notes:
            The portrait is optional by requirement, so a blank value must not
            block saving an assistant.
        """
        assert (
            Hca(
                company_id="company-1", **{**valid_hca_kwargs, "photo_url": "   "}
            ).photo_url
            is None
        )

    # ------------------------------------------------------------------ #
    #  can_drive
    # ------------------------------------------------------------------ #

    def test_no_licence_means_no_driving(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An assistant without a licence is routed at transit speed."""
        assert Hca(company_id="company-1", **valid_hca_kwargs).can_drive() is False

    def test_a_car_licence_means_driving(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A category B licence permits routing at driving speed."""
        hca = Hca(
            company_id="company-1",
            **{**valid_hca_kwargs, "driving_license": {"categories": ["B"]}},
        )
        assert hca.can_drive() is True

    def test_a_motorcycle_licence_does_not_mean_driving(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A motorcycle-only licence is not a car licence."""
        hca = Hca(
            company_id="company-1",
            **{**valid_hca_kwargs, "driving_license": {"categories": ["A2"]}},
        )
        assert hca.can_drive() is False

    # ------------------------------------------------------------------ #
    #  is_available_on / blocking_slots_on
    # ------------------------------------------------------------------ #

    def test_an_assistant_with_no_absences_is_always_available(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Assistants are full-time; only exceptions are recorded."""
        assert (
            Hca(company_id="company-1", **valid_hca_kwargs).is_available_on(
                date(2026, 8, 12)
            )
            is True
        )

    def test_a_whole_day_absence_removes_the_day(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A whole-day slot makes the assistant unavailable."""
        hca = Hca(
            company_id="company-1",
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
            },
        )
        assert hca.is_available_on(date(2026, 8, 12)) is False
        assert hca.is_available_on(date(2026, 8, 17)) is True

    def test_a_partial_absence_leaves_the_day_workable(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A morning off does not remove the whole day.

        Notes:
            The solver models the window as a blocking interval rather than as
            an absence, so the afternoon is still schedulable.
        """
        hca = Hca(
            company_id="company-1",
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
            },
        )
        assert hca.is_available_on(date(2026, 8, 12)) is True
        blocking = hca.blocking_slots_on(date(2026, 8, 12))
        assert len(blocking) == 1
        assert blocking[0].start_time == time(9, 0)

    def test_blocking_slots_exclude_whole_day_absences(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A whole-day slot is an absence, not a blocking interval."""
        hca = Hca(
            company_id="company-1",
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
            },
        )
        assert hca.blocking_slots_on(date(2026, 8, 12)) == []

    def test_blocking_slots_ignore_other_days(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Only slots covering the day in question are returned."""
        hca = Hca(
            company_id="company-1",
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
            },
        )
        assert hca.blocking_slots_on(date(2026, 8, 13)) == []

    # ------------------------------------------------------------------ #
    #  working_weekdays
    # ------------------------------------------------------------------ #

    def test_a_new_assistant_works_the_standard_week(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Monday to Friday is what a full-time hire means by default."""
        hca = Hca(company_id="company-1", **valid_hca_kwargs)

        assert hca.working_weekdays == [
            Weekday.MONDAY,
            Weekday.TUESDAY,
            Weekday.WEDNESDAY,
            Weekday.THURSDAY,
            Weekday.FRIDAY,
        ]

    def test_the_working_week_is_sorted_and_deduplicated(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Two spellings of the same week must not compare differently.

        Notes:
            The set is stored as a delimited string, so ``["friday",
            "monday"]`` and ``["monday", "friday"]`` would otherwise produce
            two different column values for one working week.
        """
        hca = Hca(
            company_id="company-1",
            **{
                **valid_hca_kwargs,
                "working_weekdays": ["friday", "monday", "friday"],
            },
        )

        assert hca.working_weekdays == [Weekday.MONDAY, Weekday.FRIDAY]

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            pytest.param(date(2026, 8, 10), True, id="a Monday they work"),
            pytest.param(date(2026, 8, 12), False, id="a Wednesday they do not"),
            pytest.param(date(2026, 8, 15), False, id="a Saturday nobody works"),
        ],
    )
    def test_a_day_off_in_the_week_is_not_worked(
        self, valid_hca_kwargs: Dict[str, ModelInput], day: date, expected: bool
    ) -> None:
        """The recurring pattern answers per weekday, not per date.

        Args:
            valid_hca_kwargs (Dict[str, ModelInput]): Base constructor arguments.
            day (date): The day to test.
            expected (bool): Whether it should be worked.
        """
        hca = Hca(
            company_id="company-1",
            **{
                **valid_hca_kwargs,
                "working_weekdays": ["monday", "tuesday", "thursday", "friday"],
            },
        )

        assert hca.works_on_weekday(day) is expected

    def test_a_day_off_is_not_an_absence(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The two questions stay separate, and only one of them is dated.

        Notes:
            This is what lets the unplaced-work report tell a manager whether
            to hire cover for a Wednesday or to wait for somebody to come back
            from leave. Folding the two together would report the second when
            the first is true.
        """
        hca = Hca(
            company_id="company-1",
            **{**valid_hca_kwargs, "working_weekdays": ["monday", "tuesday"]},
        )
        wednesday = date(2026, 8, 12)

        assert hca.works_on_weekday(wednesday) is False
        assert hca.is_available_on(wednesday) is True
        assert hca.is_schedulable_on(wednesday) is False

    def test_an_absence_on_a_working_day_still_blocks_it(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Both halves have to hold for the solver to offer work."""
        hca = Hca(
            company_id="company-1",
            **{
                **valid_hca_kwargs,
                "working_weekdays": ["monday", "tuesday", "wednesday"],
                "availability": [
                    {
                        "hca_id": "hca-1",
                        "start_date": date(2026, 8, 12),
                        "end_date": date(2026, 8, 12),
                        "kind": "sick-leave",
                    }
                ],
            },
        )
        wednesday = date(2026, 8, 12)

        assert hca.works_on_weekday(wednesday) is True
        assert hca.is_available_on(wednesday) is False
        assert hca.is_schedulable_on(wednesday) is False

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param([], id="Invalid - works no day at all"),
            pytest.param(["funday"], id="Invalid - not a weekday"),
            pytest.param(["monday", "mondee"], id="Invalid - one bad entry"),
            pytest.param("monday", id="Invalid - a bare string, not a list"),
            pytest.param(7, id="Invalid - not a collection"),
        ],
    )
    def test_an_unusable_working_week_is_refused(
        self, valid_hca_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """An empty week is a statement, not a request for the default.

        Args:
            valid_hca_kwargs (Dict[str, ModelInput]): Base constructor arguments.
            value (ModelInput): The rejected working week.

        Notes:
            Silently restoring Monday-to-Friday for an empty list would put
            somebody back on rounds they had just declined.
        """
        with pytest.raises(MTHcaInvalidWorkingWeekdays):
            Hca(
                company_id="company-1",
                **{**valid_hca_kwargs, "working_weekdays": value},
            )

    def test_the_working_week_exception_shares_the_model_base(self) -> None:
        """One except clause still catches everything this model raises."""
        assert issubclass(MTHcaInvalidWorkingWeekdays, MTInvalidHcaException)

    # ------------------------------------------------------------------ #
    #  field_employee
    # ------------------------------------------------------------------ #

    def test_an_assistant_goes_out_on_rounds_by_default(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The default is what every record that predates the field already was.

        Notes:
            Defaulting to False would have emptied the workforce on the
            deployment that introduced the field and failed every planning run
            until somebody ticked a box they had not been told about.
        """
        assert Hca(company_id="company-1", **valid_hca_kwargs).field_employee is True

    def test_field_employee_can_be_cleared(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Somebody on office duties is held back from the planning."""
        assistant = Hca(
            company_id="company-1", **valid_hca_kwargs, field_employee=False
        )
        assert assistant.field_employee is False

    def test_a_none_flag_falls_back_to_going_out(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A row written before the column existed reads back as schedulable."""
        assert (
            Hca(
                company_id="company-1", **valid_hca_kwargs, field_employee=None
            ).field_employee
            is True
        )

    @pytest.mark.parametrize(
        "invalid_flag",
        [
            pytest.param("false", id="Invalid - string false"),
            pytest.param("true", id="Invalid - string true"),
            pytest.param(0, id="Invalid - int"),
            pytest.param([], id="Invalid - list"),
        ],
    )
    def test_invalid_field_employee_raises(
        self, valid_hca_kwargs: Dict[str, ModelInput], invalid_flag: ModelInput
    ) -> None:
        """The flag is a boolean, never a truthy string.

        Notes:
            ``"false"`` is truthy in Python. Coercing it would put somebody who
            does not go out on the road back onto a round, and coercing the
            reverse would withdraw an assistant from the workforce with nothing
            on any screen to say why.
        """
        with pytest.raises(MTHcaInvalidFieldEmployee):
            Hca(company_id="company-1", **valid_hca_kwargs, field_employee=invalid_flag)

    # ------------------------------------------------------------------ #
    #  holds_certifications
    # ------------------------------------------------------------------ #

    def test_work_requiring_nothing_is_satisfied_by_everybody(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An assistant with no qualifications can still do unqualified work."""
        assistant = Hca(company_id="company-1", **valid_hca_kwargs)
        assert assistant.holds_certifications([], date(2026, 8, 5)) is True

    def test_a_held_code_qualifies(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A matching, unlapsed qualification meets the requirement."""
        assistant = Hca(
            company_id="company-1",
            **valid_hca_kwargs,
            certifications=[Certification(name="DEAES", code="DEAES")],
        )
        assert assistant.holds_certifications(["DEAES"], date(2026, 8, 5)) is True

    def test_every_code_is_needed_not_just_one(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A requirement listing two diplomas means the person needs both.

        Notes:
            Reading it as "one of these" would send somebody to a visit half
            qualified, which is the failure the whole field exists to prevent.
        """
        assistant = Hca(
            company_id="company-1",
            **valid_hca_kwargs,
            certifications=[Certification(name="DEAES", code="DEAES")],
        )
        assert (
            assistant.holds_certifications(["DEAES", "SST"], date(2026, 8, 5)) is False
        )

    def test_a_lapsed_qualification_does_not_count(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Expiry is measured against the day of the visit."""
        assistant = Hca(
            company_id="company-1",
            **valid_hca_kwargs,
            certifications=[
                Certification(name="SST", code="SST", expires_on=date(2026, 8, 4))
            ],
        )
        assert assistant.holds_certifications(["SST"], date(2026, 8, 5)) is False
        assert assistant.holds_certifications(["SST"], date(2026, 8, 4)) is True

    def test_an_untyped_qualification_does_not_count(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A free-text name is not a claim the agency can match against."""
        assistant = Hca(
            company_id="company-1",
            **valid_hca_kwargs,
            certifications=[Certification(name="DEAES")],
        )
        assert assistant.holds_certifications(["DEAES"], date(2026, 8, 5)) is False

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
            MTHcaInvalidFieldEmployee,
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
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The URL leaves the model as plain text, not as a URL object."""
        stored = "https://simple-erp.s3.fr-par.amazonaws.com/hca-photos/h1/a.jpg"
        hca = Hca(company_id="company-1", **{**valid_hca_kwargs, "photo_url": stored})
        assert hca.model_dump()["photo_url"] == stored

    def test_a_stored_photo_url_is_accepted(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A URL the object store issued is what the field is for."""
        stored = "https://minio.internal/simple-erp/hca-photos/h1/a.png"
        assert (
            Hca(
                company_id="company-1", **{**valid_hca_kwargs, "photo_url": stored}
            ).photo_url
            is not None
        )

    @pytest.mark.parametrize(
        "foreign_url",
        [
            pytest.param(
                "https://evil.example.com/pic.jpg", id="Invalid - third party"
            ),
            pytest.param(
                "https://simple-erp.s3.amazonaws.com/backups/dump.sql",
                id="Invalid - wrong prefix",
            ),
            pytest.param("ftp://host/hca-photos/a.jpg", id="Invalid - wrong scheme"),
            pytest.param("/hca-photos/a.jpg", id="Invalid - relative"),
        ],
    )
    def test_a_url_outside_the_object_store_is_rejected(
        self, valid_hca_kwargs: Dict[str, ModelInput], foreign_url: str
    ) -> None:
        """Only a photograph this application stored may be linked.

        Notes:
            Accepting an arbitrary URL would make the application render a
            remote image it does not control, and disclose every viewer's
            address to whoever hosts it.
        """
        with pytest.raises(MTHcaInvalidPhotoUrl):
            Hca(
                company_id="company-1", **{**valid_hca_kwargs, "photo_url": foreign_url}
            )

    def test_model_dump_round_trip(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An assistant survives a dump-and-rebuild unchanged."""
        hca = Hca(
            company_id="company-1",
            **{
                **valid_hca_kwargs,
                "certifications": [{"name": "DEAVS"}],
                "driving_license": {"categories": ["B"]},
            },
        )
        assert Hca(**hca.model_dump()) == hca
