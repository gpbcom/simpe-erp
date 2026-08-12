from __future__ import annotations

# Standard library imports

# Third-party imports
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTInvalidPhotoConstraintsResponseException,
    MTPhotoConstraintsResponseInvalidContentTypes,
    MTPhotoConstraintsResponseInvalidMaxUploadBytes,
)
from models.schemas.responses.hca.photo_constraints_response import (
    PhotoConstraintsResponse,
)
from tests.annotations import ModelInput


class TestPhotoConstraintsResponse:
    """Tests for the PhotoConstraintsResponse schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_publishes_the_limit_and_the_types(self) -> None:
        """A client learns what it may upload before it uploads it."""
        response = PhotoConstraintsResponse(
            max_upload_bytes=5_242_880,
            accepted_content_types=["image/jpeg", "image/png"],
        )
        assert response.max_upload_bytes == 5_242_880
        assert response.accepted_content_types == ["image/jpeg", "image/png"]

    def test_content_types_are_normalised(self) -> None:
        """A type is published in the form a client compares against."""
        response = PhotoConstraintsResponse(
            max_upload_bytes=1,
            accepted_content_types=[" Image/JPEG ", "IMAGE/PNG"],
        )
        assert response.accepted_content_types == ["image/jpeg", "image/png"]

    def test_a_tuple_of_types_is_accepted(self) -> None:
        """The configuration holds a tuple; the response publishes a list."""
        response = PhotoConstraintsResponse(
            max_upload_bytes=1, accepted_content_types=("image/webp",)
        )
        assert response.accepted_content_types == ["image/webp"]

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(1.5, id="Invalid - float"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param("5242880", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_invalid_limit_raises(self, invalid_value: ModelInput) -> None:
        """A limit that is not a positive integer is rejected.

        Notes:
            ``True`` is included deliberately: it is an ``int`` in Python, and
            a one-byte limit would reject every photograph while looking like a
            configured value.
        """
        with pytest.raises(MTPhotoConstraintsResponseInvalidMaxUploadBytes):
            PhotoConstraintsResponse(
                max_upload_bytes=invalid_value,
                accepted_content_types=["image/jpeg"],
            )

    def test_an_empty_type_list_raises(self) -> None:
        """Publishing no accepted type would mean nothing can be uploaded."""
        with pytest.raises(MTPhotoConstraintsResponseInvalidContentTypes):
            PhotoConstraintsResponse(max_upload_bytes=1, accepted_content_types=[])

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("image/jpeg", id="Invalid - bare string"),
            pytest.param(None, id="Invalid - None"),
            pytest.param([""], id="Invalid - empty entry"),
            pytest.param([42], id="Invalid - non-string entry"),
        ],
    )
    def test_invalid_content_types_raise(self, invalid_value: ModelInput) -> None:
        """Anything but a list of real content types is rejected."""
        with pytest.raises(MTPhotoConstraintsResponseInvalidContentTypes):
            PhotoConstraintsResponse(
                max_upload_bytes=1, accepted_content_types=invalid_value
            )

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTPhotoConstraintsResponseInvalidContentTypes,
            MTPhotoConstraintsResponseInvalidMaxUploadBytes,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the model's own family."""
        assert issubclass(exception_class, MTInvalidPhotoConstraintsResponseException)
