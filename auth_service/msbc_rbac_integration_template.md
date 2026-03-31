# `msbc_rbac` Integration Guide — Template for Journies Services

> **Document type**: Engineering Template  
> **Written from**: `journies-login-ms` (auth_service) integration  
> **Applicable to**: All Journies microservices (auth, booking, inventory, reporting, …)  
> **Package version**: `msbc_rbac-0.0.14`  
> **Last updated**: 2026-03-31

---

## Purpose

This document is the authoritative step-by-step guide for integrating the centralised
`msbc_rbac` Python package into any Django microservice in the Journies ecosystem.
Follow these steps in order. Each section is a discrete, verifiable step.

---

## Conceptual Overview Before You Begin

The RBAC system introduces **two databases** and **two separate "tenant" definitions**
that must never be confused:

| Term | Model | Database | Meaning |
|---|---|---|---|
| **Journies Tenant** | `<service>_app.Tenant` | Service DB (e.g. `auth_service`) | Your domain entity — hotels, companies, etc. |
| **RBAC Tenant** | `core.Tenant` | `rbac_project` DB | The RBAC-level administrative record for the **entire journies service** |

> [!IMPORTANT]
> Journies Tenant ≠ RBAC Tenant. They are completely separate concepts in separate databases.
> All five+ journies microservices together form **ONE** `core.Tenant` entry in `rbac_project`
> named `"Journies Global Project"`. Individual domain tenants (hotels, companies) have
> **zero bearing on RBAC configuration**.

The RBAC system manages **many applications** (journies, CRM, etc.). Each application
registers as a single `core.Tenant`. Within that tenant, roles and API-level permissions
are configured centrally.

### Cross-DB User ↔ Role Link

The service's `UserModel` and the RBAC system's `accounts.UserRole` are linked by
two stable identifiers that exist in both databases:

| Journies side | RBAC side | Type | Purpose |
|---|---|---|---|
| `UserModel.id` (UUID) | `accounts.User.username` | UUID as string | Stable cross-DB user identity |
| `UserModel.role_id` (int) | `admin_role.Role.id` (int) | Same integer PK | Role assignment link |

The `post_save` signal writes both `accounts.User` and `accounts.UserRole`
automatically whenever a `UserModel` is saved with a `role_id` set.
This eliminates the need for manual role assignment in most cases.


---

## Step 1: Prerequisites

Before starting, confirm the following:

- [ ] Python 3.10+ environment active
- [ ] Django 4.x project running
- [ ] PostgreSQL reachable at `localhost:5432` (or your host)
- [ ] Two PostgreSQL databases exist:
  - `<service_name>` — your service's own DB (e.g. `auth_service`)
  - `rbac_project` — shared RBAC DB (one instance for all journies services)
- [ ] `rbac_project` DB has been previously initialised by another service OR this is the first service (in which case `init_rbac` creates it)
- [ ] The `msbc_rbac-0.0.14-py3-none-any.whl` wheel file is accessible

---

## Step 2: Install the Package

Copy the wheel to your environment and install it, bypassing any cached versions:

```bash
pip install /path/to/msbc_rbac-0.0.14-py3-none-any.whl --force-reinstall
```

Add to `requirements.txt` or equivalent:

```
# Local wheel — update path per deployment environment
msbc_rbac @ file:///path/to/msbc_rbac-0.0.14-py3-none-any.whl
```

---

## Step 3: Environment Variables (`.env`)

Add both database connection blocks. The RBAC DB uses the same postgres credentials
as your service DB (different database name only):

```ini
# ── Your service database ─────────────────────────────────────────────────
DB_NAME=your_service_db        # e.g. auth_service
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# ── RBAC database (shared across all journies services) ───────────────────
RBAC_DB_NAME=rbac_project
RBAC_DB_USER=postgres
RBAC_DB_PASSWORD=your_password
RBAC_DB_HOST=localhost
RBAC_DB_PORT=5432

# ── RBAC package settings ────────────────────────────────────────────────
# Do NOT set TENANT_MODEL — the package hard-codes it to 'core.Tenant'
PROJECT_SCOPE=accounts         # used as a related_name prefix in accounts models
```

> [!CAUTION]
> Do **not** set `TENANT_MODEL` in `.env` or `settings.py`. The package hard-codes
> `settings.TENANT_MODEL = 'core.Tenant'` at import time. Overriding it cross-wires
> FK bindings and crashes permission resolution.

---

## Step 4: `settings.py` — Full Configuration

