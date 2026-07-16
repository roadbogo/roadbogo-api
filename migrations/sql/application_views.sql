-- ============================================================
-- 도로보GO MVP 조회 View
-- ============================================================
USE roadbogo;

CREATE OR REPLACE VIEW v_incident_dashboard AS
SELECT
    i.public_id AS incident_public_id,
    i.incident_no,
    i.incident_status,
    i.object_category,
    i.current_risk_score,
    i.current_risk_grade,
    i.priority_order,
    i.detected_at,
    i.last_detected_at,
    i.detection_count,
    i.duration_ms,
    i.cctv_name_snapshot,
    i.road_name_snapshot,
    i.road_section_name_snapshot,
    i.direction_snapshot,
    i.latitude_snapshot,
    i.longitude_snapshot,
    u.public_id AS controller_public_id,
    u.user_name AS controller_name,
    d.public_id AS active_dispatch_public_id,
    d.dispatch_status,
    ru.public_id AS responder_public_id,
    ru.user_name AS responder_name
FROM incidents i
LEFT JOIN users u ON u.user_id = i.current_controller_user_id
LEFT JOIN dispatch_requests d
    ON d.incident_id = i.incident_id
   AND d.dispatch_status NOT IN ('REJECTED','CANCELLED','ACTION_COMPLETED')
LEFT JOIN users ru ON ru.user_id = d.responder_user_id;

CREATE OR REPLACE VIEW v_responder_active_dispatches AS
SELECT
    d.public_id AS dispatch_public_id,
    d.dispatch_status,
    d.requested_at,
    d.responder_user_id,
    i.public_id AS incident_public_id,
    i.incident_no,
    i.object_category,
    i.current_risk_grade,
    i.cctv_name_snapshot,
    i.road_name_snapshot,
    i.road_section_name_snapshot,
    i.direction_snapshot,
    i.latitude_snapshot,
    i.longitude_snapshot
FROM dispatch_requests d
JOIN incidents i ON i.incident_id = d.incident_id
WHERE d.dispatch_status NOT IN ('REJECTED','CANCELLED','ACTION_COMPLETED');

CREATE OR REPLACE VIEW v_unread_notification_counts AS
SELECT user_id, COUNT(*) AS unread_count
FROM notification_recipients
WHERE read_at IS NULL
GROUP BY user_id;
