# RBAC Testing Guide — `auth_service`

> **Version**: 2.0 — Expanded with automated test suite  
> **Package**: `msbc_rbac`  

---

## Overview

This guide provides a complete testing strategy for the `msbc_rbac` integration. It combines:

- **Automated unit tests** — fast, isolated, no live DB required for router/middleware logic
- **Automated integration tests** — full stack tests against real test databases
- **Manual Postman/Swagger tests** — for visual confirmation and exploratory testing

---

## Running the Automated Tests

```bash
# All RBAC tests
python manage.py test auth_app.tests

# Unit tests only (fast, no rbac DB needed for router tests)
python manage.py test auth_app.tests.unit.test_rbac_middleware

# Integration tests only (requires both DB connections)
python manage.py test auth_app.tests.integration.test_rbac_integration

# Verbose output
python manage.py test auth_app.tests -v 2

# Keep test databases between runs (faster on re-runs)
python manage.py test auth_app.tests --keepdb
```

> [!IMPORTANT]
> Integration tests create isolated `test_auth_service` and `test_rbac_project` databases automatically. Both PostgreSQL connections must be reachable. Ensure your `.env` has both `DB_*` and `RBAC_DB_*` variables set correctly.

---

## Automated Test Coverage

### Unit Tests (`test_rbac_middleware.py`)

| Test Class | Tests | What it verifies |
|---|---|---|
| `TestRBACDatabaseRouter` | 15 | Router correctly routes reads, writes, migrations, and relations per DB |
| `TestBypassPathPrefixes` | 7 | All public paths are in BYPASS prefixes; BYPASS ⊇ JWT_PUBLIC_PATHS |
| `TestRBACMiddlewareBehaviourMocked` | 6 | Middleware decision tree (bypass → anon → unregistered → disabled → blocked → authorized) |
| `TestSignalRegistration` | 1 | post_save signal for UserModel is wired up |

### Integration Tests (`test_rbac_integration.py`)

| Test Class | Tests | What it verifies |
|---|---|---|
| `TestPublicBypass` | 5 | Login/signup/health/swagger/jwks bypass RBAC |
| `TestJWTEnforcement` | 2 | No token or invalid token → 401 from JWT middleware (before RBAC) |
| `TestRBACStep3Denial` | 1 | Valid JWT + no ApiOperation → 401 from RBACMiddleware (step 3 denial) confirms middleware is wired |
| `TestDatabaseSeparation` | 7 | DB Router correctness; no RBAC tables pollute the journies database |
| `TestUserSync` | 9 | Identity fields sync to the global rbac tenant; setting `role_id` assigns the user to the matching RBAC `Role` |

**Total Integration Tests: 24**

> [!NOTE]
> Testing the actual permission resolution (Roles → Permissions → API Enforcements) is the sole responsibility of the RBAC service's own test suite. The `auth_service` test suite stops at verifying the middleware stack is installed, the databases are strictly separated, and the 1-way user identity sync operates.

## Manual Verification Tests (Postman / Swagger)

### Test 1: Public Bypass Endpoints

**Verify**: `RBACMiddleware` correctly ignores endpoints in `BYPASS_PATH_PREFIXES`.

```
POST /api/v1/users/login/
Body: {"email": "test@test.com", "password": "wrong"}
Headers: (none)
```

| ✓ Pass | ✗ Fail |
|---|---|
| Returns `400 Bad Request` (wrong credentials) or `200 OK` | Returns `401` with `"User is not authorized"` in the body |

Also test: `GET /health/` → `200 OK`, `GET /swagger/` → HTML page loaded.

---

### Test 2: Unauthenticated Access to Protected Endpoint

**Verify**: Missing JWT triggers `JWTAuthenticationMiddleware`, not RBAC.

```
GET /api/v1/users/
Headers: (none)
```

| ✓ Pass | ✗ Fail |
|---|---|
| Returns `401` with `{"detail": "Missing or invalid token"}` | Returns `403` or `401` with RBAC-formatted body |

---

### Test 3: Authenticated — No RBAC Mapping

**Verify**: Valid JWT but no `ApiOperation` in the rbac DB → step 3 deny.

```bash
# Step 1 — Get a token
POST /api/v1/users/login/
Body: {"email": "user@hotel.com", "password": "..."}

# Step 2 — Use token on protected endpoint (no ApiOperation configured yet)
GET /api/v1/users/
Headers: Authorization: Bearer <token>
```

| ✓ Pass | ✗ Fail |
|---|---|
| Returns `401` with `{"success": false, "message": "User is not authorized"}` | Request passes through to view (no RBAC guard active) |

---

### Test 4: Full Authorisation Pass-Through

**Verify**: Complete RBAC object graph → request reaches view (200 OK).

#### Setup in Django Admin or psql (rbac_project DB):

