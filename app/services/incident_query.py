from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import AppException
from app.models.ai import Detection, InferenceRun
from app.models.dispatch import DispatchRequest
from app.models.file import VideoFrame
from app.models.incident import (
    Incident,
    IncidentDecision,
    IncidentEvidence,
    IncidentStatusHistory,
)
from app.models.road import RoadSection
from app.models.tracking import RiskEvaluation
from app.services.query_common import file_url, number, pagination, utc_z

RISK_GRADES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
OBJECT_CATEGORIES = ("VEHICLE", "DEBRIS", "WILDLIFE", "OTHER")


def _not_found() -> AppException:
    return AppException(404, "INCIDENT_NOT_FOUND", "사건 정보를 찾을 수 없습니다.")


def _reason_codes(risk: object | None) -> list:
    if risk is None or not isinstance(risk.rule_snapshot_json, dict):
        return []
    value = risk.rule_snapshot_json.get("reason_codes", [])
    return value if isinstance(value, list) else []


def _confidence(incident: Incident):
    if incident.latest_risk_evaluation is not None:
        return number(incident.latest_risk_evaluation.confidence_value)
    if incident.representative_detection is not None:
        return number(incident.representative_detection.confidence)
    return None


def _incident_conditions(filters: dict) -> list:
    conditions = []
    mapping = {
        "status": Incident.incident_status,
        "risk_grade": Incident.current_risk_grade,
        "object_category": Incident.object_category,
    }
    for key, column in mapping.items():
        if filters.get(key):
            conditions.append(column == filters[key])
    if filters.get("keyword"):
        term = filters["keyword"]
        conditions.append(or_(Incident.incident_no.contains(term), Incident.cctv_name_snapshot.contains(term)))
    if filters.get("class_code"):
        conditions.append(Incident.object_clas.has(class_code=filters["class_code"]))
    if filters.get("cctv_public_id"):
        conditions.append(Incident.cctv.has(public_id=str(filters["cctv_public_id"])))
    if filters.get("road_section_public_id"):
        conditions.append(
            Incident.road_section.has(public_id=str(filters["road_section_public_id"]))
        )
    if filters.get("road_public_id"):
        conditions.append(
            Incident.road_section.has(RoadSection.road.has(public_id=str(filters["road_public_id"])))
        )
    if filters.get("controller_public_id"):
        conditions.append(
            Incident.current_controller_user.has(public_id=str(filters["controller_public_id"]))
        )
    if filters.get("mine_only"):
        conditions.append(Incident.current_controller_user_id == filters["current_user_id"])
    if filters.get("unclaimed_only"):
        conditions.append(Incident.current_controller_user_id.is_(None))
    if filters.get("from_dt"):
        conditions.append(Incident.first_detected_at >= filters["from_dt"])
    if filters.get("to_dt"):
        conditions.append(Incident.first_detected_at <= filters["to_dt"])
    return conditions


def summary(db: Session, *, from_dt=None, to_dt=None, road_public_id=None) -> dict:
    conditions = []
    if from_dt:
        conditions.append(Incident.first_detected_at >= from_dt)
    if to_dt:
        conditions.append(Incident.first_detected_at <= to_dt)
    if road_public_id:
        conditions.append(
            Incident.road_section.has(RoadSection.road.has(public_id=str(road_public_id)))
        )
    rows = db.execute(
        select(
            Incident.incident_status,
            Incident.current_risk_grade,
            Incident.object_category,
            func.count(),
        )
        .where(*conditions)
        .group_by(
            Incident.incident_status, Incident.current_risk_grade, Incident.object_category
        )
    ).all()
    status_counts: dict[str, int] = {}
    grades = dict.fromkeys(RISK_GRADES, 0)
    categories = dict.fromkeys(OBJECT_CATEGORIES, 0)
    total = 0
    for status, grade, category, count in rows:
        total += count
        status_counts[status] = status_counts.get(status, 0) + count
        grades[grade] = grades.get(grade, 0) + count
        categories[category] = categories.get(category, 0) + count
    return {
        "total_count": total,
        "new_count": status_counts.get("NEW", 0),
        "acknowledged_count": status_counts.get("ACKNOWLEDGED", 0),
        "claimed_count": status_counts.get("CLAIMED", 0),
        "under_review_count": status_counts.get("UNDER_REVIEW", 0),
        "dispatch_requested_count": status_counts.get("DISPATCH_REQUESTED", 0),
        "dispatch_in_progress_count": sum(
            status_counts.get(value, 0)
            for value in ("DISPATCHED", "ON_SCENE", "ACTION_IN_PROGRESS")
        ),
        "action_completed_count": status_counts.get("ACTION_COMPLETED", 0),
        "closed_count": status_counts.get("CLOSED", 0),
        "false_positive_count": status_counts.get("FALSE_POSITIVE", 0),
        "risk_grade_counts": grades,
        "object_category_counts": categories,
        "generated_at": utc_z(datetime.now(UTC)),
    }


