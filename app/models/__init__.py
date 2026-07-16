from app.models.ai import (
    AiModel,
    AiModelVersion,
    Detection,
    InferenceRun,
    ModelVersionClass,
    ObjectClass,
)
from app.models.auth import (
    Organization,
    Permission,
    ResponderProfile,
    Role,
    RolePermission,
    User,
    UserRole,
    UserSession,
)
from app.models.dispatch import (
    DispatchRequest,
    DispatchStateTransition,
    DispatchStatusHistory,
    FieldActionFile,
    FieldActionReport,
)
from app.models.file import File, VideoFrame
from app.models.incident import (
    Incident,
    IncidentClaim,
    IncidentDecision,
    IncidentEvidence,
    IncidentFile,
    IncidentNote,
    IncidentStateTransition,
    IncidentStatusHistory,
)
from app.models.infrastructure import Cctv, CctvStream, ItsSyncRun
from app.models.notification import (
    AuditLog,
    EventOutbox,
    IdempotencyKey,
    Notification,
    NotificationRecipient,
)
from app.models.road import BusinessSequence, Road, RoadSection
from app.models.tracking import (
    RiskEvaluation,
    TrackedObject,
    TrackingSession,
    TrackObservation,
)
from app.core.database import Base
from app.models.metadata import normalize_mariadb_metadata

normalize_mariadb_metadata(Base.metadata)

__all__ = [
    "AiModel",
    "AiModelVersion",
    "AuditLog",
    "BusinessSequence",
    "Cctv",
    "CctvStream",
    "Detection",
    "DispatchRequest",
    "DispatchStateTransition",
    "DispatchStatusHistory",
    "EventOutbox",
    "FieldActionFile",
    "FieldActionReport",
    "File",
    "IdempotencyKey",
    "Incident",
    "IncidentClaim",
    "IncidentDecision",
    "IncidentEvidence",
    "IncidentFile",
    "IncidentNote",
    "IncidentStateTransition",
    "IncidentStatusHistory",
    "InferenceRun",
    "ItsSyncRun",
    "ModelVersionClass",
    "Notification",
    "NotificationRecipient",
    "ObjectClass",
    "Organization",
    "Permission",
    "ResponderProfile",
    "RiskEvaluation",
    "Road",
    "RoadSection",
    "Role",
    "RolePermission",
    "TrackedObject",
    "TrackingSession",
    "TrackObservation",
    "User",
    "UserRole",
    "UserSession",
    "VideoFrame",
]
