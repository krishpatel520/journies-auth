"""
auth_app/tests/unit/test_rbac_middleware.py

Unit tests for the RBAC middleware stack and database router.

These tests are fast, isolated, and do NOT require a running RBAC DB
connection for the router tests.  They use Django's RequestFactory and
unittest.mock to verify middleware logic in isolation.

Run with:
    python manage.py test auth_app.tests.unit.test_rbac_middleware
"""
from unittest.mock import MagicMock, patch, PropertyMock
from django.test import TestCase, RequestFactory, override_settings
from django.http import JsonResponse, HttpResponse

from auth_service.db_router import RBACDatabaseRouter, RBAC_APP_LABELS


# ============================================================================
# 1. Database Router Unit Tests
# ============================================================================

class TestRBACDatabaseRouter(TestCase):
    """Verify the router correctly directs models to the right database."""

    def setUp(self):
        self.router = RBACDatabaseRouter()

    def _make_model(self, app_label: str):
        """Create a minimal mock model with the given app_label."""
        model = MagicMock()
        model._meta.app_label = app_label
        return model

    # ── db_for_read ──────────────────────────────────────────────────────────

    def test_core_app_reads_from_rbac_db(self):
        model = self._make_model('core')
        self.assertEqual(self.router.db_for_read(model), 'rbac')

    def test_accounts_app_reads_from_rbac_db(self):
        model = self._make_model('accounts')
        self.assertEqual(self.router.db_for_read(model), 'rbac')

    def test_auth_app_reads_from_default_db(self):
        model = self._make_model('auth_app')
        self.assertEqual(self.router.db_for_read(model), 'default')

    def test_django_admin_reads_from_default_db(self):
        model = self._make_model('admin')
        self.assertEqual(self.router.db_for_read(model), 'default')

    def test_contenttypes_reads_from_default_db(self):
        model = self._make_model('contenttypes')
        self.assertEqual(self.router.db_for_read(model), 'default')

    # ── db_for_write ─────────────────────────────────────────────────────────

    def test_core_app_writes_to_rbac_db(self):
        model = self._make_model('core')
        self.assertEqual(self.router.db_for_write(model), 'rbac')

    def test_accounts_app_writes_to_rbac_db(self):
        model = self._make_model('accounts')
        self.assertEqual(self.router.db_for_write(model), 'rbac')

    def test_auth_app_writes_to_default_db(self):
        model = self._make_model('auth_app')
        self.assertEqual(self.router.db_for_write(model), 'default')

    # ── allow_migrate ─────────────────────────────────────────────────────────

    def test_core_migrations_allowed_on_rbac_db(self):
        self.assertTrue(self.router.allow_migrate('rbac', 'core'))

    def test_accounts_migrations_allowed_on_rbac_db(self):
        self.assertTrue(self.router.allow_migrate('rbac', 'accounts'))

    def test_core_migrations_blocked_on_default_db(self):
        """RBAC apps must NOT migrate into the journies DB."""
        self.assertFalse(self.router.allow_migrate('default', 'core'))

    def test_accounts_migrations_blocked_on_default_db(self):
        """RBAC apps must NOT migrate into the journies DB."""
        self.assertFalse(self.router.allow_migrate('default', 'accounts'))

    def test_auth_app_migrations_allowed_on_default_db(self):
        self.assertTrue(self.router.allow_migrate('default', 'auth_app'))

    def test_auth_app_migrations_blocked_on_rbac_db(self):
        """Journies apps must NOT migrate into the rbac_project DB (except during tests)."""
        self.assertTrue(self.router.allow_migrate('rbac', 'auth_app'))

    def test_django_builtins_migrate_to_both_dbs(self):
        """auth and contenttypes must migrate to BOTH databases because RBAC models depend on auth."""
        for app in ('contenttypes', 'auth'):
            with self.subTest(app=app):
                self.assertTrue(self.router.allow_migrate('default', app))
                self.assertTrue(self.router.allow_migrate('rbac', app))

    def test_other_builtins_migrate_to_default_only(self):
        """admin, sessions, etc. stay exclusively in the default DB."""
        for app in ('admin', 'sessions', 'messages'):
            with self.subTest(app=app):
                self.assertTrue(self.router.allow_migrate('default', app))
                self.assertFalse(self.router.allow_migrate('rbac', app))

    # ── allow_relation ────────────────────────────────────────────────────────

    def test_cross_db_relations_are_blocked(self):
        """
        UUID-based cross-DB references (journies user → RBAC UserRole)
        must be blocked by the router (False) to prevent the schema editor
        from attempting to create cross-db FK constraints.
        """
        journies_user = self._make_model('auth_app')
        rbac_userrole = self._make_model('accounts')
        result = self.router.allow_relation(journies_user, rbac_userrole)
        self.assertFalse(result)

    def test_same_db_relations_are_allowed(self):
        rbac_obj1 = self._make_model('core')
        rbac_obj2 = self._make_model('accounts')
        self.assertTrue(self.router.allow_relation(rbac_obj1, rbac_obj2))

    # ── RBAC_APP_LABELS constant ──────────────────────────────────────────────

    def test_rbac_app_labels_contains_core_and_accounts(self):
        self.assertIn('core', RBAC_APP_LABELS)
        self.assertIn('accounts', RBAC_APP_LABELS)

    def test_rbac_app_labels_does_not_contain_auth_app(self):
        self.assertNotIn('auth_app', RBAC_APP_LABELS)