### 4A. Installed Apps

```python
INSTALLED_APPS = [
    # Django builtins
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'corsheaders',

    # Your service app
    'your_service_app',          # e.g. 'auth_app'

    # RBAC package — both sub-apps required
    'msbc_rbac.accounts',
    'msbc_rbac.core',
]
```

### 4B. Middleware Order

> [!IMPORTANT]
> Order is critical. Each middleware depends on the one above it having run first.

```python
MIDDLEWARE = [
    # 1. Network / security baseline
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',

    # 2. Identity — extracts user from JWT, sets request.user
    'your_service.middleware.jwt_auth.JWTAuthenticationMiddleware',

    # 3. Business tenant context — reads 'tid' from JWT, sets request.tenant
    #    (your service's own middleware for domain-level multi-tenancy)
    'your_service.middleware.tenant_context.TenantContextMiddleware',

    # 4. RBAC tenant context — stores request.user.tenant in thread-local
    'msbc_rbac.core.middleware.CurrentTenantMiddleware',

    # 5. RBAC enforcement — the permission gate
    'msbc_rbac.core.services.RBACMiddleware.RBACMiddleware',

    # 6. Error formatting — converts RBAC exceptions to structured JSON
    'msbc_rbac.core.exception_middleware.JSONExceptionMiddleware',

    # Django session/auth (position after RBAC is fine)
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]
```

### 4C. Dual Database Configuration

```python
from decouple import config

DATABASES = {
    # ── Your service DB: owns all domain tables ───────────────────────────
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     config('DB_NAME'),
        'USER':     config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST':     config('DB_HOST'),
        'PORT':     config('DB_PORT'),
    },

    # ── RBAC DB: owns all msbc_rbac tables ───────────────────────────────
    # Never create domain tables here. Never create RBAC tables in 'default'.
    'rbac': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     config('RBAC_DB_NAME',     default='rbac_project'),
        'USER':     config('RBAC_DB_USER',     default=config('DB_USER')),
        'PASSWORD': config('RBAC_DB_PASSWORD', default=config('DB_PASSWORD')),
        'HOST':     config('RBAC_DB_HOST',     default=config('DB_HOST')),
        'PORT':     config('RBAC_DB_PORT',     default=config('DB_PORT')),
    },
}

# The router enforces which models migrate to which database
DATABASE_ROUTERS = ['your_service.db_router.RBACDatabaseRouter']
```

### 4D. Bypass Paths

```python
# Paths that skip BOTH JWT validation AND RBAC enforcement
JWT_PUBLIC_PATHS = [
    '/api/v1/your-service/login/',
    '/api/v1/your-service/signup/',
    '/.well-known/jwks.json',
    '/health/',
    '/swagger/',
    '/redoc/',
    '/static/',
    '/admin/',
]
BYPASS_PATH_PREFIXES = JWT_PUBLIC_PATHS   # RBACMiddleware reads this
```

> [!NOTE]
> Keep `BYPASS_PATH_PREFIXES` minimal. Every path listed here bypasses all permission checks.
> Never add business API paths to this list.

### 4E. DRF Exception Handler

```python
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'msbc_rbac.core.drf_exception_handler.custom_exception_handler',
    # ... rest of your DRF config
}
```

---

## Step 5: Create the Database Router

Create `your_service/db_router.py` (at the same level as `settings.py`):

```python
"""
db_router.py

Routes msbc_rbac.core and msbc_rbac.accounts models to the 'rbac' database.
Routes all service-native models to the 'default' database.

This prevents `python manage.py migrate` from ever creating RBAC tables in
your service DB, and prevents domain tables from appearing in rbac_project.
"""

RBAC_APP_LABELS = frozenset({'core', 'accounts'})


class RBACDatabaseRouter:

    def db_for_read(self, model, **hints):
        return 'rbac' if model._meta.app_label in RBAC_APP_LABELS else 'default'

    def db_for_write(self, model, **hints):
        return 'rbac' if model._meta.app_label in RBAC_APP_LABELS else 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # Permit loose UUID-based cross-DB references (no DB-level FK constraint)
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in RBAC_APP_LABELS:
            return db == 'rbac'
        return db == 'default'
```

Register it in `settings.py`:

```python
DATABASE_ROUTERS = ['your_service.db_router.RBACDatabaseRouter']
```

---

## Step 6: Create the User Sync Signal

The RBAC database needs to know about users from your service so that RBAC
administrators can assign roles to them. A one-way sync signal handles this.

