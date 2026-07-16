from typing import TYPE_CHECKING, Optional
import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    VARBINARY,
    text,
)
from sqlalchemy.dialects.mysql import (
    BIGINT,
    CHAR,
    DATETIME,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.dispatch import DispatchRequest, DispatchStatusHistory, FieldActionReport
    from app.models.file import File
    from app.models.incident import (
        Incident,
        IncidentClaim,
        IncidentDecision,
        IncidentFile,
        IncidentNote,
        IncidentStatusHistory,
    )
    from app.models.notification import AuditLog, NotificationRecipient

__all__ = [
    "Organization",
    "Permission",
    "ResponderProfile",
    "Role",
    "RolePermission",
    "User",
    "UserRole",
    "UserSession",
]


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "`organization_type` in ('SYSTEM','CONTROL_CENTER','DISPATCH_TEAM','AI_TEAM','OTHER')",
            name="ck_organizations_type",
        ),
        ForeignKeyConstraint(
            ["parent_organization_id"],
            ["organizations.organization_id"],
            name="fk_organizations_parent",
        ),
        Index("fk_organizations_parent", "parent_organization_id"),
        Index("uk_organizations_code", "organization_code", unique=True),
        Index("uk_organizations_public_id", "public_id", unique=True),
    )

    organization_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    organization_code: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    organization_name: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    organization_type: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    parent_organization_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    parent_organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", remote_side=[organization_id], back_populates="parent_organization_reverse"
    )
    parent_organization_reverse: Mapped[list["Organization"]] = relationship(
        "Organization", remote_side=[parent_organization_id], back_populates="parent_organization"
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            "`scope_type` in ('GLOBAL','ORGANIZATION','ASSIGNED','OWN')",
            name="ck_permissions_scope",
        ),
        Index("uk_permissions_code", "permission_code", unique=True),
    )

    permission_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    permission_code: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    permission_name: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    resource_code: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    action_code: Mapped[str] = mapped_column(VARCHAR(40), nullable=False)
    scope_type: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'GLOBAL'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    description: Mapped[Optional[str]] = mapped_column(VARCHAR(500))

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission"
    )


