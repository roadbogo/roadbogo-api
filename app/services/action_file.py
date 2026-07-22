import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.exceptions import AppException
from app.models.dispatch import DispatchRequest, FieldActionFile, FieldActionReport
from app.models.file import File
from app.models.incident import Incident
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services.incident_command import CommandResult, IDEMPOTENCY_RETENTION_HOURS
from app.services.query_common import utc_z

SCOPE = "FIELD_ACTION_FILE_UPLOAD"
MESSAGE = "현장 조치 사진이 등록되었습니다."
MAX_SIZE = 10 * 1024 * 1024
MIMES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def err(status, code, msg):
    return AppException(status, code, msg)


def validate_file(name, declared, data):
    if not data:
        raise err(422, "FILE_EMPTY", "빈 파일은 업로드할 수 없습니다.")
    if len(data) > MAX_SIZE:
        raise err(413, "FILE_TOO_LARGE", "파일 크기는 10 MiB를 초과할 수 없습니다.")
    safe = (name or "").replace("\\", "/").split("/")[-1].strip()
    if not safe or "." not in safe or safe in {".", ".."}:
        raise err(422, "FILE_NAME_INVALID", "파일 이름이 올바르지 않습니다.")
    ext = safe.rsplit(".", 1)[1].lower()
    actual = None
    if data.startswith(b"\xff\xd8\xff"):
        actual = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        actual = "image/png"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        actual = "image/webp"
    if actual is None or MIMES.get(ext) != actual or declared != actual:
        raise err(422, "FILE_INVALID_TYPE", "지원하지 않는 이미지 형식입니다.")
    return safe, ext, actual