Create `your_service_app/signals.py`:

```python
"""
signals.py — One-way sync: domain UserModel → accounts.User (rbac DB)

The sync mirrors only identity fields (UUID as username, email, name, active status).
Passwords, tokens, and all domain data stay in your service DB.
All synced users are placed under 'Journies Global Project' in rbac.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_RBAC_GLOBAL_TENANT_NAME = 'Journies Global Project'
_rbac_global_tenant_cache = None


def _get_rbac_global_tenant():
    global _rbac_global_tenant_cache
    if _rbac_global_tenant_cache is not None:
        return _rbac_global_tenant_cache
    try:
        from msbc_rbac.core.models import Tenant as RBACTenant
        tenant = RBACTenant.objects.using('rbac').filter(
            name=_RBAC_GLOBAL_TENANT_NAME
        ).first()
        if tenant:
            _rbac_global_tenant_cache = tenant
        else:
            logger.warning(
                f"[RBAC Sync] '{_RBAC_GLOBAL_TENANT_NAME}' not found in rbac DB. "
                "Run: python manage.py init_rbac"
            )
        return tenant
    except Exception as exc:
        logger.error(f"[RBAC Sync] Could not query rbac DB: {exc}", exc_info=True)
        return None


def _bust_rbac_tenant_cache():
    global _rbac_global_tenant_cache
    _rbac_global_tenant_cache = None


def sync_user_to_rbac(sender, instance, created, **kwargs):
    """
    Mirror UserModel to accounts.User + accounts.UserRole in rbac DB.

    Identity link: str(instance.id) → accounts.User.username
    Role link:     instance.role_id  → admin_role.Role.id (same integer PK)
    """
    try:
        from msbc_rbac.accounts.models import User as RBACUser, UserRole
        from msbc_rbac.core.models import Role as RBACRole

        rbac_tenant = _get_rbac_global_tenant()
        if rbac_tenant is None:
            return   # init_rbac hasn't run yet — skip gracefully

        clean_email = (
            instance.email.split('#')[0] if '#' in instance.email else instance.email
        )
        is_active = instance.is_active and not instance.is_deleted

        rbac_user, rbac_created = RBACUser.objects.using('rbac').update_or_create(
            username=str(instance.id),
            defaults={
                'email': clean_email,
                'first_name': getattr(instance, 'first_name', '') or '',
                'last_name':  getattr(instance, 'last_name', '')  or '',
                'is_active':  is_active,
                'tenant':     rbac_tenant,
            },
        )
        if rbac_created:
            rbac_user.set_unusable_password()
            rbac_user.save(using='rbac', update_fields=['password'])

        logger.info(
            f"[RBAC Sync] {'Created' if rbac_created else 'Updated'} "
            f"accounts.User for {clean_email}"
        )

        # Sync role assignment if role_id is set
        # UserModel.role_id carries the same integer PK as admin_role.Role.id
        if instance.role_id:
            try:
                rbac_role = RBACRole.objects.using('rbac').get(
                    pk=instance.role_id, tenant=rbac_tenant
                )
                existing = UserRole.objects.using('rbac').filter(user=rbac_user).first()
                if existing:
                    if existing.role_id != instance.role_id:
                        existing.role = rbac_role
                        existing.tenant = rbac_tenant
                        existing.save(using='rbac', update_fields=['role', 'tenant'])
                else:
                    UserRole.objects.using('rbac').create(
                        user=rbac_user, role=rbac_role, tenant=rbac_tenant
                    )
                logger.info(f"[RBAC Sync] UserRole: {rbac_user.username} → {rbac_role.name}")
            except RBACRole.DoesNotExist:
                logger.warning(
                    f"[RBAC Sync] admin_role.Role pk={instance.role_id} not found. "
                    "Run 'init_rbac' then re-save the user."
                )

    except Exception as exc:
        logger.error(
            f"[RBAC Sync] Failed to sync user {instance.id}: {exc}", exc_info=True
        )


def register_signals():
    from your_service_app.models import YourUserModel   # replace with actual model
    post_save.connect(sync_user_to_rbac, sender=YourUserModel)
    logger.debug("[RBAC Sync] UserModel.post_save signal registered.")
```

---

## Step 7: Wire Signals in `apps.py`

Update your app's `apps.py`:

```python
from django.apps import AppConfig


class YourServiceAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'your_service_app'

    def ready(self):
        from your_service_app.signals import register_signals
        register_signals()
```

Ensure your `__init__.py` references the config:

