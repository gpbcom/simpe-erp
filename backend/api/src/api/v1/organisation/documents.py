from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, File, Response, UploadFile, status

# First-party imports
from api.dependencies import (
    get_app_config,
    get_current_user,
    get_team_document_service,
)
from models.auth.user import User
from models.organisation.team.team_document import TeamDocument
from models.schemas.responses.organisation.team_document_constraints_response import (
    TeamDocumentConstraintsResponse,
)
from service.organisation.team_documents import TeamDocumentService
from storage.s3.s3_storage import S3Storage

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/teams", tags=["Team documents"])


@router.get("/document-constraints", response_model=TeamDocumentConstraintsResponse)  # noqa: E501
async def team_document_constraints(
    _: User = Depends(get_current_user),
) -> TeamDocumentConstraintsResponse:
    """Report what a team's shared space accepts.

    Args:
        _ (User): The authenticated caller.

    Returns:
        TeamDocumentConstraintsResponse: The accepted media types and the size
        limit.

    Notes:
        Declared **before** ``/{team_id}/documents`` and, more to the point,
        before ``/{team_id}`` on the sibling router: FastAPI matches in
        declaration order, and ``document-constraints`` would otherwise be read
        as a team identifier and answered 404 by a lookup that can never
        succeed. The two routers are mounted in the order that keeps this true.
    """
    config = get_app_config().s3
    accepted = sorted(
        {media for _signature, media in S3Storage.TEAM_DOCUMENT_SIGNATURES}
    )  # noqa: E501
    logger.debug(
        "Reporting the teamspace constraints: %d bytes, %d media type(s).",
        config.max_upload_bytes,
        len(accepted),
    )
    return TeamDocumentConstraintsResponse(
        max_upload_bytes=config.max_upload_bytes,
        accepted_content_types=accepted,
    )


@router.get("/{team_id}/documents", response_model=List[TeamDocument])
async def list_team_documents(
    team_id: str,
    service: TeamDocumentService = Depends(get_team_document_service),
    caller: User = Depends(get_current_user),
) -> List[TeamDocument]:
    """Return the files a team shares.

    Args:
        team_id (str): The team whose space is being read.
        service (TeamDocumentService): The teamspace service.
        caller (User): The authenticated caller.

    Returns:
        List[TeamDocument]: The records, newest first.

    Raises:
        MTTeamNotFound: If no such team exists, or the caller is not on it;
            answered as a 404 in both cases, so a space somebody may not open is
            indistinguishable from one that does not exist.
    """
    logger.debug("Listing the documents of team %s for %s.", team_id, caller.email)  # noqa: E501
    return await service.list(team_id, caller)


@router.post(
    "/{team_id}/documents",
    response_model=TeamDocument,
    status_code=status.HTTP_201_CREATED,
)
async def upload_team_document(
    team_id: str,
    document: UploadFile = File(...),
    service: TeamDocumentService = Depends(get_team_document_service),
    caller: User = Depends(get_current_user),
) -> TeamDocument:
    """Add a file to a team's shared space.

    Args:
        team_id (str): The team whose space it joins.
        document (UploadFile): The uploaded file.
        service (TeamDocumentService): The teamspace service.
        caller (User): The member adding it.

    Returns:
        TeamDocument: The stored record.

    Raises:
        MTTeamNotFound: If no such team exists, or the caller is not on it; 404.
        MTTeamDocumentStorageUnavailable: If no object store is configured; 503.
        MTS3EmptyPayload: If the file carries no bytes. Answered as a 422.
        MTS3UnsupportedContentType: If it is not a shareable type; 415.
        MTS3PayloadTooLarge: If it exceeds the configured limit; 413.

    Notes:
        - **Guarded at ``get_current_user``, not at manager.** Everybody on the
          team may add a document — that is the requirement, and it is what makes
          the space shared rather than published. The check that actually
          matters, that the caller is on *this* team, is in the service, because
          membership is polymorphic and cannot be resolved from a credential
          alone.
        - The whole file is read into memory before anything is written, so its
          real type and size are known before an object exists. The size is
          bounded by the configured limit, so one request cannot exhaust the
          process.
        - The declared ``Content-Type`` is ignored. The store decides from the
          file's own leading bytes, for the same reason the photograph route
          does.
    """
    payload = await document.read()
    file_name = document.filename if document.filename else "document"
    logger.info(
        "Received %d bytes named %r for team %s from %s.",
        len(payload),
        file_name,
        team_id,
        caller.email,
    )
    return await service.upload(team_id, caller, file_name, payload)


@router.get("/{team_id}/documents/{document_id}")
async def download_team_document(
    team_id: str,
    document_id: str,
    service: TeamDocumentService = Depends(get_team_document_service),
    caller: User = Depends(get_current_user),
) -> Response:
    """Read one of a team's shared files back.

    Args:
        team_id (str): The team whose space it sits in.
        document_id (str): The record to read.
        service (TeamDocumentService): The teamspace service.
        caller (User): The authenticated caller.

    Returns:
        Response: The bytes, with the stored media type and the uploader's file
        name.

    Raises:
        MTTeamNotFound: If no such team exists, or the caller is not on it; 404.
        MTTeamDocumentNotFound: If no such document exists, or the object behind
            it could not be read. Answered as a 404.
        MTTeamDocumentStorageUnavailable: If no object store is configured; 503.

    Notes:
        - Declared with **no response model**: the body is bytes rather than a
          record, and there is no model to infer one from. The same reason the
          invoice download gives.
        - Served as an **attachment**, so a shared file is downloaded rather than
          rendered in the tab. The media type was detected from the file's own
          bytes, but a document nobody vetted is still somebody else's content
          being served from the application's origin.
    """
    payload, content_type, file_name = await service.download(
        team_id, document_id, caller
    )
    logger.info("Serving %d bytes of %s to %s.", len(payload), file_name, caller.email)
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.delete(
    "/{team_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_team_document(
    team_id: str,
    document_id: str,
    service: TeamDocumentService = Depends(get_team_document_service),
    caller: User = Depends(get_current_user),
) -> None:
    """Remove one of a team's shared files.

    Args:
        team_id (str): The team whose space it sits in.
        document_id (str): The record to remove.
        service (TeamDocumentService): The teamspace service.
        caller (User): The member removing it.

    Raises:
        MTTeamNotFound: If no such team exists, or the caller is not on it; 404.
        MTTeamDocumentNotFound: If no such document exists. Answered as a 404.
        MTTeamDocumentForbidden: If the caller neither uploaded it, runs the
            team, nor is an administrator. Answered as a 403.
        MTTeamDocumentStorageUnavailable: If no object store is configured; 503.

    Notes:
        Three people may remove a file and the route names none of them: whoever
        added it, the team's manager and an administrator are decided in the
        service, because only the record knows who uploaded it.
    """
    logger.info(
        "Removing document %s from team %s at the request of %s.",
        document_id,
        team_id,
        caller.email,
    )
    await service.delete(team_id, document_id, caller)
