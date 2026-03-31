"""
auth_app/tests/fixtures/rbac_test_data.py

Test helpers for the auth_service test suite.

Scope
-----
The auth_service tests cover:
  1. Public endpoint bypass (login/signup/health bypass RBAC)
  2. JWT auth enforcement (missing/invalid token → 401)
  3. RBAC middleware denial when no ApiOperation exists (step 3)
  4. Database separation (no RBAC tables in journies DB)
  5. User identity sync (auth_app.UserModel → accounts.User in rbac DB)

What is out of scope for auth_service tests:
  Full RBAC permission resolution (roles → permissions → modules → endpoints).
  That is the RBAC service's own test concern.

The two "tenant" concepts are SEPARATE and are NOT reconciled here:
  auth_app.Tenant = journies business tenant (hotels/companies)
  core.Tenant     = RBAC administrative tenant ("Journies Global Project")

These helpers only create journies-side data (default DB).
The only rbac-DB interaction in tests is the user sync assertion.
"""
import uuid
from auth_app.models.user_model import Tenant as JourneysTenant, UserModel

# The single RBAC tenant name — used only in sync assertion tests
RBAC_GLOBAL_TENANT_NAME = 'Journies Global Project'


def make_journies_tenant(code='TEST_HOTEL', name='Test Hotel') -> JourneysTenant:
    """
    Create a journies business tenant (hotel) in the default DB.

    Not related to core.Tenant (RBAC).  Required solely as a FK for UserModel.
    """
    return JourneysTenant.objects.create(
        id=uuid.uuid4(),
        code=code,
        name=name,
        status='active',
    )


def make_journies_user(
    tenant: JourneysTenant,
    email='testuser@journies.test',
    password='SecureP@ss123!',
    is_superuser=False,
) -> UserModel:
    """Create a journies UserModel in the default (auth_service) DB."""
    return UserModel.objects.create_user(
        email=email,
        password=password,
        tenant=tenant,
        first_name='Test',
        last_name='User',
        is_email_verified=True,
        status='active',
        is_superuser=is_superuser,
    )


def ensure_rbac_global_tenant():
    """
    Ensure 'Journies Global Project' core.Tenant exists in the rbac DB.
    Called in setUp() of sync tests — mirrors what `init_rbac` does in production.
    """
    from msbc_rbac.core.models import Tenant as RBACTenant
    from auth_app.signals import _bust_rbac_tenant_cache

    tenant, _ = RBACTenant.objects.using('rbac').get_or_create(
        name=RBAC_GLOBAL_TENANT_NAME,
        defaults={'is_active': True},
    )
    _bust_rbac_tenant_cache()
    return tenant