```python
# your_service_app/__init__.py
default_app_config = 'your_service_app.apps.YourServiceAppConfig'
```

---

## Step 8: Run Migrations (Both Databases)

> [!CAUTION]
> Never run `migrate` without `--database` after adding the router.
> Each database must be migrated independently.

```bash
# 1. Generate RBAC migrations (first time only — creates migration files in package)
python manage.py makemigrations core accounts

# 2. Apply your service migrations to the service DB
python manage.py migrate --database=default

# 3. Apply RBAC migrations to the rbac_project DB
python manage.py migrate --database=rbac

# 4. Verify: check there are no RBAC tables in your service DB
python manage.py cleanup_journies_db --dry-run
```

---

## Step 9: Clean Up Orphaned Tables (One-Time)

If you applied migrations before the router was in place, RBAC tables may exist
in your service DB. Remove them:

```bash
# Preview what will be removed (safe — no changes)
python manage.py cleanup_journies_db --dry-run

# Drop with confirmation prompt
python manage.py cleanup_journies_db

# Drop without prompt (CI/CD)
python manage.py cleanup_journies_db --force
```

The command drops all `accounts_*`, `admin_*`, and `tenant` tables from
the `default` database and cleans orphaned `django_migrations` records.

---

## Step 10: Seed the RBAC Tenant and Baseline Roles

Run once per environment (dev, staging, production):

```bash
python manage.py init_rbac
```

This creates in `rbac_project`:
- `core.Tenant` → `"Journies Global Project"` (the one RBAC tenant for all of journies)
- `admin_role` → `owner`, `regional_manager`, `general_manager`, `department_head`, `team_member`

If `"Journies Global Project"` already exists (created by another journies service),
the command is idempotent — it only creates what is missing.

> [!NOTE]
> Run `init_rbac` **before starting your service** for the first time in each
> environment. The user sync signal depends on `'Journies Global Project'` existing
> in the rbac DB — it skips gracefully if absent but logs a warning until it is created.

---

## Step 11: Register Your API Endpoints in RBAC

Every protected API endpoint must be registered in `rbac_project` before requests
can pass through `RBACMiddleware` (step 3: "API must be registered").

Use the `seed_rbac_demo` command for development/test environments:

```bash
python manage.py seed_rbac_demo          # creates module + endpoints + permissions
python manage.py seed_rbac_demo --flush  # recreate (drops and rebuilds)
```

For **production**, register endpoints via Django admin on `rbac_project` or via
a service-specific seeding command:

```
rbac_project Django Admin → Admin Api Details → Add
  Path       : /api/v1/your-endpoint     (no trailing slash)
  Module     : AUTH (or your module code)
  Submodule  : (leave blank if top-level)

rbac_project Django Admin → Admin Api Operations → Add
  Endpoint   : /api/v1/your-endpoint
  Http method: GET
  Is enabled : ✓
  Permission code: read
```

> [!IMPORTANT]
> `resolve_api_operation()` strips the trailing slash before matching. Always
> register paths WITHOUT a trailing slash (e.g. `/api/v1/users`, not `/api/v1/users/`).

---

## Step 12: Assign Users to Roles

Role assignment is **automatic** when done through your service.

When `UserModel.role_id` is set (by Compass or your domain service) and the user is saved,
the `post_save` signal automatically creates or updates `accounts.UserRole` in the rbac DB
using `role_id` as the direct FK to `admin_role.Role`.

```
UserModel.role_id = 1     →  accounts.UserRole.role_id = 1  (owner)
UserModel.role_id = 3     →  accounts.UserRole updated        (general_manager)
UserModel.role_id = None  →  no accounts.UserRole created
```

If you need to manually assign in **production** (e.g. seeding, data repair):

Via Django admin on `rbac_project`:
```
Admin → Accounts User Roles → Add
  User   : <UUID of the journies user>  (stored as username in accounts.User)
  Role   : owner (id=1, or appropriate role)
  Tenant : Journies Global Project
```

Via psql (direct):
```sql
INSERT INTO accounts_userrole (user_id, role_id, tenant_id)
SELECT id, 1, (SELECT id FROM tenant WHERE name = 'Journies Global Project')
FROM accounts_user
WHERE username = '<journies-user-uuid-as-string>'
ON CONFLICT DO NOTHING;
```

> [!NOTE]
> `accounts.UserRole.user_id` stores the `accounts.User.id` (Django integer PK), NOT the
> journies UUID directly. The journies UUID is stored in `accounts.User.username`.
> The signal handles this lookup automatically.