def list_incidents(db: Session, *, page: int, size: int, filters: dict, sort: str) -> dict:
    conditions = _incident_conditions(filters)
    total = db.scalar(select(func.count()).select_from(Incident).where(*conditions)) or 0
    sort_map = {
        "priority,desc": (Incident.priority_order.asc(), Incident.detected_at.desc()),
        "first_detected_at,desc": (Incident.first_detected_at.desc(),),
        "last_detected_at,desc": (Incident.last_detected_at.desc(),),
        "risk_score,desc": (Incident.current_risk_score.desc(),),
        "status,asc": (Incident.incident_status.asc(),),
    }
    stmt = (
        select(Incident)
        .where(*conditions)
        .options(
            joinedload(Incident.object_clas),
            joinedload(Incident.current_controller_user),
            joinedload(Incident.cctv),
            joinedload(Incident.road_section),
            joinedload(Incident.latest_risk_evaluation),
            joinedload(Incident.representative_detection)
            .joinedload(Detection.inference_run)
            .joinedload(InferenceRun.video_frame)
            .joinedload(VideoFrame.original_file),
        )
        .order_by(*sort_map[sort], Incident.incident_id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = []
    for incident in db.scalars(stmt).unique():
        detection = incident.representative_detection
        original_file = (
            detection.inference_run.video_frame.original_file if detection is not None else None
        )
        items.append(
            {
                "public_id": incident.public_id,
                "incident_no": incident.incident_no,
                "status": incident.incident_status,
                "object_category": incident.object_category,
                "class_code": incident.object_clas.class_code if incident.object_clas else None,
                "class_name": incident.object_clas.class_name if incident.object_clas else None,
                "ai_risk_score": number(incident.current_risk_score),
                "ai_risk_grade": incident.current_risk_grade,
                "representative_confidence": _confidence(incident),
                "detection_count": incident.detection_count,
                "duration_ms": incident.duration_ms,
                "first_detected_at": utc_z(incident.first_detected_at),
                "last_detected_at": utc_z(incident.last_detected_at),
                "acknowledged_at": utc_z(incident.acknowledged_at),
                "claimed_by": (
                    {
                        "public_id": incident.current_controller_user.public_id,
                        "user_name": incident.current_controller_user.user_name,
                    }
                    if incident.current_controller_user
                    else None
                ),
                "cctv": {
                    "public_id": incident.cctv.public_id,
                    "cctv_name": incident.cctv_name_snapshot,
                    "direction_code": incident.direction_snapshot,
                },
                "location": {
                    "road_name": incident.road_name_snapshot,
                    "road_section_name": incident.road_section_name_snapshot,
                    "latitude": number(incident.latitude_snapshot),
                    "longitude": number(incident.longitude_snapshot),
                },
                "representative_image_url": file_url(original_file),
                "version_no": incident.version_no,
                "updated_at": utc_z(incident.updated_at),
            }
        )
    return {"items": items, "pagination": pagination(page, size, total)}


def _base_incident(db: Session, public_id: str) -> Incident:
    incident = db.scalars(
        select(Incident)
        .where(Incident.public_id == public_id)
        .options(
            joinedload(Incident.object_clas),
            joinedload(Incident.current_controller_user),
            joinedload(Incident.cctv),
            joinedload(Incident.latest_risk_evaluation),
            joinedload(Incident.tracked_object),
            joinedload(Incident.representative_detection)
            .joinedload(Detection.inference_run)
            .joinedload(InferenceRun.video_frame)
            .joinedload(VideoFrame.original_file),
            joinedload(Incident.representative_detection)
            .joinedload(Detection.inference_run)
            .joinedload(InferenceRun.annotated_file),
            selectinload(Incident.incident_decisions).joinedload(
                IncidentDecision.decided_by_user
            ),
            selectinload(Incident.dispatch_requests).joinedload(
                DispatchRequest.responder_user
            ),
            selectinload(Incident.incident_status_histories),
            selectinload(Incident.incident_evidences),
            selectinload(Incident.incident_notes),
        )
    ).unique().first()
    if incident is None:
        raise _not_found()
    return incident


def get_incident(db: Session, public_id: str) -> dict:
    incident = _base_incident(db, public_id)
    risk = incident.latest_risk_evaluation
    detection = incident.representative_detection
    review_times = [
        history.changed_at
        for history in incident.incident_status_histories
        if history.to_status == "UNDER_REVIEW"
    ]
    decision = next(
        (item for item in incident.incident_decisions if item.superseded_at is None), None
    )
    active_dispatches = [
        item
        for item in incident.dispatch_requests
        if item.dispatch_status not in ("REJECTED", "CANCELLED", "ACTION_COMPLETED")
    ]
    dispatch = max(active_dispatches, key=lambda item: item.requested_at, default=None)
    original_file = detection.inference_run.video_frame.original_file if detection else None
    annotated_file = detection.inference_run.annotated_file if detection else None
    evidence = None
    if detection:
        evidence = {
            "detection_public_id": detection.public_id,
            "original_image_url": file_url(original_file),
            "annotated_image_url": file_url(annotated_file),
            "bbox": {
                "x": number(detection.bbox_x),
                "y": number(detection.bbox_y),
                "width": number(detection.bbox_width),
                "height": number(detection.bbox_height),
            },
        }
    return {
        "public_id": incident.public_id,
        "incident_no": incident.incident_no,
        "status": incident.incident_status,
        "version_no": incident.version_no,
        "object": {
            "object_category": incident.object_category,
            "class_code": incident.object_clas.class_code if incident.object_clas else None,
            "class_name": incident.object_clas.class_name if incident.object_clas else None,
            "tracked_object_public_id": incident.tracked_object.public_id if incident.tracked_object else None,
            "external_track_id": incident.tracked_object.external_track_id if incident.tracked_object else None,
        },
        "ai_analysis": {
            "representative_confidence": _confidence(incident),
            "confidence_calculation_type": risk.confidence_calculation_type if risk else None,
            "risk_score": number(incident.current_risk_score),
            "risk_grade": incident.current_risk_grade,
            "duration_ms": incident.duration_ms,
            "repeat_count": risk.repeat_count if risk else None,
            "rule_code": risk.rule_code if risk else None,
            "rule_version": risk.rule_version_snapshot if risk else None,
            "reason_codes": _reason_codes(risk),
        },
        "cctv_snapshot": {
            "cctv_public_id": incident.cctv.public_id,
            "cctv_name": incident.cctv_name_snapshot,
            "direction_code": incident.direction_snapshot,
            "road_name": incident.road_name_snapshot,
            "road_section_name": incident.road_section_name_snapshot,
            "latitude": number(incident.latitude_snapshot),
            "longitude": number(incident.longitude_snapshot),
            "km_post": number(incident.cctv.km_post),
        },
        "timeline": {
            "first_detected_at": utc_z(incident.first_detected_at),
            "last_detected_at": utc_z(incident.last_detected_at),
            "created_at": utc_z(incident.created_at),
            "updated_at": utc_z(incident.updated_at),
            "acknowledged_at": utc_z(incident.acknowledged_at),
            "claimed_at": utc_z(incident.claimed_at),
            "review_started_at": utc_z(max(review_times)) if review_times else None,
            "closed_at": utc_z(incident.closed_at),
        },
        "controller": (
            {"public_id": incident.current_controller_user.public_id, "user_name": incident.current_controller_user.user_name}
            if incident.current_controller_user else None
        ),
        "decision": (
            {
                "public_id": decision.public_id,
                "decision_type": decision.decision_type,
                "decision_reason": decision.decision_reason,
                "decided_by": {"public_id": decision.decided_by_user.public_id, "user_name": decision.decided_by_user.user_name},
                "decided_at": utc_z(decision.decided_at),
            }
            if decision else None
        ),
        "active_dispatch": (
            {
                "public_id": dispatch.public_id,
                "status": dispatch.dispatch_status,
                "responder": {"public_id": dispatch.responder_user.public_id, "user_name": dispatch.responder_user.user_name},
                "requested_at": utc_z(dispatch.requested_at),
                "updated_at": utc_z(dispatch.updated_at),
            }
            if dispatch else None
        ),
        "representative_evidence": evidence,
        "evidence_count": len(incident.incident_evidences),
        "memo_count": sum(note.deleted_at is None for note in incident.incident_notes),
    }


def evidences(db: Session, public_id: str, *, page: int, size: int, representative_only: bool, sort: str) -> dict:
    incident_id = db.scalar(select(Incident.incident_id).where(Incident.public_id == public_id))
    if incident_id is None:
        raise _not_found()
    conditions = [IncidentEvidence.incident_id == incident_id]
    if representative_only:
        conditions.append(IncidentEvidence.is_primary == 1)
    total = db.scalar(select(func.count()).select_from(IncidentEvidence).where(*conditions)) or 0
    detected_at = func.coalesce(Detection.detected_at, IncidentEvidence.added_at)
    ordering = detected_at.asc() if sort.endswith("asc") else detected_at.desc()
    rows = db.scalars(
        select(IncidentEvidence)
        .outerjoin(IncidentEvidence.detection)
        .where(*conditions)
        .options(
            joinedload(IncidentEvidence.detection).joinedload(Detection.object_clas),
            joinedload(IncidentEvidence.detection).joinedload(Detection.inference_run).joinedload(InferenceRun.annotated_file),
            joinedload(IncidentEvidence.detection)
            .joinedload(Detection.inference_run)
            .joinedload(InferenceRun.video_frame)
            .joinedload(VideoFrame.original_file),
            joinedload(IncidentEvidence.video_frame).joinedload(VideoFrame.original_file),
            joinedload(IncidentEvidence.risk_evaluation).joinedload(
                RiskEvaluation.tracked_object
            ),
        )
        .order_by(ordering, IncidentEvidence.incident_evidence_id.asc())
        .offset((page - 1) * size).limit(size)
    ).unique()
    items = []
    for row in rows:
        detection = row.detection
        risk = row.risk_evaluation
        frame = row.video_frame or (detection.inference_run.video_frame if detection else None)
        original = frame.original_file if frame else None
        annotated = detection.inference_run.annotated_file if detection else None
        items.append({
            "detection_public_id": detection.public_id if detection else None,
            "evidence_type": row.evidence_type,
            "is_representative": bool(row.is_primary),
            "detected_at": utc_z(detection.detected_at if detection else row.added_at),
            "class_code": detection.object_clas.class_code if detection else None,
            "class_name": detection.object_clas.class_name if detection else None,
            "confidence": number(detection.confidence) if detection else None,
            "bbox": ({"x": number(detection.bbox_x), "y": number(detection.bbox_y), "width": number(detection.bbox_width), "height": number(detection.bbox_height)} if detection else None),
            "original_image_url": file_url(original),
            "annotated_image_url": file_url(annotated),
            "risk": ({"risk_score": number(risk.risk_score), "risk_grade": risk.risk_grade, "duration_ms": risk.duration_ms, "repeat_count": risk.repeat_count, "tracked_object_public_id": risk.tracked_object.public_id, "external_track_id": risk.tracked_object.external_track_id, "reason_codes": _reason_codes(risk)} if risk else None),
        })
    return {"items": items, "pagination": pagination(page, size, total)}


def histories(db: Session, public_id: str, *, page: int, size: int, sort: str) -> dict:
    incident_id = db.scalar(select(Incident.incident_id).where(Incident.public_id == public_id))
    if incident_id is None:
        raise _not_found()
    total = db.scalar(select(func.count()).select_from(IncidentStatusHistory).where(IncidentStatusHistory.incident_id == incident_id)) or 0
    ordering = IncidentStatusHistory.changed_at.asc() if sort.endswith("asc") else IncidentStatusHistory.changed_at.desc()
    rows = db.scalars(
        select(IncidentStatusHistory)
        .where(IncidentStatusHistory.incident_id == incident_id)
        .options(joinedload(IncidentStatusHistory.actor_user))
        .order_by(ordering, IncidentStatusHistory.incident_status_history_id.asc())
        .offset((page - 1) * size).limit(size)
    )
    items = [{
        "public_id": row.public_id,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "actor_type": row.actor_type,
        "actor": ({"public_id": row.actor_user.public_id, "user_name": row.actor_user.user_name} if row.actor_user else None),
        "change_source": row.change_source,
        "reason_code": row.reason_code,
        "reason_text": row.reason_text,
        "changed_at": utc_z(row.changed_at),
    } for row in rows]
    return {"items": items, "pagination": pagination(page, size, total)}
