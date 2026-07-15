-- ============================================================
-- 도로보GO MVP 기준정보 Seed
-- ============================================================
USE roadbogo;

INSERT INTO roles (role_code, role_name, description) VALUES
('SYSTEM_ADMIN', '시스템 관리자', '서비스 전체 운영 및 사용자·권한·서버·DB 관리'),
('CONTROL_MANAGER', '관제 관리자', '관제 업무 감독, 통계 및 관제자 관리'),
('CONTROLLER', '관제자', '사건 확인·선점·판정·출동 요청'),
('RESPONDER', '출동 담당자', '출동 요청 수락·현장 조치'),
('GENERAL_USER', '일반 사용자', '고도화 단계 시민 신고 사용자'),
('AI_MODEL_USER', 'AI 모델 사용자', '고도화 단계 사용자 모델 테스트');

INSERT INTO permissions (permission_code, permission_name, resource_code, action_code, scope_type) VALUES
('USER.READ_ALL','전체 사용자 조회','USER','READ','GLOBAL'),
('USER.WRITE','사용자 등록·수정·비활성화','USER','WRITE','GLOBAL'),
('ROLE.MANAGE','역할·권한 관리','ROLE','MANAGE','GLOBAL'),
('CCTV.READ','CCTV 조회','CCTV','READ','GLOBAL'),
('CCTV.MANAGE','CCTV 관리','CCTV','MANAGE','GLOBAL'),
('INCIDENT.READ_ALL','전체 사건 조회','INCIDENT','READ','GLOBAL'),
('INCIDENT.READ_ASSIGNED','담당 사건 조회','INCIDENT','READ','ASSIGNED'),
('INCIDENT.CLAIM','사건 선점','INCIDENT','CLAIM','GLOBAL'),
('INCIDENT.DECIDE','위험·오탐 판정','INCIDENT','DECIDE','ASSIGNED'),
('INCIDENT.CLOSE','사건 종료','INCIDENT','CLOSE','ASSIGNED'),
('DISPATCH.ASSIGN','출동 배정','DISPATCH','ASSIGN','ASSIGNED'),
('DISPATCH.READ_OWN','본인 출동 조회','DISPATCH','READ','OWN'),
('DISPATCH.UPDATE_OWN','본인 출동 상태 변경','DISPATCH','UPDATE','OWN'),
('FILE.READ_ASSIGNED','담당 사건 파일 조회','FILE','READ','ASSIGNED'),
('FILE.UPLOAD_ACTION','현장 조치 파일 업로드','FILE','UPLOAD','OWN'),
('NOTIFICATION.READ_OWN','본인 알림 조회','NOTIFICATION','READ','OWN'),
('AUDIT.READ','감사 로그 조회','AUDIT','READ','GLOBAL'),
('DB.STATUS.READ','DB 백업·복제 조회','DB_STATUS','READ','GLOBAL');

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r CROSS JOIN permissions p
WHERE r.role_code = 'SYSTEM_ADMIN';

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r JOIN permissions p ON p.permission_code IN (
    'CCTV.READ','INCIDENT.READ_ALL','INCIDENT.CLAIM','INCIDENT.DECIDE','INCIDENT.CLOSE',
    'DISPATCH.ASSIGN','FILE.READ_ASSIGNED','NOTIFICATION.READ_OWN'
)
WHERE r.role_code = 'CONTROL_MANAGER';

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r JOIN permissions p ON p.permission_code IN (
    'CCTV.READ','INCIDENT.READ_ALL','INCIDENT.CLAIM','INCIDENT.DECIDE','INCIDENT.CLOSE',
    'DISPATCH.ASSIGN','FILE.READ_ASSIGNED','NOTIFICATION.READ_OWN'
)
WHERE r.role_code = 'CONTROLLER';

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r JOIN permissions p ON p.permission_code IN (
    'CCTV.READ','INCIDENT.READ_ASSIGNED','DISPATCH.READ_OWN','DISPATCH.UPDATE_OWN',
    'FILE.READ_ASSIGNED','FILE.UPLOAD_ACTION','NOTIFICATION.READ_OWN'
)
WHERE r.role_code = 'RESPONDER';

INSERT INTO object_classes (class_code, class_name, object_category, is_incident_target) VALUES
('CAR','승용차','VEHICLE',FALSE),
('BUS','버스','VEHICLE',FALSE),
('TRUCK','트럭','VEHICLE',FALSE),
('MOTORCYCLE','이륜차','VEHICLE',FALSE),
('BOX','박스','DEBRIS',TRUE),
('TIRE','타이어','DEBRIS',TRUE),
('CARGO','적재물','DEBRIS',TRUE),
('WILDLIFE','야생동물','WILDLIFE',TRUE);

INSERT INTO incident_state_transitions (from_status, to_status, actor_scope) VALUES
('NEW','ACKNOWLEDGED','CONTROLLER'),
('ACKNOWLEDGED','CLAIMED','CONTROLLER'),
('CLAIMED','UNDER_REVIEW','CONTROLLER'),
('UNDER_REVIEW','FALSE_POSITIVE','CONTROLLER'),
('UNDER_REVIEW','CLOSED','CONTROLLER'),
('UNDER_REVIEW','DISPATCH_REQUESTED','CONTROLLER'),
('DISPATCH_REQUESTED','DISPATCHED','SYSTEM'),
('DISPATCHED','ON_SCENE','SYSTEM'),
('ON_SCENE','ACTION_IN_PROGRESS','SYSTEM'),
('ACTION_IN_PROGRESS','ACTION_COMPLETED','SYSTEM'),
('ACTION_COMPLETED','CLOSED','CONTROLLER');

INSERT INTO dispatch_state_transitions (from_status, to_status, actor_scope) VALUES
('REQUESTED','ACCEPTED','RESPONDER'),
('REQUESTED','REJECTED','RESPONDER'),
('REQUESTED','CANCELLED','CONTROLLER'),
('ACCEPTED','DEPARTED','RESPONDER'),
('DEPARTED','EN_ROUTE','RESPONDER'),
('EN_ROUTE','ARRIVED','RESPONDER'),
('ARRIVED','ACTION_IN_PROGRESS','RESPONDER'),
('ACTION_IN_PROGRESS','ACTION_COMPLETED','RESPONDER');