---

## Step 13: Verify the Integration

### 13A. Database Cleanliness

```bash
# Confirm your service DB has NO RBAC tables
python manage.py cleanup_journies_db --dry-run
# Expected: "✓ auth_service DB is clean"

# Confirm tables are in the right databases
python manage.py dbshell --database=default
\dt                   # should show only your service's tables

python manage.py dbshell --database=rbac
\dt                   # should show admin_*, accounts_*, tenant — NO service tables
```

### 13B. User Sync

```bash
python manage.py shell
>>> from your_service_app.models import YourUserModel
>>> from msbc_rbac.accounts.models import User as RBACUser
>>> u = YourUserModel.objects.first()
>>> RBACUser.objects.using('rbac').filter(username=str(u.id)).first()
# Expected: <User: <UUID>>
```

### 13C. Manual Postman Tests

**Test 1 — Public bypass** (login path must NOT be blocked by RBAC):
```
POST /api/v1/your-service/login/
Body: {"email": "test@test.com", "password": "wrong"}
Expected: 400 (bad credentials from view, NOT 401 from RBAC)
```

**Test 2 — JWT enforcement** (no token → 401 from JWT middleware):
```
GET /api/v1/your-service/users/
Headers: (none)
Expected: 401
Body must NOT contain "User is not authorized" (that's the RBAC message)
```

**Test 3 — RBAC step-3 denial** (valid JWT + no ApiOperation → 401 from RBAC):
```
GET /api/v1/your-service/users/
Headers: Authorization: Bearer <valid_token>
(with no ApiOperation registered for this path in rbac_project)
Expected: 401, body: {"success": false, "message": "User is not authorized"}
```

**Test 4 — Authorized pass-through** (full RBAC graph + assigned role → 200):
```
GET /api/v1/your-service/users/
Headers: Authorization: Bearer <valid_token>
(ApiOperation registered, user has owner role, TenantModule enabled)
Expected: 200 OK (or 400 if view needs more data — NOT a RBAC 401)
```

### 13D. Automated Tests

```bash
# All integration/unit tests for RBAC integration
python manage.py test your_service_app.tests -v 2

# Unit tests only (fast, no rbac DB required for router/middleware logic)
python manage.py test your_service_app.tests.unit.test_rbac_middleware

# Integration tests (requires both DB connections)
python manage.py test your_service_app.tests.integration.test_rbac_integration
```

---

## Step 14: RBAC Debugging Checklist

When a request returns RBAC 401 unexpectedly, work through this checklist:

```sql
-- Connect to rbac_project DB
-- Step 3: Is there an ApiOperation for this path + method?
SELECT ao.id, ae.path, ao.http_method, ao.is_enabled
FROM admin_api_operation ao
JOIN admin_api_details ae ON ae.id = ao.endpoint_id
WHERE ae.path = '/api/v1/your-endpoint'   -- no trailing slash
  AND ao.http_method = 'GET';

-- Step 4: Is is_enabled = TRUE on the ApiOperation? (checked above)

-- Step 5: Is there a TenantModule subscription?
SELECT tm.*, m.code, m.name
FROM admin_tenant_module tm
JOIN admin_module m ON m.code = tm.module_id
WHERE tm.tenant_id = <tenant_id>
  AND tm.is_enabled = TRUE;

-- Step 6: Is there a TenantApiOverride blocking the operation?
SELECT * FROM admin_tenant_api_operation
WHERE tenant_id = <tenant_id>
  AND api_operation_id = <operation_id>
  AND is_enabled = FALSE;

-- Step 7: Is the user blocked at the API level?
SELECT * FROM accounts_userapiblock
WHERE user_id = '<user-uuid>'::uuid;

-- Steps 8-9: Does the user's role have the correct permission?
SELECT u.user_id, r.name as role, p.code as permission, rpm.allowed
FROM accounts_userrole u
JOIN admin_role r ON r.id = u.role_id
JOIN admin_role_permission_mapping rpm ON rpm.role_id = r.id
JOIN admin_permission p ON p.id = rpm.permission_id
WHERE u.user_id = '<user-uuid>'::uuid
  AND p.code = 'read';   -- or the relevant action code
```

---

## Appendix A: File Checklist

