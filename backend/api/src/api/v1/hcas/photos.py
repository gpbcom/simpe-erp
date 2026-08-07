from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends, File, UploadFile

# First-party imports
from api.dependencies import get_app_config, get_hca_service, get_manager_user
from models.auth.user import User
from models.schemas.responses.hca.hca_response import HcaResponse
from models.schemas.responses.hca.photo_constraints_response import (
    PhotoConstraintsResponse,
)
from service.hcas.hcas import HcaService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/hcas", tags=["Assistant photographs"])


@router.put("/{hca_id}/photo", response_model=HcaResponse)
async def upload_photo(
    hca_id: str,
    photo: UploadFile = File(...),
    service: HcaService = Depends(get_hca_service),
    _: User = Depends(get_manager_user),
) -> HcaResponse:
    """Store an assistant's photograph in the object store.

    Args:
        hca_id (str): The assistant the photograph belongs to.
        photo (UploadFile): The uploaded image.
        service (HcaService): The photograph service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        HcaResponse: The updated assistant, whose ``photo_url`` now points at
        the stored object.

    Raises:
        MTHcaNotFound: If the assistant does not exist; answered as a 404.
        MTS3PayloadTooLarge: If the file exceeds the configured limit;
            answered as a 413.
        MTS3UnsupportedContentType: If it is not an accepted image; answered
            as a 415.
        MTS3EmptyPayload: If it is empty; answered as a 422.
        MTS3BucketUnavailable: If the object store cannot be reached; answered
            as a 503.
        MTS3UploadFailed: If the write itself failed; answered as a 500.

    Notes:
        - The whole file is read into memory before it is uploaded, so its real
          size and format can be checked before anything is written. The size is
          bounded by the configured limit, which is itself capped, so a single
          request cannot exhaust the process's memory.
        - The declared ``Content-Type`` is ignored: the store decides the type
          from the file's own leading bytes. A client controls that header
          completely, and a bucket serving attacker-chosen content types is how a
          stored file becomes a stored cross-site-scripting payload.
    """
    payload = await photo.read()
    logger.info("Received a %d-byte photograph for assistant %s.", len(payload), hca_id)
    updated = await service.set_photo(hca_id, payload)
    return HcaResponse.from_hca(updated)


@router.delete("/{hca_id}/photo", response_model=HcaResponse)
async def delete_photo(
    hca_id: str,
    service: HcaService = Depends(get_hca_service),
    _: User = Depends(get_manager_user),
) -> HcaResponse:
    """Remove an assistant's photograph.

    Args:
        hca_id (str): The assistant to clear.
        service (HcaService): The photograph service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        HcaResponse: The updated assistant, with no photograph.

    Raises:
        MTHcaNotFound: If the assistant does not exist; answered as a 404.
        MTS3BucketUnavailable: If the object store cannot be reached; answered
            as a 503.
    """
    updated = await service.clear_photo(hca_id)
    logger.info("Assistant %s no longer has a photograph.", hca_id)
    return HcaResponse.from_hca(updated)


@router.get("/photo-constraints", response_model=PhotoConstraintsResponse)
async def photo_constraints(
    _: User = Depends(get_manager_user),
) -> PhotoConstraintsResponse:
    """Report what the photograph endpoint accepts.

    Args:
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        PhotoConstraintsResponse: The accepted image types and the size limit.

    Notes:
        Declared before ``/{hca_id}/photo`` would otherwise be a routing
        hazard — it is not, because the paths differ in shape, but the client
        needs these limits to reject an oversized file before uploading it
        rather than after.
    """
    config = get_app_config().s3
    logger.debug(
        "Reporting the photograph constraints: %d bytes, %d content type(s).",
        config.max_upload_bytes,
        len(config.ALLOWED_PHOTO_CONTENT_TYPES),
    )
    return PhotoConstraintsResponse(
        max_upload_bytes=config.max_upload_bytes,
        accepted_content_types=list(config.ALLOWED_PHOTO_CONTENT_TYPES),
    )