class ResponderProfile(Base):
    __tablename__ = "responder_profiles"
    __table_args__ = (
        CheckConstraint(
            "`duty_status` in ('AVAILABLE','BUSY','OFF_DUTY','UNAVAILABLE')",
            name="ck_responder_profiles_status",
        ),
        ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_responder_profiles_user"),
        Index("uk_responder_profiles_code", "responder_code", unique=True),
        Index("uk_responder_profiles_user", "user_id", unique=True),
    )

    responder_profile_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    responder_code: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    duty_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'OFF_DUTY'")
    )
    is_dispatch_enabled: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    coverage_area: Mapped[Optional[str]] = mapped_column(VARCHAR(255))

    user: Mapped["User"] = relationship("User", back_populates="responder_profiles")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (Index("uk_roles_code", "role_code", unique=True),)

    role_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    role_code: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    role_name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    is_system_role: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("1")
    )
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    description: Mapped[Optional[str]] = mapped_column(VARCHAR(500))

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role"
    )
    user_roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="role")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_role_permissions_granted_by",
        ),
        ForeignKeyConstraint(
            ["permission_id"], ["permissions.permission_id"], name="fk_role_permissions_permission"
        ),
        ForeignKeyConstraint(["role_id"], ["roles.role_id"], name="fk_role_permissions_role"),
        Index("fk_role_permissions_granted_by", "granted_by_user_id"),
        Index("fk_role_permissions_permission", "permission_id"),
        Index("uk_role_permissions", "role_id", "permission_id", unique=True),
    )

    role_permission_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    role_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    permission_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    granted_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    granted_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    granted_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="role_permissions"
    )
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")
    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "`account_status` in ('ACTIVE','INACTIVE','LOCKED')", name="ck_users_account_status"
        ),
        ForeignKeyConstraint(
            ["deactivated_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_users_deactivated_by",
        ),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            ondelete="SET NULL",
            name="fk_users_organization",
        ),
        Index("fk_users_deactivated_by", "deactivated_by_user_id"),
        Index("fk_users_organization", "organization_id"),
        Index("ix_users_status_org", "account_status", "organization_id"),
        Index("uk_users_email", "email", unique=True),
        Index("uk_users_public_id", "public_id", unique=True),
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    email: Mapped[str] = mapped_column(VARCHAR(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    user_name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    account_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'ACTIVE'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    organization_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    phone_encrypted: Mapped[Optional[bytes]] = mapped_column(VARBINARY(512))
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    deactivated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    deactivated_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))

    deactivated_by_user: Mapped[Optional["User"]] = relationship(
        "User", remote_side=[user_id], back_populates="deactivated_by_user_reverse"
    )
    deactivated_by_user_reverse: Mapped[list["User"]] = relationship(
        "User", remote_side=[deactivated_by_user_id], back_populates="deactivated_by_user"
    )
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", back_populates="users"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor_user")
    files_created_by_users: Mapped[list["File"]] = relationship(
        "File", foreign_keys="[File.created_by_user_id]", back_populates="created_by_user"
    )
    files_deleted_by_users: Mapped[list["File"]] = relationship(
        "File", foreign_keys="[File.deleted_by_user_id]", back_populates="deleted_by_user"
    )
    notification_recipients: Mapped[list["NotificationRecipient"]] = relationship(
        "NotificationRecipient", back_populates="user"
    )
    responder_profiles: Mapped[list["ResponderProfile"]] = relationship(
        "ResponderProfile", back_populates="user"
    )
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="granted_by_user"
    )
    user_roles_assigned_by_users: Mapped[list["UserRole"]] = relationship(
        "UserRole", foreign_keys="[UserRole.assigned_by_user_id]", back_populates="assigned_by_user"
    )
    user_roles_users: Mapped[list["UserRole"]] = relationship(
        "UserRole", foreign_keys="[UserRole.user_id]", back_populates="user"
    )
    user_sessions: Mapped[list["UserSession"]] = relationship("UserSession", back_populates="user")
    incidents_acknowledged_by_users: Mapped[list["Incident"]] = relationship(
        "Incident",
        foreign_keys="[Incident.acknowledged_by_user_id]",
        back_populates="acknowledged_by_user",
    )
    incidents_current_controller_users: Mapped[list["Incident"]] = relationship(
        "Incident",
        foreign_keys="[Incident.current_controller_user_id]",
        back_populates="current_controller_user",
    )
    dispatch_requests_assigned_by_users: Mapped[list["DispatchRequest"]] = relationship(
        "DispatchRequest",
        foreign_keys="[DispatchRequest.assigned_by_user_id]",
        back_populates="assigned_by_user",
    )
    dispatch_requests_responder_users: Mapped[list["DispatchRequest"]] = relationship(
        "DispatchRequest",
        foreign_keys="[DispatchRequest.responder_user_id]",
        back_populates="responder_user",
    )
    incident_claims: Mapped[list["IncidentClaim"]] = relationship(
        "IncidentClaim", back_populates="controller_user"
    )
    incident_decisions: Mapped[list["IncidentDecision"]] = relationship(
        "IncidentDecision", back_populates="decided_by_user"
    )
    incident_files: Mapped[list["IncidentFile"]] = relationship(
        "IncidentFile", back_populates="uploaded_by_user"
    )
    incident_notes_created_by_users: Mapped[list["IncidentNote"]] = relationship(
        "IncidentNote",
        foreign_keys="[IncidentNote.created_by_user_id]",
        back_populates="created_by_user",
    )
    incident_notes_deleted_by_users: Mapped[list["IncidentNote"]] = relationship(
        "IncidentNote",
        foreign_keys="[IncidentNote.deleted_by_user_id]",
        back_populates="deleted_by_user",
    )
    incident_status_histories: Mapped[list["IncidentStatusHistory"]] = relationship(
        "IncidentStatusHistory", back_populates="actor_user"
    )
    dispatch_status_histories: Mapped[list["DispatchStatusHistory"]] = relationship(
        "DispatchStatusHistory", back_populates="actor_user"
    )
    field_action_reports: Mapped[list["FieldActionReport"]] = relationship(
        "FieldActionReport", back_populates="created_by_user"
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_user_roles_assigned_by",
        ),
        ForeignKeyConstraint(["role_id"], ["roles.role_id"], name="fk_user_roles_role"),
        ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_user_roles_user"),
        Index("fk_user_roles_assigned_by", "assigned_by_user_id"),
        Index("fk_user_roles_role", "role_id"),
        Index("uk_user_roles", "user_id", "role_id", unique=True),
    )

    user_role_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    role_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    assigned_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    assigned_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    assigned_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_by_user_id], back_populates="user_roles_assigned_by_users"
    )
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="user_roles_users"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint(
            "`client_type` in ('WEB','WEBAPP','MOBILE','DEVICE')",
            name="ck_user_sessions_client_type",
        ),
        CheckConstraint("`expires_at` > `created_at`", name="ck_user_sessions_expiry"),
        ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="CASCADE", name="fk_user_sessions_user"
        ),
        Index("ix_user_sessions_user_expiry", "user_id", "expires_at", "revoked_at"),
        Index("uk_user_sessions_public_id", "public_id", unique=True),
        Index("uk_user_sessions_token_hash", "refresh_token_hash", unique=True),
    )

    user_session_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    client_type: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'WEB'")
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    ip_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    user_agent_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    revoked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    revoke_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(300))

    user: Mapped["User"] = relationship("User", back_populates="user_sessions")