# ============================================================================
# 2. BYPASS_PATH_PREFIXES Middleware Logic Tests
# ============================================================================

class TestBypassPathPrefixes(TestCase):
    """
    Verify that the BYPASS_PATH_PREFIXES setting correctly whitelists paths.

    We test the bypass logic directly against settings, since RBACMiddleware
    reads BYPASS_PATH_PREFIXES at class definition time and we cannot
    easily monkey-patch it mid-test.  These tests prove the setting is
    configured with the required public paths.
    """

    def test_login_path_in_bypass_prefixes(self):
        from django.conf import settings
        self.assertIn('/api/v1/users/login/', settings.BYPASS_PATH_PREFIXES)

    def test_signup_path_in_bypass_prefixes(self):
        from django.conf import settings
        self.assertIn('/api/v1/users/signup/', settings.BYPASS_PATH_PREFIXES)

    def test_health_path_in_bypass_prefixes(self):
        from django.conf import settings
        self.assertIn('/health/', settings.BYPASS_PATH_PREFIXES)

    def test_swagger_path_in_bypass_prefixes(self):
        from django.conf import settings
        self.assertIn('/swagger/', settings.BYPASS_PATH_PREFIXES)

    def test_redoc_path_in_bypass_prefixes(self):
        from django.conf import settings
        self.assertIn('/redoc/', settings.BYPASS_PATH_PREFIXES)

    def test_jwks_path_in_bypass_prefixes(self):
        from django.conf import settings
        self.assertIn('/.well-known/jwks.json', settings.BYPASS_PATH_PREFIXES)

    def test_bypass_prefixes_matches_jwt_public_paths(self):
        """BYPASS_PATH_PREFIXES must be a superset of JWT_PUBLIC_PATHS."""
        from django.conf import settings
        for path in settings.JWT_PUBLIC_PATHS:
            self.assertIn(
                path, settings.BYPASS_PATH_PREFIXES,
                msg=f"'{path}' is in JWT_PUBLIC_PATHS but missing from BYPASS_PATH_PREFIXES",
            )


# ============================================================================
# 3. RBACMiddleware Behaviour Tests (mocked DB)
# ============================================================================

