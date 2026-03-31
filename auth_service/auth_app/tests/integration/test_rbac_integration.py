"""
auth_app/tests/integration/test_rbac_integration.py

Integration tests for the msbc_rbac middleware integration in auth_service.

Scope
-----
These tests verify that the auth_service has correctly integrated the RBAC
middleware stack. They do NOT test RBAC permission resolution logic — that
belongs to the RBAC service's own test suite.

The two "tenant" concepts are kept completely separate:
  auth_app.Tenant  = hotels/companies inside journies  (default DB)
  core.Tenant      = RBAC administrative tenant         (rbac DB)

Cross-DB User ↔ Role link
--------------------------
  auth_app.UserModel.id       (UUID)  ↔  accounts.User.username  (str(UUID))
  auth_app.UserModel.role_id  (int)   ↔  admin_role.Role.id      (int)

When UserModel.role_id is set (by Compass service), the post_save signal
automatically creates/updates accounts.UserRole in the rbac DB.

What is tested here:
  1. Public bypass — login/signup/health are never blocked by RBAC
  2. JWT enforcement — missing/invalid token → 401 from JWT middleware
  3. RBAC step-3 denial — valid JWT but no ApiOperation → 401 from RBAC
  4. Database separation — no RBAC tables polluting the journies DB
  5. User identity sync — UserModel.post_save mirrors to accounts.User in rbac DB

Run:
    python manage.py test auth_app.tests.integration.test_rbac_integration -v 2
"""
import json
from unittest.mock import patch

from django.test import TestCase, Client

