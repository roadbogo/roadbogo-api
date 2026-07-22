from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.responses import success_response
from app.dependencies.auth import CurrentUser
from app.dependencies.permissions import require_permissions
from app.schemas.action_file import ActionFileListData, ActionFileUploadData, PhotoPhase
from app.schemas.common import SuccessResponse
from app.services import action_file
from app.services.file_storage import FileStorage, get_file_storage

router = APIRouter(prefix="/dispatches", tags=["action-files"])
UploadPermission = Annotated[CurrentUser, Depends(require_permissions("FILE.UPLOAD_ACTION"))]
ReadPermission = Annotated[CurrentUser, Depends(require_permissions("FILE.READ_ASSIGNED"))]


@router.post(
    "/{dispatch_public_id}/action-files",
    status_code=201,
    response_model=SuccessResponse[ActionFileUploadData],
)
def upload_action_file(
    dispatch_public_id: UUID,
    request: Request,
    current_user: UploadPermission,
    photo_phase: PhotoPhase = Form(...),
    display_order: int = Form(1, ge=1),
    file: UploadFile = File(...),
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_file_storage),
):
    result = action_file.upload(
        db,
        dispatch_public_id=str(dispatch_public_id),
        photo_phase=photo_phase.value,
        display_order=display_order,
        filename=file.filename,
        declared_type=file.content_type,
        content=file.file.read(),
        idempotency_key=str(idempotency_key),
        current_user=current_user,
        trace_id=request.state.trace_id,
        storage=storage,
    )
    return success_response(
        data=result.data, message=result.message, trace_id=request.state.trace_id
    )


@router.get(
    "/{dispatch_public_id}/action-files", response_model=SuccessResponse[ActionFileListData]
)
def list_action_files(
    dispatch_public_id: UUID,
    request: Request,
    current_user: ReadPermission,
    photo_phase: PhotoPhase | None = Query(None),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_file_storage),
):
    data = action_file.list_files(
        db,
        dispatch_public_id=str(dispatch_public_id),
        photo_phase=photo_phase.value if photo_phase else None,
        current_user=current_user,
        storage=storage,
    )
    return success_response(data=data, trace_id=request.state.trace_id)