def req_hash(actor, dispatch, phase, order, digest, size, mime):
    return hashlib.sha256(
        json.dumps(
            {
                "scope_code": SCOPE,
                "actor_public_id": actor,
                "dispatch_public_id": dispatch,
                "photo_phase": phase,
                "display_order": order,
                "sha256_hash": digest,
                "size_bytes": size,
                "mime_type": mime,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def existing(db, key):
    return db.scalars(
        select(IdempotencyKey)
        .where(IdempotencyKey.scope_code == SCOPE, IdempotencyKey.idempotency_key == key)
        .with_for_update()
    ).first()


def replay(rec, h):
    snap = rec.response_snapshot_json
    if rec.request_hash != h or rec.processing_status != "COMPLETED":
        raise err(409, "FILE_IDEMPOTENCY_CONFLICT", "멱등 요청을 재사용할 수 없습니다.")
    data = snap.get("data") if isinstance(snap, dict) else None
    msg = snap.get("message") if isinstance(snap, dict) else None
    if not isinstance(data, dict) or not isinstance(msg, str) or not msg.strip():
        raise err(409, "FILE_IDEMPOTENCY_CONFLICT", "처리 결과를 재사용할 수 없습니다.")
    return CommandResult(data, msg)


def upload(
    db,
    *,
    dispatch_public_id,
    photo_phase,
    display_order,
    filename,
    declared_type,
    content,
    idempotency_key,
    current_user,
    trace_id,
    storage,
):
    name, ext, mime = validate_file(filename, declared_type, content)
    digest = hashlib.sha256(content).hexdigest()
    now = datetime.now(UTC).replace(tzinfo=None)
    actor = current_user.user
    h = req_hash(
        actor.public_id, dispatch_public_id, photo_phase, display_order, digest, len(content), mime
    )
    uploaded = None
    try:
        rec = existing(db, idempotency_key)
        if rec:
            return replay(rec, h)
        idem = IdempotencyKey(
            scope_code=SCOPE,
            idempotency_key=idempotency_key,
            request_hash=h,
            processing_status="PROCESSING",
            expires_at=now + timedelta(hours=IDEMPOTENCY_RETENTION_HOURS),
        )
        db.add(idem)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            rec = existing(db, idempotency_key)
            if rec is None:
                raise
            return replay(rec, h)
        dispatch = db.scalars(
            select(DispatchRequest)
            .where(
                DispatchRequest.public_id == dispatch_public_id,
                DispatchRequest.responder_user_id == actor.user_id,
            )
            .with_for_update()
        ).first()
        if (
            dispatch is None
            or dispatch.public_id != dispatch_public_id
            or dispatch.responder_user_id != actor.user_id
        ):
            raise err(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
        incident = db.scalars(
            select(Incident).where(Incident.incident_id == dispatch.incident_id).with_for_update()
        ).first()
        report = db.scalars(
            select(FieldActionReport)
            .where(FieldActionReport.dispatch_request_id == dispatch.dispatch_request_id)
            .with_for_update()
        ).first()
        if dispatch.dispatch_status != "ACTION_COMPLETED":
            raise err(
                409,
                "DISPATCH_INVALID_STATE_TRANSITION",
                "완료된 출동에만 사진을 등록할 수 있습니다.",
            )
        if report is None:
            raise err(409, "DISPATCH_ACTION_REPORT_REQUIRED", "현장 조치 보고서가 필요합니다.")
        if incident is not None and incident.incident_status == "CLOSED":
            raise err(
                409, "FIELD_ACTION_FILE_UPLOAD_CLOSED", "종료된 사건에는 사진을 등록할 수 없습니다."
            )
        public_id = str(uuid4())
        uploaded = f"field-actions/{report.public_id}/{public_id}.{ext}"
        storage.put_object(uploaded, content, mime)
        file = File(
            public_id=public_id,
            storage_provider="MINIO",
            bucket_name=storage.bucket,
            object_key=uploaded,
            original_file_name=name,
            file_extension=ext,
            mime_type=mime,
            size_bytes=len(content),
            sha256_hash=digest,
            file_status="ACTIVE",
            access_level="RESTRICTED",
            created_by_user_id=actor.user_id,
            created_at=now,
        )
        db.add(file)
        db.flush()
        db.add(
            FieldActionFile(
                field_action_report_id=report.field_action_report_id,
                file_id=file.file_id,
                photo_phase=photo_phase,
                display_order=display_order,
                created_at=now,
            )
        )
        public = {
            "file_public_id": public_id,
            "dispatch_public_id": dispatch.public_id,
            "report_public_id": report.public_id,
            "photo_phase": photo_phase,
            "display_order": display_order,
            "mime_type": mime,
            "size_bytes": len(content),
        }
        db.add(
            AuditLog(
                public_id=str(uuid4()),
                actor_type="USER",
                actor_user_id=actor.user_id,
                action_code="FILE.UPLOAD_ACTION",
                resource_type="FIELD_ACTION_FILE",
                resource_public_id=public_id,
                result_status="SUCCESS",
                before_json=None,
                after_json=public,
                trace_id=trace_id,
            )
        )
        event = str(uuid4())
        payload = {
            "event_id": event,
            "event_type": "FIELD_ACTION.FILE_ADDED",
            "occurred_at": utc_z(now),
            "resource": {"resource_type": "FIELD_ACTION_FILE", "resource_public_id": public_id},
            "version_no": 1,
            "data": {
                "file_public_id": public_id,
                "dispatch_public_id": dispatch.public_id,
                "incident_public_id": incident.public_id,
                "report_public_id": report.public_id,
                "photo_phase": photo_phase,
                "display_order": display_order,
                "uploaded_by": {"public_id": actor.public_id, "user_name": actor.user_name},
                "uploaded_at": utc_z(now),
            },
            "notification": None,
            "trace_id": trace_id,
        }
        db.add(
            EventOutbox(
                event_uuid=event,
                aggregate_type="FIELD_ACTION_FILE",
                aggregate_public_id=public_id,
                event_type="FIELD_ACTION.FILE_ADDED",
                payload_json=payload,
                publish_status="PENDING",
                retry_count=0,
                next_attempt_at=now,
            )
        )
        item = {
            "public_id": public_id,
            "original_file_name": name,
            "mime_type": mime,
            "size_bytes": len(content),
            "photo_phase": photo_phase,
            "display_order": display_order,
            "download_url": storage.presigned_get_url(uploaded),
            "created_at": utc_z(now),
        }
        data = {"file": item}
        idem.processing_status = "COMPLETED"
        idem.resource_type = "FIELD_ACTION_FILE"
        idem.resource_public_id = public_id
        idem.response_code = 201
        idem.response_snapshot_json = {"data": data, "message": MESSAGE}
        db.flush()
        db.commit()
        return CommandResult(data, MESSAGE)
    except Exception:
        db.rollback()
        if uploaded:
            try:
                storage.remove_object(uploaded)
            except Exception:
                pass
        raise


def list_files(db, *, dispatch_public_id, photo_phase, current_user, storage):
    dispatch = db.scalars(
        select(DispatchRequest).where(DispatchRequest.public_id == dispatch_public_id)
    ).first()
    if dispatch is None:
        raise err(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
    incident = db.scalars(
        select(Incident).where(Incident.incident_id == dispatch.incident_id)
    ).first()
    roles = set(current_user.summary.roles)
    if not (
        dispatch.responder_user_id == current_user.user.user_id
        or (incident and incident.current_controller_user_id == current_user.user.user_id)
        or roles & {"CONTROL_MANAGER", "SYSTEM_ADMIN"}
    ):
        raise err(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
    stmt = (
        select(FieldActionFile, File)
        .join(File, File.file_id == FieldActionFile.file_id)
        .join(
            FieldActionReport,
            FieldActionReport.field_action_report_id == FieldActionFile.field_action_report_id,
        )
        .where(
            FieldActionReport.dispatch_request_id == dispatch.dispatch_request_id,
            File.file_status == "ACTIVE",
        )
    )
    if photo_phase:
        stmt = stmt.where(FieldActionFile.photo_phase == photo_phase)
    rows = db.execute(
        stmt.order_by(
            FieldActionFile.photo_phase,
            FieldActionFile.display_order,
            FieldActionFile.created_at,
            File.public_id,
        )
    ).all()
    return {
        "items": [
            {
                "public_id": f.public_id,
                "original_file_name": f.original_file_name,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "photo_phase": link.photo_phase,
                "display_order": link.display_order,
                "download_url": storage.presigned_get_url(f.object_key),
                "created_at": utc_z(link.created_at),
            }
            for link, f in rows
        ]
    }