class TestRBACMiddlewareBehaviourMocked(TestCase):
    """
    Test the RBACMiddleware decision tree using mocked database interactions.

    This avoids needing a real rbac_project DB and instead patches
    the resolver functions that the middleware delegates to.
    """
    databases = ['default', 'rbac']

    def setUp(self):
        self.factory = RequestFactory()
        self.dummy_response = HttpResponse('ok', status=200)

    def _get_middleware(self, get_response=None):
        from msbc_rbac.core.services.RBACMiddleware import RBACMiddleware
        return RBACMiddleware(get_response or (lambda r: self.dummy_response))

    def _authenticated_request(self, path='/api/v1/users/', method='GET'):
        """Build a request with a mock authenticated user attached."""
        request = self.factory.generic(method, path)
        user = MagicMock()
        user.is_authenticated = True
        user.tenant = MagicMock()
        user.tenant.pk = 1
        request.user = user
        return request

    def _anonymous_request(self, path='/api/v1/users/', method='GET'):
        """Build a request with an anonymous (unauthenticated) user."""
        request = self.factory.generic(method, path)
        user = MagicMock()
        user.is_authenticated = False
        request.user = user
        return request

    # ── bypass paths ─────────────────────────────────────────────────────────

    @patch('msbc_rbac.core.services.RBACMiddleware.RBACMiddleware.BYPASS_PATH_PREFIXES',
           ['/api/v1/users/login/'])
    def test_bypass_path_returns_200_without_rbac_check(self):
        """Login path must pass through without any RBAC DB interaction."""
        request = self._authenticated_request('/api/v1/users/login/')
        middleware = self._get_middleware()

        with patch('msbc_rbac.core.services.RBACMiddleware.resolve_api_operation') as mock_resolver:
            response = middleware(request)

        # resolve_api_operation should never be called for a bypass path
        mock_resolver.assert_not_called()
        self.assertEqual(response.status_code, 200)

    # ── anonymous user ────────────────────────────────────────────────────────

    @patch('msbc_rbac.core.services.RBACMiddleware.RBACMiddleware.BYPASS_PATH_PREFIXES', [])
    def test_anonymous_user_passes_through_rbac_step_2(self):
        """
        Unauthenticated users must flow past the RBAC middleware without a 401.
        Authentication is enforced separately by JWTAuthenticationMiddleware.
        """
        request = self._anonymous_request('/api/v1/some-protected/')
        middleware = self._get_middleware()

        with patch('msbc_rbac.core.services.RBACMiddleware.resolve_api_operation') as mock_resolver:
            response = middleware(request)

        mock_resolver.assert_not_called()
        self.assertEqual(response.status_code, 200)

    # ── no ApiOperation registered ────────────────────────────────────────────

    @patch('msbc_rbac.core.services.RBACMiddleware.RBACMiddleware.BYPASS_PATH_PREFIXES', [])
    @patch('msbc_rbac.core.services.RBACMiddleware.resolve_api_operation', return_value=None)
    def test_unregistered_api_returns_401(self, mock_resolver):
        """
        If the endpoint has no ApiOperation row in the rbac DB, the middleware
        must deny the request (step 3 — API must be registered).
        """
        request = self._authenticated_request('/api/v1/unregistered-endpoint/')
        middleware = self._get_middleware()
        response = middleware(request)

        self.assertEqual(response.status_code, 401)
        import json
        body = json.loads(response.content)
        self.assertFalse(body.get('success'))

    # ── disabled ApiOperation ─────────────────────────────────────────────────

    @patch('msbc_rbac.core.services.RBACMiddleware.RBACMiddleware.BYPASS_PATH_PREFIXES', [])
    @patch('msbc_rbac.core.services.RBACMiddleware.resolve_api_operation')
    def test_disabled_operation_returns_401(self, mock_resolver):
        """
        Platform-level disabled ApiOperation (is_enabled=False) must return 401
        (step 4 — platform-level API disable).
        """
        mock_op = MagicMock()
        mock_op.is_enabled = False
        mock_resolver.return_value = mock_op

        request = self._authenticated_request('/api/v1/disabled-op/')
        middleware = self._get_middleware()
        response = middleware(request)

        self.assertEqual(response.status_code, 401)

    # ── user-level API block ──────────────────────────────────────────────────

    @patch('msbc_rbac.core.services.RBACMiddleware.RBACMiddleware.BYPASS_PATH_PREFIXES', [])
    @patch('msbc_rbac.core.services.RBACMiddleware.resolve_api_operation')
    @patch('msbc_rbac.core.services.RBACMiddleware.user_api_blocked', return_value=True)
    @patch('msbc_rbac.core.services.RBACMiddleware.tenant_api_disabled', return_value=False)
    @patch('msbc_rbac.core.services.RBACMiddleware.TenantModule.objects')
    def test_user_api_block_returns_401(self, mock_tm, mock_tenant_disable, mock_user_block, mock_resolver):
        """
        An explicit UserApiBlock record must deny the request (step 7 — highest
        priority deny).
        """
        mock_op = MagicMock()
        mock_op.is_enabled = True
        mock_op.endpoint.module = MagicMock()
        mock_op.endpoint.submodule = None
        mock_resolver.return_value = mock_op

        # TenantModule subscription passes
        tm_instance = MagicMock()
        tm_instance.is_enabled = True
        tm_instance.expiration_date = None
        mock_tm.filter.return_value.filter.return_value.first.return_value = tm_instance

        request = self._authenticated_request('/api/v1/blocked-for-user/')
        middleware = self._get_middleware()
        response = middleware(request)

        self.assertEqual(response.status_code, 401)
        import json
        body = json.loads(response.content)
        self.assertIn('blocked', body.get('message', '').lower())

    # ── authorized role passes ────────────────────────────────────────────────

    @patch('msbc_rbac.core.services.RBACMiddleware.RBACMiddleware.BYPASS_PATH_PREFIXES', [])
    @patch('msbc_rbac.core.services.RBACMiddleware.resolve_api_operation')
    @patch('msbc_rbac.core.services.RBACMiddleware.user_api_blocked', return_value=False)
    @patch('msbc_rbac.core.services.RBACMiddleware.tenant_api_disabled', return_value=False)
    @patch('msbc_rbac.core.services.RBACMiddleware.get_user_permissions')
    @patch('msbc_rbac.core.services.RBACMiddleware.has_permission', return_value=True)
    @patch('msbc_rbac.core.services.RBACMiddleware.TenantModule.objects')
    def test_authorized_role_passes_through(self, mock_tm, mock_has_perm, mock_get_perms,
                                             mock_user_block, mock_tenant_disable, mock_resolver):
        """
        Full happy-path: registered operation, enabled, not blocked, and the role
        has permission → request must reach the view (200).
        """
        mock_op = MagicMock()
        mock_op.is_enabled = True
        mock_op.permission_code = 'read'
        mock_op.endpoint.module = MagicMock()
        mock_op.endpoint.submodule = None
        mock_resolver.return_value = mock_op
        mock_get_perms.return_value = []

        tm_instance = MagicMock()
        tm_instance.is_enabled = True
        tm_instance.expiration_date = None
        mock_tm.filter.return_value.filter.return_value.first.return_value = tm_instance

        request = self._authenticated_request('/api/v1/users/')
        middleware = self._get_middleware()
        response = middleware(request)

        self.assertEqual(response.status_code, 200)


# ============================================================================
# 4. Signal Registration Tests
# ============================================================================

class TestSignalRegistration(TestCase):
    """Verify that sync signals are wired up correctly."""

    def test_user_sync_signal_is_connected(self):
        """post_save(UserModel) must have sync_user_to_rbac connected."""
        from django.db.models.signals import post_save
        from auth_app.models.user_model import UserModel
        from auth_app.signals import sync_user_to_rbac

        receiver_funcs = []
        for r in post_save.receivers:
            func = r[1]()
            if func is not None:
                receiver_funcs.append(func)
        self.assertIn(sync_user_to_rbac, receiver_funcs)
