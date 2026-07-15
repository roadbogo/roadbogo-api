-- ============================================================
-- 도로보GO 1차(MVP) 스키마
-- 범위: 인증/RBAC, CCTV/ITS, 프레임, AI 추론/탐지, 추적,
--       위험 후보, 사건/관제, 웹 기반 수동 출동, 파일, 알림,
--       감사로그, Outbox, 멱등성
-- 제외: ROI, RPI/GPS, 시민 신고, 사용자 PT 모델, 챗봇,
--       자동 Failover
-- ============================================================
USE roadbogo;
SET time_zone = '+00:00';

CREATE TABLE organizations (
    organization_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    organization_code VARCHAR(50) NOT NULL,
    organization_name VARCHAR(120) NOT NULL,
    organization_type VARCHAR(30) NOT NULL,
    parent_organization_id BIGINT UNSIGNED NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_organizations_public_id UNIQUE (public_id),
    CONSTRAINT uk_organizations_code UNIQUE (organization_code),
    CONSTRAINT ck_organizations_type CHECK (organization_type IN ('SYSTEM','CONTROL_CENTER','DISPATCH_TEAM','AI_TEAM','OTHER')),
    CONSTRAINT fk_organizations_parent FOREIGN KEY (parent_organization_id)
        REFERENCES organizations (organization_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE users (
    user_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    organization_id BIGINT UNSIGNED NULL,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    user_name VARCHAR(100) NOT NULL,
    phone_encrypted VARBINARY(512) NULL,
    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    last_login_at DATETIME(3) NULL,
    deactivated_at DATETIME(3) NULL,
    deactivated_by_user_id BIGINT UNSIGNED NULL,
    deleted_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_users_public_id UNIQUE (public_id),
    CONSTRAINT uk_users_email UNIQUE (email),
    CONSTRAINT ck_users_account_status CHECK (account_status IN ('ACTIVE','INACTIVE','LOCKED')),
    CONSTRAINT fk_users_organization FOREIGN KEY (organization_id)
        REFERENCES organizations (organization_id) ON DELETE SET NULL,
    CONSTRAINT fk_users_deactivated_by FOREIGN KEY (deactivated_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE roles (
    role_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    role_code VARCHAR(50) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NULL,
    is_system_role BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_roles_code UNIQUE (role_code)
) ENGINE=InnoDB;

CREATE TABLE permissions (
    permission_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    permission_code VARCHAR(100) NOT NULL,
    permission_name VARCHAR(120) NOT NULL,
    resource_code VARCHAR(60) NOT NULL,
    action_code VARCHAR(40) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'GLOBAL',
    description VARCHAR(500) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_permissions_code UNIQUE (permission_code),
    CONSTRAINT ck_permissions_scope CHECK (scope_type IN ('GLOBAL','ORGANIZATION','ASSIGNED','OWN'))
) ENGINE=InnoDB;

CREATE TABLE user_roles (
    user_role_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    role_id BIGINT UNSIGNED NOT NULL,
    assigned_by_user_id BIGINT UNSIGNED NULL,
    assigned_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_user_roles UNIQUE (user_id, role_id),
    CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id)
        REFERENCES roles (role_id) ON DELETE RESTRICT,
    CONSTRAINT fk_user_roles_assigned_by FOREIGN KEY (assigned_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE role_permissions (
    role_permission_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    role_id BIGINT UNSIGNED NOT NULL,
    permission_id BIGINT UNSIGNED NOT NULL,
    granted_by_user_id BIGINT UNSIGNED NULL,
    granted_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_role_permissions UNIQUE (role_id, permission_id),
    CONSTRAINT fk_role_permissions_role FOREIGN KEY (role_id)
        REFERENCES roles (role_id) ON DELETE RESTRICT,
    CONSTRAINT fk_role_permissions_permission FOREIGN KEY (permission_id)
        REFERENCES permissions (permission_id) ON DELETE RESTRICT,
    CONSTRAINT fk_role_permissions_granted_by FOREIGN KEY (granted_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE user_sessions (
    user_session_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL,
    client_type VARCHAR(30) NOT NULL DEFAULT 'WEB',
    ip_hash CHAR(64) NULL,
    user_agent_hash CHAR(64) NULL,
    expires_at DATETIME(3) NOT NULL,
    revoked_at DATETIME(3) NULL,
    revoke_reason VARCHAR(300) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_user_sessions_public_id UNIQUE (public_id),
    CONSTRAINT uk_user_sessions_token_hash UNIQUE (refresh_token_hash),
    CONSTRAINT ck_user_sessions_client_type CHECK (client_type IN ('WEB','WEBAPP','MOBILE','DEVICE')),
    CONSTRAINT ck_user_sessions_expiry CHECK (expires_at > created_at),
    CONSTRAINT fk_user_sessions_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE responder_profiles (
    responder_profile_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    responder_code VARCHAR(50) NOT NULL,
    duty_status VARCHAR(20) NOT NULL DEFAULT 'OFF_DUTY',
    coverage_area VARCHAR(255) NULL,
    is_dispatch_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_responder_profiles_user UNIQUE (user_id),
    CONSTRAINT uk_responder_profiles_code UNIQUE (responder_code),
    CONSTRAINT ck_responder_profiles_status CHECK (duty_status IN ('AVAILABLE','BUSY','OFF_DUTY','UNAVAILABLE')),
    CONSTRAINT fk_responder_profiles_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE business_sequences (
    sequence_code VARCHAR(40) NOT NULL,
    sequence_date DATE NOT NULL,
    last_value BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (sequence_code, sequence_date),
    CONSTRAINT ck_business_sequences_value CHECK (last_value >= 0)
) ENGINE=InnoDB;

CREATE TABLE roads (
    road_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    road_code VARCHAR(30) NOT NULL,
    road_name VARCHAR(120) NOT NULL,
    road_type VARCHAR(30) NOT NULL DEFAULT 'EXPRESSWAY',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_roads_public_id UNIQUE (public_id),
    CONSTRAINT uk_roads_code UNIQUE (road_code),
    CONSTRAINT ck_roads_type CHECK (road_type IN ('EXPRESSWAY','NATIONAL_ROAD','OTHER'))
) ENGINE=InnoDB;

CREATE TABLE road_sections (
    road_section_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    road_id BIGINT UNSIGNED NOT NULL,
    section_code VARCHAR(50) NOT NULL,
    section_name VARCHAR(150) NOT NULL,
    start_point_name VARCHAR(120) NULL,
    end_point_name VARCHAR(120) NULL,
    start_km DECIMAL(8,3) NULL,
    end_km DECIMAL(8,3) NULL,
    region_name VARCHAR(100) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_road_sections_public_id UNIQUE (public_id),
    CONSTRAINT uk_road_sections_code UNIQUE (section_code),
    CONSTRAINT ck_road_sections_km CHECK (start_km IS NULL OR end_km IS NULL OR end_km >= start_km),
    CONSTRAINT fk_road_sections_road FOREIGN KEY (road_id)
        REFERENCES roads (road_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE cctvs (
    cctv_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    road_section_id BIGINT UNSIGNED NOT NULL,
    cctv_code VARCHAR(60) NOT NULL,
    external_its_cctv_id VARCHAR(100) NULL,
    cctv_name VARCHAR(150) NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    direction_code VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    latitude DECIMAL(10,7) NOT NULL,
    longitude DECIMAL(10,7) NOT NULL,
    km_post DECIMAL(8,3) NULL,
    operational_status VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_successful_sync_at DATETIME(3) NULL,
    metadata_json JSON NULL,
    deleted_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_cctvs_public_id UNIQUE (public_id),
    CONSTRAINT uk_cctvs_code UNIQUE (cctv_code),
    CONSTRAINT uk_cctvs_external_its_id UNIQUE (external_its_cctv_id),
    CONSTRAINT ck_cctvs_source_type CHECK (source_type IN ('ITS','MANUAL','DEMO')),
    CONSTRAINT ck_cctvs_direction CHECK (direction_code IN ('ASC','DESC','BOTH','UNKNOWN')),
    CONSTRAINT ck_cctvs_latitude CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT ck_cctvs_longitude CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT ck_cctvs_status CHECK (operational_status IN ('NORMAL','DELAYED','FAULT','INACTIVE','UNKNOWN')),
    CONSTRAINT fk_cctvs_road_section FOREIGN KEY (road_section_id)
        REFERENCES road_sections (road_section_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE cctv_streams (
    cctv_stream_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    cctv_id BIGINT UNSIGNED NOT NULL,
    stream_type VARCHAR(20) NOT NULL,
    protocol_type VARCHAR(20) NOT NULL,
    endpoint_secret_ref VARCHAR(255) NOT NULL,
    stream_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    valid_to DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    active_primary_key VARCHAR(100) GENERATED ALWAYS AS (
        CASE
            WHEN is_primary = TRUE AND stream_status = 'ACTIVE' AND valid_to IS NULL
            THEN CONCAT(CAST(cctv_id AS CHAR), ':', stream_type)
            ELSE NULL
        END
    ) STORED,
    CONSTRAINT uk_cctv_streams_public_id UNIQUE (public_id),
    CONSTRAINT uk_cctv_streams_active_primary UNIQUE (active_primary_key),
    CONSTRAINT ck_cctv_streams_type CHECK (stream_type IN ('LIVE','DEMO')),
    CONSTRAINT ck_cctv_streams_protocol CHECK (protocol_type IN ('RTSP','HLS','HTTP','FILE','OTHER')),
    CONSTRAINT ck_cctv_streams_status CHECK (stream_status IN ('ACTIVE','INACTIVE','ERROR')),
    CONSTRAINT ck_cctv_streams_period CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT fk_cctv_streams_cctv FOREIGN KEY (cctv_id)
        REFERENCES cctvs (cctv_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE its_sync_runs (
    its_sync_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    sync_type VARCHAR(30) NOT NULL DEFAULT 'CCTV_METADATA',
    run_status VARCHAR(20) NOT NULL,
    used_fallback_data BOOLEAN NOT NULL DEFAULT FALSE,
    requested_count INT UNSIGNED NOT NULL DEFAULT 0,
    inserted_count INT UNSIGNED NOT NULL DEFAULT 0,
    updated_count INT UNSIGNED NOT NULL DEFAULT 0,
    failed_count INT UNSIGNED NOT NULL DEFAULT 0,
    error_code VARCHAR(80) NULL,
    error_message VARCHAR(1000) NULL,
    trace_id VARCHAR(100) NULL,
    started_at DATETIME(3) NOT NULL,
    finished_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_its_sync_runs_public_id UNIQUE (public_id),
    CONSTRAINT uk_its_sync_runs_idempotency UNIQUE (idempotency_key),
    CONSTRAINT ck_its_sync_runs_status CHECK (run_status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED')),
    CONSTRAINT ck_its_sync_runs_period CHECK (finished_at IS NULL OR finished_at >= started_at)
) ENGINE=InnoDB;

CREATE TABLE files (
    file_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    storage_provider VARCHAR(20) NOT NULL,
    bucket_name VARCHAR(120) NOT NULL DEFAULT '',
    object_key VARCHAR(500) NOT NULL,
    original_file_name VARCHAR(255) NOT NULL,
    file_extension VARCHAR(20) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    sha256_hash CHAR(64) NOT NULL,
    file_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    access_level VARCHAR(20) NOT NULL DEFAULT 'RESTRICTED',
    created_by_user_id BIGINT UNSIGNED NULL,
    deleted_by_user_id BIGINT UNSIGNED NULL,
    deleted_at DATETIME(3) NULL,
    delete_reason VARCHAR(500) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_files_public_id UNIQUE (public_id),
    CONSTRAINT uk_files_storage_key UNIQUE (storage_provider, bucket_name, object_key),
    CONSTRAINT ck_files_provider CHECK (storage_provider IN ('LOCAL','MINIO','S3','OTHER')),
    CONSTRAINT ck_files_size CHECK (size_bytes > 0),
    CONSTRAINT ck_files_status CHECK (file_status IN ('PENDING','ACTIVE','DELETED','MISSING','QUARANTINED')),
    CONSTRAINT ck_files_access CHECK (access_level IN ('RESTRICTED','INTERNAL','PUBLIC')),
    CONSTRAINT fk_files_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT fk_files_deleted_by FOREIGN KEY (deleted_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE video_frames (
    video_frame_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    cctv_id BIGINT UNSIGNED NOT NULL,
    capture_source VARCHAR(20) NOT NULL,
    captured_at DATETIME(3) NOT NULL,
    frame_sequence BIGINT UNSIGNED NOT NULL,
    original_width INT UNSIGNED NOT NULL,
    original_height INT UNSIGNED NOT NULL,
    input_width INT UNSIGNED NULL,
    input_height INT UNSIGNED NULL,
    original_file_id BIGINT UNSIGNED NULL,
    preprocessed_file_id BIGINT UNSIGNED NULL,
    frame_status VARCHAR(20) NOT NULL DEFAULT 'CAPTURED',
    is_incident_evidence BOOLEAN NOT NULL DEFAULT FALSE,
    retention_until DATETIME(3) NULL,
    preprocessing_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_video_frames_public_id UNIQUE (public_id),
    CONSTRAINT uk_video_frames_sequence UNIQUE (cctv_id, captured_at, frame_sequence),
    CONSTRAINT ck_video_frames_source CHECK (capture_source IN ('LIVE','DEMO','UPLOAD')),
    CONSTRAINT ck_video_frames_dimensions CHECK (original_width > 0 AND original_height > 0),
    CONSTRAINT ck_video_frames_status CHECK (frame_status IN ('CAPTURED','PREPROCESSED','FAILED','RETAINED','EXPIRED')),
    CONSTRAINT fk_video_frames_cctv FOREIGN KEY (cctv_id)
        REFERENCES cctvs (cctv_id) ON DELETE RESTRICT,
    CONSTRAINT fk_video_frames_original_file FOREIGN KEY (original_file_id)
        REFERENCES files (file_id) ON DELETE RESTRICT,
    CONSTRAINT fk_video_frames_preprocessed_file FOREIGN KEY (preprocessed_file_id)
        REFERENCES files (file_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE ai_models (
    ai_model_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    model_code VARCHAR(60) NOT NULL,
    model_name VARCHAR(120) NOT NULL,
    model_category VARCHAR(20) NOT NULL,
    execution_order SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    model_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    description VARCHAR(1000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_ai_models_public_id UNIQUE (public_id),
    CONSTRAINT uk_ai_models_code UNIQUE (model_code),
    CONSTRAINT ck_ai_models_category CHECK (model_category IN ('VEHICLE','DEBRIS','WILDLIFE')),
    CONSTRAINT ck_ai_models_status CHECK (model_status IN ('ACTIVE','INACTIVE'))
) ENGINE=InnoDB;

CREATE TABLE ai_model_versions (
    ai_model_version_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    ai_model_id BIGINT UNSIGNED NOT NULL,
    version_label VARCHAR(60) NOT NULL,
    model_file_id BIGINT UNSIGNED NULL,
    artifact_secret_ref VARCHAR(255) NULL,
    framework_name VARCHAR(60) NOT NULL DEFAULT 'YOLO',
    input_width INT UNSIGNED NOT NULL,
    input_height INT UNSIGNED NOT NULL,
    default_confidence_threshold DECIMAL(5,4) NOT NULL,
    runtime_status VARCHAR(20) NOT NULL DEFAULT 'NOT_LOADED',
    is_operational BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at DATETIME(3) NULL,
    last_inference_at DATETIME(3) NULL,
    metadata_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_ai_model_versions_public_id UNIQUE (public_id),
    CONSTRAINT uk_ai_model_versions_label UNIQUE (ai_model_id, version_label),
    CONSTRAINT ck_ai_model_versions_threshold CHECK (default_confidence_threshold BETWEEN 0 AND 1),
    CONSTRAINT ck_ai_model_versions_dimensions CHECK (input_width > 0 AND input_height > 0),
    CONSTRAINT ck_ai_model_versions_runtime CHECK (runtime_status IN ('NOT_LOADED','LOADING','LOADED','ERROR','INACTIVE')),
    CONSTRAINT fk_ai_model_versions_model FOREIGN KEY (ai_model_id)
        REFERENCES ai_models (ai_model_id) ON DELETE RESTRICT,
    CONSTRAINT fk_ai_model_versions_file FOREIGN KEY (model_file_id)
        REFERENCES files (file_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE object_classes (
    object_class_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    class_code VARCHAR(60) NOT NULL,
    class_name VARCHAR(100) NOT NULL,
    object_category VARCHAR(20) NOT NULL,
    is_incident_target BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_object_classes_code UNIQUE (class_code),
    CONSTRAINT ck_object_classes_category CHECK (object_category IN ('VEHICLE','DEBRIS','WILDLIFE'))
) ENGINE=InnoDB;

CREATE TABLE model_version_classes (
    model_version_class_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ai_model_version_id BIGINT UNSIGNED NOT NULL,
    class_index INT UNSIGNED NOT NULL,
    object_class_id BIGINT UNSIGNED NOT NULL,
    confidence_threshold DECIMAL(5,4) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_model_version_classes_index UNIQUE (ai_model_version_id, class_index),
    CONSTRAINT uk_model_version_classes_class UNIQUE (ai_model_version_id, object_class_id),
    CONSTRAINT ck_model_version_classes_threshold CHECK (confidence_threshold IS NULL OR confidence_threshold BETWEEN 0 AND 1),
    CONSTRAINT fk_model_version_classes_version FOREIGN KEY (ai_model_version_id)
        REFERENCES ai_model_versions (ai_model_version_id) ON DELETE RESTRICT,
    CONSTRAINT fk_model_version_classes_object_class FOREIGN KEY (object_class_id)
        REFERENCES object_classes (object_class_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE inference_runs (
    inference_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    video_frame_id BIGINT UNSIGNED NOT NULL,
    ai_model_version_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    execution_order SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    inference_status VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
    started_at DATETIME(3) NULL,
    completed_at DATETIME(3) NULL,
    processing_time_ms INT UNSIGNED NULL,
    annotated_file_id BIGINT UNSIGNED NULL,
    ai_server_code VARCHAR(60) NULL,
    trace_id VARCHAR(100) NULL,
    error_code VARCHAR(80) NULL,
    error_message VARCHAR(1000) NULL,
    response_snapshot_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_inference_runs_public_id UNIQUE (public_id),
    CONSTRAINT uk_inference_runs_idempotency UNIQUE (idempotency_key),
    CONSTRAINT uk_inference_runs_frame_model UNIQUE (video_frame_id, ai_model_version_id),
    CONSTRAINT ck_inference_runs_status CHECK (inference_status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','SKIPPED')),
    CONSTRAINT ck_inference_runs_period CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at),
    CONSTRAINT fk_inference_runs_frame FOREIGN KEY (video_frame_id)
        REFERENCES video_frames (video_frame_id) ON DELETE CASCADE,
    CONSTRAINT fk_inference_runs_model_version FOREIGN KEY (ai_model_version_id)
        REFERENCES ai_model_versions (ai_model_version_id) ON DELETE RESTRICT,
    CONSTRAINT fk_inference_runs_annotated_file FOREIGN KEY (annotated_file_id)
        REFERENCES files (file_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE detections (
    detection_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    inference_run_id BIGINT UNSIGNED NOT NULL,
    detection_index INT UNSIGNED NOT NULL,
    object_class_id BIGINT UNSIGNED NOT NULL,
    class_index INT UNSIGNED NOT NULL,
    confidence DECIMAL(5,4) NOT NULL,
    bbox_x DECIMAL(8,7) NOT NULL,
    bbox_y DECIMAL(8,7) NOT NULL,
    bbox_width DECIMAL(8,7) NOT NULL,
    bbox_height DECIMAL(8,7) NOT NULL,
    is_threshold_passed BOOLEAN NOT NULL,
    detected_at DATETIME(3) NOT NULL,
    raw_detection_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_detections_public_id UNIQUE (public_id),
    CONSTRAINT uk_detections_index UNIQUE (inference_run_id, detection_index),
    CONSTRAINT ck_detections_confidence CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_detections_bbox CHECK (
        bbox_x BETWEEN 0 AND 1 AND bbox_y BETWEEN 0 AND 1 AND
        bbox_width > 0 AND bbox_width <= 1 AND
        bbox_height > 0 AND bbox_height <= 1 AND
        bbox_x + bbox_width <= 1 AND bbox_y + bbox_height <= 1
    ),
    CONSTRAINT fk_detections_inference_run FOREIGN KEY (inference_run_id)
        REFERENCES inference_runs (inference_run_id) ON DELETE CASCADE,
    CONSTRAINT fk_detections_object_class FOREIGN KEY (object_class_id)
        REFERENCES object_classes (object_class_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE tracking_sessions (
    tracking_session_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    cctv_id BIGINT UNSIGNED NOT NULL,
    session_key VARCHAR(120) NOT NULL,
    tracking_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    started_at DATETIME(3) NOT NULL,
    ended_at DATETIME(3) NULL,
    tracker_name VARCHAR(60) NULL,
    tracker_version VARCHAR(60) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_tracking_sessions_public_id UNIQUE (public_id),
    CONSTRAINT uk_tracking_sessions_key UNIQUE (cctv_id, session_key),
    CONSTRAINT ck_tracking_sessions_status CHECK (tracking_status IN ('ACTIVE','ENDED','FAILED')),
    CONSTRAINT ck_tracking_sessions_period CHECK (ended_at IS NULL OR ended_at >= started_at),
    CONSTRAINT fk_tracking_sessions_cctv FOREIGN KEY (cctv_id)
        REFERENCES cctvs (cctv_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE tracked_objects (
    tracked_object_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    tracking_session_id BIGINT UNSIGNED NOT NULL,
    cctv_id BIGINT UNSIGNED NOT NULL,
    external_track_id VARCHAR(100) NOT NULL,
    object_class_id BIGINT UNSIGNED NOT NULL,
    tracking_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    first_detected_at DATETIME(3) NOT NULL,
    last_detected_at DATETIME(3) NOT NULL,
    duration_ms BIGINT UNSIGNED NOT NULL DEFAULT 0,
    detection_count INT UNSIGNED NOT NULL DEFAULT 1,
    last_confidence DECIMAL(5,4) NOT NULL,
    max_confidence DECIMAL(5,4) NOT NULL,
    average_confidence DECIMAL(5,4) NOT NULL,
    version_no INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_tracked_objects_public_id UNIQUE (public_id),
    CONSTRAINT uk_tracked_objects_external UNIQUE (tracking_session_id, external_track_id),
    CONSTRAINT ck_tracked_objects_status CHECK (tracking_status IN ('ACTIVE','LOST','ENDED')),
    CONSTRAINT ck_tracked_objects_period CHECK (last_detected_at >= first_detected_at),
    CONSTRAINT ck_tracked_objects_confidence CHECK (
        last_confidence BETWEEN 0 AND 1 AND max_confidence BETWEEN 0 AND 1 AND average_confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT fk_tracked_objects_session FOREIGN KEY (tracking_session_id)
        REFERENCES tracking_sessions (tracking_session_id) ON DELETE RESTRICT,
    CONSTRAINT fk_tracked_objects_cctv FOREIGN KEY (cctv_id)
        REFERENCES cctvs (cctv_id) ON DELETE RESTRICT,
    CONSTRAINT fk_tracked_objects_class FOREIGN KEY (object_class_id)
        REFERENCES object_classes (object_class_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE track_observations (
    track_observation_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tracked_object_id BIGINT UNSIGNED NOT NULL,
    detection_id BIGINT UNSIGNED NOT NULL,
    observation_sequence INT UNSIGNED NOT NULL,
    observed_at DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_track_observations_detection UNIQUE (detection_id),
    CONSTRAINT uk_track_observations_sequence UNIQUE (tracked_object_id, observation_sequence),
    CONSTRAINT fk_track_observations_object FOREIGN KEY (tracked_object_id)
        REFERENCES tracked_objects (tracked_object_id) ON DELETE CASCADE,
    CONSTRAINT fk_track_observations_detection FOREIGN KEY (detection_id)
        REFERENCES detections (detection_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE risk_evaluations (
    risk_evaluation_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    tracked_object_id BIGINT UNSIGNED NOT NULL,
    representative_detection_id BIGINT UNSIGNED NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    input_hash CHAR(64) NOT NULL,
    object_category VARCHAR(20) NOT NULL,
    confidence_calculation_type VARCHAR(20) NOT NULL,
    confidence_value DECIMAL(5,4) NOT NULL,
    duration_ms BIGINT UNSIGNED NOT NULL,
    repeat_count INT UNSIGNED NOT NULL,
    risk_score DECIMAL(5,2) NOT NULL,
    risk_grade VARCHAR(20) NOT NULL,
    is_incident_candidate BOOLEAN NOT NULL,
    exclusion_reason VARCHAR(80) NULL,
    rule_code VARCHAR(60) NOT NULL,
    rule_version_snapshot VARCHAR(60) NOT NULL,
    rule_snapshot_json JSON NOT NULL,
    evaluated_at DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_risk_evaluations_public_id UNIQUE (public_id),
    CONSTRAINT uk_risk_evaluations_idempotency UNIQUE (idempotency_key),
    CONSTRAINT uk_risk_evaluations_input UNIQUE (tracked_object_id, input_hash),
    CONSTRAINT ck_risk_evaluations_category CHECK (object_category IN ('VEHICLE','DEBRIS','WILDLIFE')),
    CONSTRAINT ck_risk_evaluations_confidence_type CHECK (confidence_calculation_type IN ('LAST','MAX','AVERAGE')),
    CONSTRAINT ck_risk_evaluations_confidence CHECK (confidence_value BETWEEN 0 AND 1),
    CONSTRAINT ck_risk_evaluations_score CHECK (risk_score BETWEEN 0 AND 100),
    CONSTRAINT ck_risk_evaluations_grade CHECK (risk_grade IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CONSTRAINT fk_risk_evaluations_object FOREIGN KEY (tracked_object_id)
        REFERENCES tracked_objects (tracked_object_id) ON DELETE RESTRICT,
    CONSTRAINT fk_risk_evaluations_detection FOREIGN KEY (representative_detection_id)
        REFERENCES detections (detection_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE incident_state_transitions (
    incident_state_transition_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    actor_scope VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_incident_state_transitions UNIQUE (from_status, to_status, actor_scope),
    CONSTRAINT ck_incident_transition_actor CHECK (actor_scope IN ('SYSTEM','CONTROLLER','RESPONDER','ADMIN'))
) ENGINE=InnoDB;

CREATE TABLE incidents (
    incident_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    incident_no VARCHAR(40) NOT NULL,
    source_type VARCHAR(20) NOT NULL DEFAULT 'AI',
    cctv_id BIGINT UNSIGNED NOT NULL,
    road_section_id BIGINT UNSIGNED NOT NULL,
    tracked_object_id BIGINT UNSIGNED NULL,
    representative_detection_id BIGINT UNSIGNED NULL,
    latest_risk_evaluation_id BIGINT UNSIGNED NULL,
    object_class_id BIGINT UNSIGNED NULL,
    object_category VARCHAR(20) NOT NULL,
    incident_status VARCHAR(30) NOT NULL DEFAULT 'NEW',
    current_risk_score DECIMAL(5,2) NOT NULL,
    current_risk_grade VARCHAR(20) NOT NULL,
    priority_order SMALLINT UNSIGNED NOT NULL DEFAULT 100,
    detected_at DATETIME(3) NOT NULL,
    first_detected_at DATETIME(3) NOT NULL,
    last_detected_at DATETIME(3) NOT NULL,
    detection_count INT UNSIGNED NOT NULL DEFAULT 1,
    duration_ms BIGINT UNSIGNED NOT NULL DEFAULT 0,
    current_controller_user_id BIGINT UNSIGNED NULL,
    acknowledged_by_user_id BIGINT UNSIGNED NULL,
    acknowledged_at DATETIME(3) NULL,
    claimed_at DATETIME(3) NULL,
    cctv_name_snapshot VARCHAR(150) NOT NULL,
    road_name_snapshot VARCHAR(120) NOT NULL,
    road_section_name_snapshot VARCHAR(150) NOT NULL,
    direction_snapshot VARCHAR(20) NOT NULL,
    latitude_snapshot DECIMAL(10,7) NOT NULL,
    longitude_snapshot DECIMAL(10,7) NOT NULL,
    location_description_snapshot VARCHAR(255) NULL,
    version_no INT UNSIGNED NOT NULL DEFAULT 0,
    closed_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    active_track_key VARCHAR(100) GENERATED ALWAYS AS (
        CASE
            WHEN tracked_object_id IS NOT NULL AND incident_status NOT IN ('CLOSED','FALSE_POSITIVE')
            THEN CONCAT(CAST(cctv_id AS CHAR), ':', CAST(tracked_object_id AS CHAR))
            ELSE NULL
        END
    ) STORED,
    CONSTRAINT uk_incidents_public_id UNIQUE (public_id),
    CONSTRAINT uk_incidents_no UNIQUE (incident_no),
    CONSTRAINT uk_incidents_active_track UNIQUE (active_track_key),
    CONSTRAINT ck_incidents_source CHECK (source_type IN ('AI','MANUAL','CITIZEN_REPORT')),
    CONSTRAINT ck_incidents_category CHECK (object_category IN ('VEHICLE','DEBRIS','WILDLIFE','OTHER')),
    CONSTRAINT ck_incidents_status CHECK (incident_status IN (
        'NEW','ACKNOWLEDGED','CLAIMED','UNDER_REVIEW','FALSE_POSITIVE','DISPATCH_REQUESTED',
        'DISPATCHED','ON_SCENE','ACTION_IN_PROGRESS','ACTION_COMPLETED','CLOSED'
    )),
    CONSTRAINT ck_incidents_score CHECK (current_risk_score BETWEEN 0 AND 100),
    CONSTRAINT ck_incidents_grade CHECK (current_risk_grade IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CONSTRAINT ck_incidents_period CHECK (last_detected_at >= first_detected_at),
    CONSTRAINT ck_incidents_location CHECK (latitude_snapshot BETWEEN -90 AND 90 AND longitude_snapshot BETWEEN -180 AND 180),
    CONSTRAINT fk_incidents_cctv FOREIGN KEY (cctv_id)
        REFERENCES cctvs (cctv_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incidents_road_section FOREIGN KEY (road_section_id)
        REFERENCES road_sections (road_section_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incidents_tracked_object FOREIGN KEY (tracked_object_id)
        REFERENCES tracked_objects (tracked_object_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incidents_representative_detection FOREIGN KEY (representative_detection_id)
        REFERENCES detections (detection_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incidents_latest_risk FOREIGN KEY (latest_risk_evaluation_id)
        REFERENCES risk_evaluations (risk_evaluation_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incidents_object_class FOREIGN KEY (object_class_id)
        REFERENCES object_classes (object_class_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incidents_current_controller FOREIGN KEY (current_controller_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT fk_incidents_acknowledged_by FOREIGN KEY (acknowledged_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE incident_evidences (
    incident_evidence_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    incident_id BIGINT UNSIGNED NOT NULL,
    detection_id BIGINT UNSIGNED NULL,
    risk_evaluation_id BIGINT UNSIGNED NULL,
    video_frame_id BIGINT UNSIGNED NULL,
    evidence_type VARCHAR(30) NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    added_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_incident_evidences_detection UNIQUE (detection_id),
    CONSTRAINT uk_incident_evidences_risk UNIQUE (risk_evaluation_id),
    CONSTRAINT ck_incident_evidences_target CHECK (
        detection_id IS NOT NULL OR risk_evaluation_id IS NOT NULL OR video_frame_id IS NOT NULL
    ),
    CONSTRAINT ck_incident_evidences_type CHECK (evidence_type IN ('PRIMARY','ADDITIONAL','MERGED','MANUAL')),
    CONSTRAINT fk_incident_evidences_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_evidences_detection FOREIGN KEY (detection_id)
        REFERENCES detections (detection_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incident_evidences_risk FOREIGN KEY (risk_evaluation_id)
        REFERENCES risk_evaluations (risk_evaluation_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incident_evidences_frame FOREIGN KEY (video_frame_id)
        REFERENCES video_frames (video_frame_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE incident_files (
    incident_file_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    incident_id BIGINT UNSIGNED NOT NULL,
    file_id BIGINT UNSIGNED NOT NULL,
    file_role VARCHAR(30) NOT NULL,
    uploaded_by_user_id BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_incident_files UNIQUE (incident_id, file_id, file_role),
    CONSTRAINT ck_incident_files_role CHECK (file_role IN ('ORIGINAL_FRAME','ANNOTATED_FRAME','VIDEO_CLIP','ATTACHMENT')),
    CONSTRAINT fk_incident_files_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_files_file FOREIGN KEY (file_id)
        REFERENCES files (file_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incident_files_uploaded_by FOREIGN KEY (uploaded_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE incident_status_histories (
    incident_status_history_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    incident_id BIGINT UNSIGNED NOT NULL,
    from_status VARCHAR(30) NULL,
    to_status VARCHAR(30) NOT NULL,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id BIGINT UNSIGNED NULL,
    change_source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    idempotency_key VARCHAR(160) NOT NULL,
    reason_code VARCHAR(80) NULL,
    reason_text VARCHAR(1000) NULL,
    metadata_json JSON NULL,
    changed_at DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_incident_status_histories_public_id UNIQUE (public_id),
    CONSTRAINT uk_incident_status_histories_idempotency UNIQUE (idempotency_key),
    CONSTRAINT ck_incident_status_histories_actor CHECK (actor_type IN ('USER','SYSTEM','DEVICE')),
    CONSTRAINT ck_incident_status_histories_source CHECK (change_source IN ('MANUAL','SYSTEM','DEVICE','AUTO')),
    CONSTRAINT fk_incident_status_histories_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_status_histories_actor FOREIGN KEY (actor_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE incident_claims (
    incident_claim_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    incident_id BIGINT UNSIGNED NOT NULL,
    controller_user_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    claimed_at DATETIME(3) NOT NULL,
    released_at DATETIME(3) NULL,
    release_reason VARCHAR(500) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    active_incident_id BIGINT UNSIGNED GENERATED ALWAYS AS (
        CASE WHEN released_at IS NULL THEN incident_id ELSE NULL END
    ) STORED,
    CONSTRAINT uk_incident_claims_public_id UNIQUE (public_id),
    CONSTRAINT uk_incident_claims_idempotency UNIQUE (idempotency_key),
    CONSTRAINT uk_incident_claims_active UNIQUE (active_incident_id),
    CONSTRAINT ck_incident_claims_period CHECK (released_at IS NULL OR released_at >= claimed_at),
    CONSTRAINT fk_incident_claims_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_claims_controller FOREIGN KEY (controller_user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE incident_decisions (
    incident_decision_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    incident_id BIGINT UNSIGNED NOT NULL,
    decision_type VARCHAR(30) NOT NULL,
    decision_reason VARCHAR(1000) NOT NULL,
    decided_by_user_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    decided_at DATETIME(3) NOT NULL,
    superseded_at DATETIME(3) NULL,
    superseded_by_decision_id BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    active_incident_id BIGINT UNSIGNED GENERATED ALWAYS AS (
        CASE WHEN superseded_at IS NULL THEN incident_id ELSE NULL END
    ) STORED,
    CONSTRAINT uk_incident_decisions_public_id UNIQUE (public_id),
    CONSTRAINT uk_incident_decisions_idempotency UNIQUE (idempotency_key),
    CONSTRAINT uk_incident_decisions_active UNIQUE (active_incident_id),
    CONSTRAINT ck_incident_decisions_type CHECK (decision_type IN ('REAL_RISK','FALSE_POSITIVE','NEEDS_REVIEW','NO_DISPATCH')),
    CONSTRAINT ck_incident_decisions_period CHECK (superseded_at IS NULL OR superseded_at >= decided_at),
    CONSTRAINT fk_incident_decisions_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_decisions_user FOREIGN KEY (decided_by_user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incident_decisions_superseded_by FOREIGN KEY (superseded_by_decision_id)
        REFERENCES incident_decisions (incident_decision_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE incident_notes (
    incident_note_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    incident_id BIGINT UNSIGNED NOT NULL,
    note_text TEXT NOT NULL,
    created_by_user_id BIGINT UNSIGNED NOT NULL,
    deleted_by_user_id BIGINT UNSIGNED NULL,
    deleted_at DATETIME(3) NULL,
    delete_reason VARCHAR(500) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_incident_notes_public_id UNIQUE (public_id),
    CONSTRAINT fk_incident_notes_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_notes_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_incident_notes_deleted_by FOREIGN KEY (deleted_by_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE dispatch_state_transitions (
    dispatch_state_transition_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    actor_scope VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_dispatch_state_transitions UNIQUE (from_status, to_status, actor_scope),
    CONSTRAINT ck_dispatch_transition_actor CHECK (actor_scope IN ('CONTROLLER','RESPONDER','SYSTEM','DEVICE','ADMIN'))
) ENGINE=InnoDB;

CREATE TABLE dispatch_requests (
    dispatch_request_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    incident_id BIGINT UNSIGNED NOT NULL,
    attempt_no SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    previous_dispatch_request_id BIGINT UNSIGNED NULL,
    responder_user_id BIGINT UNSIGNED NOT NULL,
    assigned_by_user_id BIGINT UNSIGNED NOT NULL,
    dispatch_status VARCHAR(30) NOT NULL DEFAULT 'REQUESTED',
    status_change_method VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    request_message VARCHAR(1000) NULL,
    rejection_reason VARCHAR(1000) NULL,
    requested_at DATETIME(3) NOT NULL,
    accepted_at DATETIME(3) NULL,
    departed_at DATETIME(3) NULL,
    en_route_at DATETIME(3) NULL,
    arrived_at DATETIME(3) NULL,
    action_started_at DATETIME(3) NULL,
    action_completed_at DATETIME(3) NULL,
    cancelled_at DATETIME(3) NULL,
    version_no INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    active_incident_id BIGINT UNSIGNED GENERATED ALWAYS AS (
        CASE WHEN dispatch_status NOT IN ('REJECTED','CANCELLED','ACTION_COMPLETED') THEN incident_id ELSE NULL END
    ) STORED,
    active_responder_id BIGINT UNSIGNED GENERATED ALWAYS AS (
        CASE WHEN dispatch_status NOT IN ('REJECTED','CANCELLED','ACTION_COMPLETED') THEN responder_user_id ELSE NULL END
    ) STORED,
    CONSTRAINT uk_dispatch_requests_public_id UNIQUE (public_id),
    CONSTRAINT uk_dispatch_requests_attempt UNIQUE (incident_id, attempt_no),
    CONSTRAINT uk_dispatch_requests_active_incident UNIQUE (active_incident_id),
    CONSTRAINT uk_dispatch_requests_active_responder UNIQUE (active_responder_id),
    CONSTRAINT ck_dispatch_requests_status CHECK (dispatch_status IN (
        'REQUESTED','ACCEPTED','REJECTED','DEPARTED','EN_ROUTE','ARRIVED',
        'ACTION_IN_PROGRESS','ACTION_COMPLETED','CANCELLED'
    )),
    CONSTRAINT ck_dispatch_requests_method CHECK (status_change_method IN ('MANUAL','DEVICE','AUTO')),
    CONSTRAINT fk_dispatch_requests_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE RESTRICT,
    CONSTRAINT fk_dispatch_requests_previous FOREIGN KEY (previous_dispatch_request_id)
        REFERENCES dispatch_requests (dispatch_request_id) ON DELETE SET NULL,
    CONSTRAINT fk_dispatch_requests_responder FOREIGN KEY (responder_user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_dispatch_requests_assigned_by FOREIGN KEY (assigned_by_user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE dispatch_status_histories (
    dispatch_status_history_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    dispatch_request_id BIGINT UNSIGNED NOT NULL,
    from_status VARCHAR(30) NULL,
    to_status VARCHAR(30) NOT NULL,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id BIGINT UNSIGNED NULL,
    change_method VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    idempotency_key VARCHAR(160) NOT NULL,
    reason_text VARCHAR(1000) NULL,
    metadata_json JSON NULL,
    changed_at DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_dispatch_status_histories_public_id UNIQUE (public_id),
    CONSTRAINT uk_dispatch_status_histories_idempotency UNIQUE (idempotency_key),
    CONSTRAINT ck_dispatch_status_histories_actor CHECK (actor_type IN ('USER','SYSTEM','DEVICE')),
    CONSTRAINT ck_dispatch_status_histories_method CHECK (change_method IN ('MANUAL','DEVICE','AUTO')),
    CONSTRAINT fk_dispatch_status_histories_dispatch FOREIGN KEY (dispatch_request_id)
        REFERENCES dispatch_requests (dispatch_request_id) ON DELETE CASCADE,
    CONSTRAINT fk_dispatch_status_histories_actor FOREIGN KEY (actor_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE field_action_reports (
    field_action_report_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    dispatch_request_id BIGINT UNSIGNED NOT NULL,
    action_type VARCHAR(60) NOT NULL,
    action_detail TEXT NOT NULL,
    created_by_user_id BIGINT UNSIGNED NOT NULL,
    action_started_at DATETIME(3) NULL,
    action_completed_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_field_action_reports_public_id UNIQUE (public_id),
    CONSTRAINT uk_field_action_reports_dispatch UNIQUE (dispatch_request_id),
    CONSTRAINT ck_field_action_reports_period CHECK (
        action_completed_at IS NULL OR action_started_at IS NULL OR action_completed_at >= action_started_at
    ),
    CONSTRAINT fk_field_action_reports_dispatch FOREIGN KEY (dispatch_request_id)
        REFERENCES dispatch_requests (dispatch_request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_field_action_reports_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE field_action_files (
    field_action_file_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    field_action_report_id BIGINT UNSIGNED NOT NULL,
    file_id BIGINT UNSIGNED NOT NULL,
    photo_phase VARCHAR(20) NOT NULL,
    display_order SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_field_action_files UNIQUE (field_action_report_id, file_id),
    CONSTRAINT ck_field_action_files_phase CHECK (photo_phase IN ('BEFORE','AFTER','OTHER')),
    CONSTRAINT fk_field_action_files_report FOREIGN KEY (field_action_report_id)
        REFERENCES field_action_reports (field_action_report_id) ON DELETE CASCADE,
    CONSTRAINT fk_field_action_files_file FOREIGN KEY (file_id)
        REFERENCES files (file_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE notifications (
    notification_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    deduplication_key VARCHAR(180) NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    body VARCHAR(2000) NOT NULL,
    resource_type VARCHAR(50) NULL,
    resource_public_id CHAR(36) NULL,
    payload_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_notifications_public_id UNIQUE (public_id),
    CONSTRAINT uk_notifications_dedup UNIQUE (deduplication_key),
    CONSTRAINT ck_notifications_severity CHECK (severity IN ('INFO','WARNING','HIGH','CRITICAL'))
) ENGINE=InnoDB;

CREATE TABLE notification_recipients (
    notification_recipient_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    notification_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    delivered_at DATETIME(3) NULL,
    read_at DATETIME(3) NULL,
    failure_reason VARCHAR(1000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_notification_recipients UNIQUE (notification_id, user_id),
    CONSTRAINT ck_notification_recipients_status CHECK (delivery_status IN ('PENDING','SENT','FAILED')),
    CONSTRAINT fk_notification_recipients_notification FOREIGN KEY (notification_id)
        REFERENCES notifications (notification_id) ON DELETE CASCADE,
    CONSTRAINT fk_notification_recipients_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE event_outbox (
    event_outbox_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_uuid CHAR(36) NOT NULL,
    aggregate_type VARCHAR(50) NOT NULL,
    aggregate_public_id CHAR(36) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload_json JSON NOT NULL,
    publish_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retry_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    locked_by VARCHAR(100) NULL,
    locked_at DATETIME(3) NULL,
    published_at DATETIME(3) NULL,
    last_error VARCHAR(1000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_event_outbox_uuid UNIQUE (event_uuid),
    CONSTRAINT ck_event_outbox_status CHECK (publish_status IN ('PENDING','PROCESSING','PUBLISHED','FAILED','DEAD'))
) ENGINE=InnoDB;

CREATE TABLE audit_logs (
    audit_log_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    public_id CHAR(36) NOT NULL,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id BIGINT UNSIGNED NULL,
    action_code VARCHAR(100) NOT NULL,
    resource_type VARCHAR(60) NOT NULL,
    resource_public_id CHAR(36) NULL,
    result_status VARCHAR(20) NOT NULL,
    before_json JSON NULL,
    after_json JSON NULL,
    reason_text VARCHAR(1000) NULL,
    trace_id VARCHAR(100) NULL,
    request_ip_hash CHAR(64) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_audit_logs_public_id UNIQUE (public_id),
    CONSTRAINT ck_audit_logs_actor CHECK (actor_type IN ('USER','SYSTEM','DEVICE')),
    CONSTRAINT ck_audit_logs_result CHECK (result_status IN ('SUCCESS','FAILURE','DENIED')),
    CONSTRAINT fk_audit_logs_actor FOREIGN KEY (actor_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE idempotency_keys (
    idempotency_key_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    scope_code VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(180) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    processing_status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',
    resource_type VARCHAR(60) NULL,
    resource_public_id CHAR(36) NULL,
    response_code INT UNSIGNED NULL,
    response_snapshot_json JSON NULL,
    expires_at DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT uk_idempotency_keys UNIQUE (scope_code, idempotency_key),
    CONSTRAINT ck_idempotency_keys_status CHECK (processing_status IN ('PROCESSING','COMPLETED','FAILED')),
    CONSTRAINT ck_idempotency_keys_expiry CHECK (expires_at > created_at)
) ENGINE=InnoDB;

-- 주요 조회 인덱스
CREATE INDEX ix_users_status_org ON users (account_status, organization_id);
CREATE INDEX ix_user_sessions_user_expiry ON user_sessions (user_id, expires_at, revoked_at);
CREATE INDEX ix_cctvs_section_status ON cctvs (road_section_id, operational_status, is_active);
CREATE INDEX ix_cctvs_location ON cctvs (latitude, longitude);
CREATE INDEX ix_its_sync_runs_started ON its_sync_runs (started_at, run_status);
CREATE INDEX ix_files_hash ON files (sha256_hash, size_bytes);
CREATE INDEX ix_video_frames_cctv_time ON video_frames (cctv_id, captured_at DESC);
CREATE INDEX ix_inference_runs_status_created ON inference_runs (inference_status, created_at);
CREATE INDEX ix_detections_class_confidence ON detections (object_class_id, confidence, detected_at);
CREATE INDEX ix_tracking_sessions_cctv_status ON tracking_sessions (cctv_id, tracking_status, started_at);
CREATE INDEX ix_tracked_objects_cctv_status_time ON tracked_objects (cctv_id, tracking_status, last_detected_at DESC);
CREATE INDEX ix_track_observations_object_time ON track_observations (tracked_object_id, observed_at);
CREATE INDEX ix_risk_evaluations_candidate_time ON risk_evaluations (is_incident_candidate, risk_grade, evaluated_at DESC);
CREATE INDEX ix_incidents_list ON incidents (incident_status, current_risk_grade, detected_at DESC);
CREATE INDEX ix_incidents_cctv_time ON incidents (cctv_id, detected_at DESC);
CREATE INDEX ix_incidents_controller_status ON incidents (current_controller_user_id, incident_status, detected_at DESC);
CREATE INDEX ix_incident_status_histories_incident_time ON incident_status_histories (incident_id, changed_at);
CREATE INDEX ix_incident_notes_incident_time ON incident_notes (incident_id, created_at);
CREATE INDEX ix_dispatch_requests_responder_status ON dispatch_requests (responder_user_id, dispatch_status, requested_at DESC);
CREATE INDEX ix_dispatch_requests_incident ON dispatch_requests (incident_id, attempt_no DESC);
CREATE INDEX ix_dispatch_status_histories_dispatch_time ON dispatch_status_histories (dispatch_request_id, changed_at);
CREATE INDEX ix_notification_recipients_user_read ON notification_recipients (user_id, read_at, notification_recipient_id DESC);
CREATE INDEX ix_event_outbox_worker ON event_outbox (publish_status, next_attempt_at, event_outbox_id);
CREATE INDEX ix_audit_logs_actor_time ON audit_logs (actor_user_id, created_at DESC);
CREATE INDEX ix_audit_logs_resource ON audit_logs (resource_type, resource_public_id, created_at DESC);
CREATE INDEX ix_idempotency_keys_expiry ON idempotency_keys (expires_at, processing_status);