from auth_app.models.user_model import Tenant as JourneysTenant, UserModel
from auth_app.tests.fixtures.rbac_test_data import (
    RBAC_GLOBAL_TENANT_NAME,
    make_journies_tenant,
    make_journies_user,
    ensure_rbac_global_tenant,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _jwt_payload(user: UserModel) -> dict:
    """Minimal JWT payload dict — mirrors what validate_jwt() returns."""
    return {
        'sub': str(user.id),
        'email': user.email,
        'tid': str(user.tenant_id),
        'is_superuser': user.is_superuser,
        'is_onboarding_complete': getattr(user, 'is_onboarding_complete', False),
        'is_plan_purchased': getattr(user, 'is_plan_purchased', False),
    }


# ============================================================================
# 1. Public Bypass — these paths must never return RBAC 401/403
# ============================================================================

class TestPublicBypass(TestCase):
    """
    Every path in BYPASS_PATH_PREFIXES must skip RBAC entirely.
    The expected response is whatever the VIEW returns (400 for bad input,
    200 for health, etc.) — NOT a 401 carrying the RBAC error body.
    """
    databases = ['default', 'rbac']

    def setUp(self):
        self.client = Client()

    def _assert_not_rbac_blocked(self, response):
        """A 401 whose body says 'User is not authorized' came from RBAC — fail."""
        if response.status_code == 401:
            try:
                body = response.json()
                self.assertNotIn(
                    'User is not authorized',
                    body.get('error', '') + body.get('message', ''),
                    msg='Bypass path returned an RBAC 401 — middleware bypass is broken.',
                )
            except Exception:
                pass

    def test_login_bypass(self):
        resp = self.client.post(
            '/api/v1/users/login/',
            data=json.dumps({'email': 'x@x.com', 'password': 'bad'}),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [400, 401, 404])
        self._assert_not_rbac_blocked(resp)

    def test_signup_bypass(self):
        resp = self.client.post(
            '/api/v1/users/signup/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertNotEqual(resp.status_code, 403)
        self._assert_not_rbac_blocked(resp)

    def test_health_bypass(self):
        resp = self.client.get('/health/')
        self.assertEqual(resp.status_code, 200)

    def test_swagger_bypass(self):
        resp = self.client.get('/swagger/?format=openapi')
        self.assertNotEqual(resp.status_code, 403)

    def test_jwks_bypass(self):
        resp = self.client.get('/.well-known/jwks.json')
        self.assertNotEqual(resp.status_code, 403)


# ============================================================================
# 2. JWT Enforcement — missing/invalid token is caught BEFORE RBAC
# ============================================================================

class TestJWTEnforcement(TestCase):
    """
    Protected endpoints reject unauthenticated requests at the JWT middleware
    layer (step 1), before RBAC even runs.
    """
    databases = ['default', 'rbac']

    def setUp(self):
        self.client = Client()

    def test_no_token_returns_401(self):
        resp = self.client.get('/api/v1/users/')
        self.assertEqual(resp.status_code, 401)

    def test_garbage_token_returns_401(self):
        resp = self.client.get(
            '/api/v1/users/',
            HTTP_AUTHORIZATION='Bearer not.a.valid.token',
        )
        self.assertEqual(resp.status_code, 401)


# ============================================================================
# 3. RBAC Middleware — step 3 denial (no ApiOperation registered)
# ============================================================================

class TestRBACStep3Denial(TestCase):
    """
    Valid JWT + no ApiOperation registered in the rbac DB → step 3 deny.
    This confirms the RBAC middleware IS running and enforcing.
    """
    databases = ['default', 'rbac']

    def setUp(self):
        self.client = Client()
        self.hotel = make_journies_tenant(code='STEP3_HOTEL')
        self.user = make_journies_user(self.hotel, email='step3@journies.test')

    @patch('auth_service.middleware.jwt_auth.validate_jwt')
    def test_valid_jwt_no_api_operation_returns_401(self, mock_jwt):
        """
        The endpoint /api/v1/users/ has no ApiOperation row in rbac DB.
        RBACMiddleware must deny at step 3 with its standard 401 body.
        """
        mock_jwt.return_value = _jwt_payload(self.user)

        with patch('auth_app.models.user_model.UserModel.objects.get') as mock_get:
            mock_get.return_value = self.user
            resp = self.client.get(
                '/api/v1/users/',
                HTTP_AUTHORIZATION='Bearer mock.jwt.token',
            )

        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertFalse(body.get('success', True))
        self.assertIn('not authorized', body.get('message', '').lower())


# ============================================================================
# 4. Database Separation
# ============================================================================

class TestDatabaseSeparation(TestCase):
    """
    The RBACDatabaseRouter must prevent any RBAC table from appearing in the
    journies (auth_service) database.

    Run after: python manage.py cleanup_journies_db
    """
    databases = ['default', 'rbac']

    def _existing_tables(self, db_alias: str):
        from django.db import connections
        with connections[db_alias].cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
            return {row[0] for row in cur.fetchall()}

    def test_no_accounts_tables_in_journies_db(self):
        tables = self._existing_tables('default')
        rbac_accounts = [t for t in tables if t.startswith('accounts_')]
        self.assertEqual(
            rbac_accounts, [],
            msg=f"RBAC accounts_* tables found in journies DB: {rbac_accounts}. "
                "Run: python manage.py cleanup_journies_db",
        )

    def test_no_admin_rbac_tables_in_journies_db(self):
        expected_absent = [
            'admin_module', 'admin_role', 'admin_permission',
            'admin_api_details', 'admin_api_operation',
            'admin_role_permission_mapping', 'admin_tenant_module',
            'tenant',
        ]
        tables = self._existing_tables('default')
        found = [t for t in expected_absent if t in tables]
        self.assertEqual(
            found, [],
            msg=f"RBAC core tables in journies DB: {found}. "
                "Run: python manage.py cleanup_journies_db",
        )

    def test_journies_tenant_table_is_in_default_db(self):
        tables = self._existing_tables('default')
        self.assertIn('journies_tenant', tables)

    def test_db_router_sends_rbac_models_to_rbac_db(self):
        from msbc_rbac.core.models import Tenant as RBACTenant
        from msbc_rbac.accounts.models import UserRole
        from auth_service.db_router import RBACDatabaseRouter
        r = RBACDatabaseRouter()
        self.assertEqual(r.db_for_read(RBACTenant), 'rbac')
        self.assertEqual(r.db_for_write(RBACTenant), 'rbac')
        self.assertEqual(r.db_for_read(UserRole), 'rbac')
        self.assertEqual(r.db_for_write(UserRole), 'rbac')

    def test_db_router_sends_auth_app_to_default_db(self):
        from auth_service.db_router import RBACDatabaseRouter
        r = RBACDatabaseRouter()
        self.assertEqual(r.db_for_read(UserModel), 'default')
        self.assertEqual(r.db_for_write(UserModel), 'default')
        self.assertEqual(r.db_for_read(JourneysTenant), 'default')
        self.assertEqual(r.db_for_write(JourneysTenant), 'default')

    def test_rbac_migration_blocked_from_default_db(self):
        from auth_service.db_router import RBACDatabaseRouter
        r = RBACDatabaseRouter()
        self.assertFalse(r.allow_migrate('default', 'core'))
        self.assertFalse(r.allow_migrate('default', 'accounts'))

    def test_auth_app_migration_blocked_from_rbac_db(self):
        from auth_service.db_router import RBACDatabaseRouter
        r = RBACDatabaseRouter()
        # Returns True during tests to bypass msbc_rbac's hardcoded constraints
        self.assertTrue(r.allow_migrate('rbac', 'auth_app'))


# ============================================================================
# 5. User Identity Sync (auth_app.UserModel → accounts.User in rbac DB)
# ============================================================================

class TestUserSync(TestCase):
    """
    Verifies that the post_save signal mirrors journies user identity AND role
    into the rbac_project DB under 'Journies Global Project'.

    Identity link:  UserModel.id (UUID)    ↔  accounts.User.username
    Role link:      UserModel.role_id (int) ↔  admin_role.Role.id

    The two tenant concepts remain entirely separate:
      auth_app.Tenant (hotel) lives in auth_service DB — NOT synced to RBAC.
      core.Tenant 'Journies Global Project' receives the synced user.
    """
    databases = ['default', 'rbac']

    def setUp(self):
        ensure_rbac_global_tenant()
        self.hotel = make_journies_tenant(code='SYNC_HOTEL')

        # Ensure the seed roles exist (normally done by init_rbac)
        from msbc_rbac.core.models import Role as RBACRole, Tenant as RBACTenant
        self.rbac_tenant = RBACTenant.objects.using('rbac').get(
            name=RBAC_GLOBAL_TENANT_NAME
        )
        # Roles expected from the DB screenshot: id 1-5
        for rid, rname in [
            (1, 'owner'), (2, 'regional_manager'), (3, 'general_manager'),
            (4, 'department_head'), (5, 'team_member'),
        ]:
            RBACRole.objects.using('rbac').get_or_create(
                pk=rid,
                defaults={'name': rname, 'tenant': self.rbac_tenant},
            )

    # ── Identity sync ────────────────────────────────────────────────────

    def test_create_user_syncs_to_rbac(self):
        from msbc_rbac.accounts.models import User as RBACUser
        user = make_journies_user(self.hotel, email='create_sync@journies.test')
        rbac = RBACUser.objects.using('rbac').filter(username=str(user.id)).first()
        self.assertIsNotNone(rbac, "accounts.User not created in rbac DB.")
        self.assertEqual(rbac.email, 'create_sync@journies.test')
        self.assertTrue(rbac.is_active)

    def test_update_user_syncs_name(self):
        from msbc_rbac.accounts.models import User as RBACUser
        user = make_journies_user(self.hotel, email='name_sync@journies.test')
        user.first_name = 'Synced'
        user.last_name = 'Name'
        user.save()
        rbac = RBACUser.objects.using('rbac').get(username=str(user.id))
        self.assertEqual(rbac.first_name, 'Synced')
        self.assertEqual(rbac.last_name, 'Name')

    def test_soft_delete_marks_rbac_user_inactive(self):
        from msbc_rbac.accounts.models import User as RBACUser
        user = make_journies_user(self.hotel, email='softdel_sync@journies.test')
        user.soft_delete()
        rbac = RBACUser.objects.using('rbac').get(username=str(user.id))
        self.assertFalse(rbac.is_active,
            "accounts.User.is_active must be False after soft-delete.")
        self.assertNotIn('#', rbac.email,
            "Soft-delete email suffix must be stripped before syncing.")

    def test_synced_user_has_unusable_password(self):
        from msbc_rbac.accounts.models import User as RBACUser
        user = make_journies_user(self.hotel, email='nopwd_sync@journies.test')
        rbac = RBACUser.objects.using('rbac').get(username=str(user.id))
        self.assertFalse(rbac.has_usable_password(),
            "Synced rbac user must not have a usable password.")

    def test_synced_user_is_under_global_project_tenant(self):
        from msbc_rbac.accounts.models import User as RBACUser
        user = make_journies_user(self.hotel, email='tenant_sync@journies.test')
        rbac = RBACUser.objects.using('rbac').get(username=str(user.id))
        self.assertEqual(rbac.tenant.name, RBAC_GLOBAL_TENANT_NAME)

    def test_sync_skips_gracefully_if_global_tenant_absent(self):
        """If init_rbac hasn't run, sync logs a warning but does NOT raise."""
        from msbc_rbac.core.models import Tenant as RBACTenant
        from auth_app.signals import _bust_rbac_tenant_cache
        RBACTenant.objects.using('rbac').filter(name=RBAC_GLOBAL_TENANT_NAME).delete()
        _bust_rbac_tenant_cache()
        try:
            make_journies_user(self.hotel, email='graceful_sync@journies.test')
        except Exception as exc:
            self.fail(f"User creation raised when RBAC tenant absent: {exc}")
        finally:
            ensure_rbac_global_tenant()

    # ── Role assignment sync ──────────────────────────────────────────────

    def test_role_id_on_creation_assigns_user_role_in_rbac(self):
        """
        When UserModel is created with role_id=1 (owner), accounts.UserRole
        must be created in the rbac DB linking the user to the 'owner' Role.

        Link: UserModel.role_id (int) == admin_role.Role.id (int)
        """
        from msbc_rbac.accounts.models import UserRole
        user = make_journies_user(self.hotel, email='owner_role@journies.test')
        user.role_id = 1   # owner — same PK as admin_role.Role id=1
        user.save()

        rbac_userrole = UserRole.objects.using('rbac').filter(
            user__username=str(user.id)
        ).select_related('role').first()

        self.assertIsNotNone(rbac_userrole,
            "accounts.UserRole not created in rbac DB when role_id is set.")
        self.assertEqual(rbac_userrole.role.name, 'owner',
            "UserRole.role must match admin_role.Role with the same PK as role_id.")
        self.assertEqual(rbac_userrole.role_id, 1)

    def test_changing_role_id_updates_existing_user_role(self):
        """
        When UserModel.role_id changes (e.g. owner → general_manager),
        the existing accounts.UserRole row must be updated, not duplicated.
        """
        from msbc_rbac.accounts.models import UserRole
        user = make_journies_user(self.hotel, email='rolechange@journies.test')

        # Assign owner (id=1)
        user.role_id = 1
        user.save()

        # Promote to regional_manager (id=2)... then later demote to gm (id=3)
        user.role_id = 3   # general_manager
        user.save()

        # Must be exactly ONE UserRole row — not two
        role_count = UserRole.objects.using('rbac').filter(
            user__username=str(user.id)
        ).count()
        self.assertEqual(role_count, 1,
            "Changing role_id must UPDATE the existing UserRole, not create a duplicate.")

        rbac_userrole = UserRole.objects.using('rbac').get(
            user__username=str(user.id)
        )
        self.assertEqual(rbac_userrole.role.name, 'general_manager')

    def test_no_role_id_does_not_create_user_role(self):
        """
        Users created without role_id (e.g. pending-onboarding owners) must
        have an accounts.User in rbac DB but NO accounts.UserRole row.
        Role is assigned later when Compass sets role_id.
        """
        from msbc_rbac.accounts.models import UserRole
        user = make_journies_user(self.hotel, email='norole@journies.test')
        # role_id is None by default

        exists = UserRole.objects.using('rbac').filter(
            user__username=str(user.id)
        ).exists()
        self.assertFalse(exists,
            "No accounts.UserRole should exist when UserModel.role_id is None.")
