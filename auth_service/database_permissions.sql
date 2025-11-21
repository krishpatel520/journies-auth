-- ============================================================================
-- DATABASE PERMISSIONS - Multi-service single-table pattern
-- ============================================================================
-- This script enforces column-level permissions for the shared journies_usermodel table
-- Auth Service: Can only update auth-related columns
-- Compass Service: Can only update compass-related columns

-- Create roles if they don't exist
DO $$ BEGIN
    CREATE ROLE auth_role LOGIN PASSWORD 'postgres';
EXCEPTION WHEN DUPLICATE_OBJECT THEN
    NULL;
END $$;

DO $$ BEGIN
    CREATE ROLE compass_role LOGIN PASSWORD 'postgres';
EXCEPTION WHEN DUPLICATE_OBJECT THEN
    NULL;
END $$;

-- ============================================================================
-- AUTH SERVICE PERMISSIONS
-- ============================================================================
-- Auth service can SELECT all columns but UPDATE only auth-owned fields

GRANT CONNECT ON DATABASE auth_service_db5 TO auth_role;
GRANT USAGE ON SCHEMA public TO auth_role;

-- SELECT all columns
GRANT SELECT ON journies_usermodel TO auth_role;

-- UPDATE only auth-owned columns
GRANT UPDATE (
    email,
    password,
    is_active,
    last_login,
    is_email_verified,
    email_verification_token,
    email_verification_sent_at,
    password_reset_token,
    password_reset_sent_at,
    failed_login_attempts,
    locked_until,
    last_failed_login,
    terms_accepted,
    is_deleted,
    deleted_at
) ON journies_usermodel TO auth_role;

-- ============================================================================
-- COMPASS SERVICE PERMISSIONS
-- ============================================================================
-- Compass service can SELECT all columns but UPDATE only compass-owned fields

GRANT CONNECT ON DATABASE auth_service_db5 TO compass_role;
GRANT USAGE ON SCHEMA public TO compass_role;

-- SELECT all columns
GRANT SELECT ON journies_usermodel TO compass_role;

-- UPDATE only compass-owned columns
GRANT UPDATE (
    first_name,
    last_name,
    full_name,
    phone_number
) ON journies_usermodel TO compass_role;

-- ============================================================================
-- AUDIT LOG PERMISSIONS
-- ============================================================================
-- Both services can INSERT audit logs

GRANT INSERT ON journies_auditlog TO auth_role;
GRANT INSERT ON journies_auditlog TO compass_role;

-- ============================================================================
-- REFRESH TOKEN PERMISSIONS
-- ============================================================================
-- Auth service manages refresh tokens

GRANT SELECT, INSERT, UPDATE ON journies_refreshtoken TO auth_role;
GRANT SELECT, INSERT, UPDATE ON journies_token_blacklist TO auth_role;

-- ============================================================================
-- TENANT PERMISSIONS
-- ============================================================================
-- Both services can read tenant data

GRANT SELECT ON journies_tenant TO auth_role;
GRANT SELECT ON journies_tenant TO compass_role;

-- ============================================================================
-- DJANGO SYSTEM TABLES
-- ============================================================================
-- Required for migrations and Django ORM

GRANT SELECT, INSERT, UPDATE, DELETE ON django_migrations TO auth_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON django_content_type TO auth_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_permission TO auth_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON django_session TO auth_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON django_migrations TO compass_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON django_content_type TO compass_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_permission TO compass_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON django_session TO compass_role;

-- ============================================================================
-- SEQUENCE PERMISSIONS
-- ============================================================================
-- Required for auto-increment fields

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO auth_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO compass_role;