| File | Action | Notes |
|---|---|---|
| `.env` | **Modify** | Add `RBAC_DB_*` variables |
| `settings.py` | **Modify** | `INSTALLED_APPS`, `MIDDLEWARE`, dual `DATABASES`, `DATABASE_ROUTERS`, `BYPASS_PATH_PREFIXES` |
| `<service>/db_router.py` | **Create** | `RBACDatabaseRouter` class |
| `<service_app>/signals.py` | **Create** | `sync_user_to_rbac` + `register_signals` |
| `<service_app>/apps.py` | **Modify** | `ready()` calls `register_signals()` |
| `<service_app>/management/commands/init_rbac.py` | **Create** | Seeds global tenant + 5 roles (idempotent) |
| `<service_app>/management/commands/seed_rbac_demo.py` | **Create** | Dev/test data: module, endpoints, permissions |
| `<service_app>/management/commands/cleanup_db.py` | **Create** | Drops orphaned RBAC tables from service DB |
| `<service_app>/tests/fixtures/rbac_test_data.py` | **Create** | Test helpers |
| `<service_app>/tests/unit/test_rbac_middleware.py` | **Create** | Unit tests (mocked) |
| `<service_app>/tests/integration/test_rbac_integration.py` | **Create** | Integration tests |

---

## Appendix B: What Belongs in Each Database

| Table | Database | Owned By |
|---|---|---|
| `<service>_tenant` | Service DB (`default`) | Your service |
| `<service>_usermodel` | Service DB (`default`) | Your service |
| `<service>_*` (all domain tables) | Service DB (`default`) | Your service |
| `tenant` (`core.Tenant`) | `rbac_project` (`rbac`) | `msbc_rbac.core` |
| `admin_role` | `rbac_project` | `msbc_rbac.core` |
| `admin_module` | `rbac_project` | `msbc_rbac.core` |
| `admin_permission` | `rbac_project` | `msbc_rbac.core` |
| `admin_api_details` | `rbac_project` | `msbc_rbac.core` |
| `admin_api_operation` | `rbac_project` | `msbc_rbac.core` |
| `admin_tenant_module` | `rbac_project` | `msbc_rbac.core` |
| `admin_role_permission_mapping` | `rbac_project` | `msbc_rbac.core` |
| `admin_tenant_api_operation` | `rbac_project` | `msbc_rbac.core` |
| `accounts_user` | `rbac_project` | `msbc_rbac.accounts` |
| `accounts_userrole` | `rbac_project` | `msbc_rbac.accounts` |
| `accounts_userapiblock` | `rbac_project` | `msbc_rbac.accounts` |

---

## Appendix C: Request Flow Reference

```
Request arrives
│
├─ path in BYPASS_PATH_PREFIXES?
│     YES → skip all middleware → view ✓
│
├─ JWTAuthenticationMiddleware
│     invalid/missing token → 401
│     valid → sets request.user
│
├─ TenantContextMiddleware (your service)
│     reads 'tid' from JWT → sets request.tenant (business tenant context)
│
├─ CurrentTenantMiddleware (msbc_rbac)
│     stores request.user.tenant in thread-local
│
└─ RBACMiddleware (msbc_rbac)
      Step 3: resolve_api_operation(request) → no match → 401
      Step 4: operation.is_enabled = False → 401
      Step 5: TenantModule subscription missing/disabled/expired → 401
      Step 6: TenantApiOverride blocks operation → 401
      Step 7: UserApiBlock for this user → 401
      Step 8: resolve action code from HTTP method
      Step 9: has_permission(user_permissions, module, action) → allow → view ✓
                                                                → deny → 401
```

---

## Appendix D: Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `TENANT_MODEL` set in `.env` | RBAC FK resolution crashes on startup | Remove it entirely |
| Ran `migrate` without `--database` | RBAC tables appear in service DB | Run `cleanup_db --force` then re-migrate per DB |
| Trailing slash in `ApiEndpoint.path` | All requests get step-3 401 | Re-register paths without trailing slash |
| `init_rbac` not run before first request | User sync silently skips | Run `init_rbac`, then resave affected users |
| `BYPASS_PATH_PREFIXES` not set | Server crashes on startup (`AttributeError`) | Add `BYPASS_PATH_PREFIXES` list to `settings.py` |
| Wrong middleware order | RBAC runs before JWT auth, `request.user` is Anonymous | Follow the exact middleware order in Step 4B |
| `role_id` set before `init_rbac` | UserRole not created, warning logged | Run `init_rbac` first, then trigger a re-save of the user |
| `role_id` value doesn't match any admin_role.id | UserRole not created, warning logged | Verify role IDs match between journies and RBAC; roles are seeded by `init_rbac` |