```sql
-- 1. Ensure the global tenant exists (seeded by init_rbac)
SELECT id FROM tenant WHERE name = 'Journies Global Project';

-- 2. Confirm or create the AUTH Module
INSERT INTO admin_module (code, name, icon, "order")
VALUES ('AUTH', 'Authentication', '', 1)
ON CONFLICT DO NOTHING;

-- 3. Create an ApiEndpoint (NO trailing slash)
INSERT INTO admin_api_details (path, module_id, submodule_id)
VALUES ('/api/v1/users', 'AUTH', NULL);

-- 4. Create ApiOperation for GET
INSERT INTO admin_api_operation (endpoint_id, http_method, is_enabled, permission_code)
VALUES (<endpoint_id>, 'GET', TRUE, 'read');

-- 5. Create Permission
INSERT INTO admin_permission (tenant_id, module_id, submodule_id, code, is_active)
VALUES (<global_tenant_id>, 'AUTH', NULL, 'read', TRUE);

-- 6. Map Role → Permission (Roles are seeded by init_rbac)
INSERT INTO admin_role_permission_mapping (role_id, permission_id, allowed)
VALUES (1, <permission_id>, TRUE); -- 1 = owner

-- 7. Subscribe the tenant to the module
INSERT INTO admin_tenant_module (tenant_id, module_id, submodule_id, is_enabled)
VALUES (<global_tenant_id>, 'AUTH', NULL, TRUE);

-- 8. Assure user is assigned to 'owner' role (usually automatic via post_save sync)
INSERT INTO accounts_userrole (user_id, role_id, tenant_id)
VALUES ('<your_user_uuid>', 1, <global_tenant_id>)
ON CONFLICT DO NOTHING;
```

#### Fire the request:

```
GET /api/v1/users/
Headers: Authorization: Bearer <valid_token>
```

| ✓ Pass | ✗ Fail |
|---|---|
| Returns `200 OK` with user list data | Returns `401` — check each RBAC step in sequence below |

---

## RBAC Debugging Checklist

When a request returns an unexpected `401`, work through this checklist against the `rbac_project` DB:

```
Step 3: Does an ApiOperation row exist for this exact path + HTTP method?
    SELECT * FROM admin_api_details WHERE path = '/api/v1/users/';
    SELECT * FROM admin_api_operation WHERE endpoint_id = <id> AND http_method = 'GET';

Step 4: Is is_enabled = TRUE on that ApiOperation?

Step 5: Does a TenantModule row exist for this tenant + module?
    SELECT * FROM admin_tenant_module WHERE tenant_id = <rbac_tenant_id>;
    Is is_enabled = TRUE and expiration_date NULL or in the future?

Step 6: Is there a TenantApiOverride blocking the operation?
    SELECT * FROM admin_tenant_api_operation WHERE tenant_id = <rbac_tenant_id>;

Step 7: Is there a UserApiBlock for this user?
    SELECT * FROM accounts_userapiblock WHERE user_id = '<user_uuid>';

Step 8/9: Does the user's role have the correct Permission linked via RolePermission?
    SELECT u.user_id, r.name as role, p.code as permission
    FROM accounts_userrole u
    JOIN admin_role r ON r.id = u.role_id
    JOIN admin_role_permission_mapping rpm ON rpm.role_id = r.id
    JOIN admin_permission p ON p.id = rpm.permission_id
    WHERE u.user_id = '<user_uuid>';
```

---

## Database Separation Verification

Run these after adding the router + cleanup command to confirm clean separation:

```bash
# Confirm no RBAC tables in journies DB
python manage.py cleanup_journies_db --dry-run
# Expected: "✓ auth_service DB is clean — no orphaned RBAC tables"

# List tables in journies DB (should only show journies_*)
python manage.py dbshell --database=default
\dt
# Expected: journies_tenant, journies_usermodel, journies_refreshtoken,
#           journies_token_blacklist, journies_auditlog, django_migrations,
#           django_content_type, django_session, auth_group, auth_permission

# List tables in rbac DB (should show accounts_*, admin_*, tenant)
python manage.py dbshell --database=rbac
\dt
# Expected: accounts_user, accounts_userrole, admin_module, admin_role,
#           admin_permission, tenant, etc. — NO journies_* tables
```

---

## Data Sync Verification

After creating a journies user with a `role_id`, verify they appear in the rbac DB with their role assigned to the `Journies Global Project` tenant:

```bash
python manage.py shell
>>> from auth_app.models.user_model import UserModel
>>> from msbc_rbac.accounts.models import User as RBACUser, UserRole

# 1. Take a user from the journies DB
>>> u = UserModel.objects.first()
>>> str(u.id)
'123e4567-e89b-12d3-a456-426614174000'
>>> u.role_id
1

# 2. Check the user exists in rbac DB
>>> rbac_u = RBACUser.objects.using('rbac').get(username=str(u.id))
>>> rbac_u.email
'testuser@hotel.com'

# 3. Check they are under the global tenant
>>> rbac_u.tenant.name
'Journies Global Project'

# 4. Check their role assignment synced
>>> role_assignment = UserRole.objects.using('rbac').get(user=rbac_u)
>>> role_assignment.role.name
'owner'
```

---

## CI/CD Integration

Add this block to your CI pipeline (`GitHub Actions` / `Azure DevOps`):

```yaml
# Run RBAC test suite
- name: Run RBAC integration tests
  env:
    DB_NAME: test_auth_service
    DB_USER: postgres
    DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
    RBAC_DB_NAME: test_rbac_project
    RBAC_DB_USER: postgres
    RBAC_DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
  run: |
    cd auth_service
    python manage.py test auth_app.tests --verbosity=2 --failfast
```

> [!TIP]
> Use `--keepdb` in local development to preserve test databases between runs and dramatically speed up test feedback cycles. Never use `--keepdb` in CI pipelines.
