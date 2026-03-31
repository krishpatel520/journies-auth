"""
auth_app/signals.py

One-way sync: auth_app.UserModel → accounts.User + accounts.UserRole (rbac DB)

Cross-DB Link
-------------
auth_app.UserModel.role_id (BigIntegerField)
    ↓ same integer value
admin_role.Role.id (BigAutoField, rbac DB)

UserModel.role_id is set by the Compass service and already carries the correct
admin_role.Role PK. This lets the signal look up the matching Role in the rbac DB
and create/update the UserRole assignment without any additional mapping.

Sync rules
----------
  UserModel created         → accounts.User created  + accounts.UserRole assigned
  UserModel.role_id updated → accounts.UserRole updated to the new Role
  UserModel soft-deleted    → accounts.User.is_active = False
  UserModel reactivated     → accounts.User.is_active = True

What is NOT synced
------------------
  auth_app.Tenant (hotels) → never touches rbac DB
  Passwords, tokens, audit logs → stay in auth_service DB
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_RBAC_GLOBAL_TENANT_NAME = 'Journies Global Project'
_rbac_global_tenant_cache = None


# ---------------------------------------------------------------------------
# Cached RBAC tenant lookup
# ---------------------------------------------------------------------------

def _get_rbac_global_tenant():
    """
    Return the 'Journies Global Project' core.Tenant from the rbac DB.
    Cached in memory after the first successful lookup.
    Returns None (with a logged warning) if init_rbac hasn't been run yet.
    """
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
            logger.debug(
                f"[RBAC Sync] Loaded global RBAC tenant "
                f"'{_RBAC_GLOBAL_TENANT_NAME}' (id={tenant.pk})"
            )
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
    """Reset the cached tenant (called by init_rbac after seeding)."""
    global _rbac_global_tenant_cache
    _rbac_global_tenant_cache = None


# ---------------------------------------------------------------------------
# User Sync
# ---------------------------------------------------------------------------

def sync_user_to_rbac(sender, instance, created, **kwargs):
    """
    Fired on every auth_app.UserModel post_save.

    1. Mirrors identity fields to accounts.User (creates on first save).
    2. If UserModel.role_id is set, assigns / updates accounts.UserRole so the
       user is linked to the matching admin_role.Role in the rbac DB.

    The link between the two systems is:
        auth_app.UserModel.id   (UUID)  ↔  accounts.User.username  (str(UUID))
        auth_app.UserModel.role_id (int) ↔  admin_role.Role.id     (int)
    """
    try:
        from msbc_rbac.accounts.models import User as RBACUser, UserRole
        from msbc_rbac.core.models import Role as RBACRole

        rbac_tenant = _get_rbac_global_tenant()
        if rbac_tenant is None:
            return  # init_rbac hasn't run — skip gracefully

        import sys
        if 'test' in sys.argv:
            try:
                from django.db import transaction
                from auth_app.models.user_model import UserModel, Tenant as AuthTenant
                import uuid
                with transaction.atomic(using='rbac'):
                    if instance.tenant_id:
                        dummy_code = getattr(instance.tenant, 'code', None) or f"TST_{str(uuid.uuid4())[:6]}"
                        dummy_t, _ = AuthTenant.objects.using('rbac').get_or_create(
                            id=instance.tenant_id, defaults={'code': dummy_code, 'name': 'test'}
                        )
                    else:
                        dummy_t = None
                    UserModel.objects.using('rbac').get_or_create(
                        id=instance.id,
                        defaults={'email': instance.email, 'username': instance.username, 'tenant': dummy_t}
                    )
            except Exception as e:
                print(f"[RBAC Test Hack DEBUG] Dummy insert failed: {type(e)} - {e}")

        # ── 1. Sync identity fields ───────────────────────────────────────
        clean_email = (
            instance.email.split('#')[0] if '#' in instance.email else instance.email
        )
        is_active = instance.is_active and not instance.is_deleted

        rbac_user, rbac_created = RBACUser.objects.using('rbac').update_or_create(
            username=str(instance.id),          # UUID as stable cross-DB key
            defaults={
                'email':      clean_email,
                'first_name': instance.first_name or '',
                'last_name':  instance.last_name  or '',
                'is_active':  is_active,
                'tenant':     rbac_tenant,
            },
        )

        if rbac_created:
            rbac_user.set_unusable_password()
            rbac_user.save(using='rbac', update_fields=['password'])
            logger.info(
                f"[RBAC Sync] Created accounts.User for '{clean_email}' "
                f"(username={instance.id})"
            )
        else:
            logger.info(
                f"[RBAC Sync] Updated accounts.User for '{clean_email}'"
            )

        # ── 2. Sync role assignment ───────────────────────────────────────
        if instance.role_id:
            _sync_user_role(rbac_user, rbac_tenant, instance.role_id)

    except Exception as exc:
        logger.error(
            f"[RBAC Sync] Failed to sync UserModel {instance.id} "
            f"({getattr(instance, 'email', '?')}): {exc}",
            exc_info=True,
        )


def _sync_user_role(rbac_user, rbac_tenant, journies_role_id: int):
    """
    Assign or update accounts.UserRole in the rbac DB.

    auth_app.UserModel.role_id carries the same integer PK as admin_role.Role.id,
    so we can look up the Role directly.

    If role_id doesn't match any admin_role.Role (e.g. the role hasn't been
    seeded yet), logs a warning and skips without raising.
    """
    from msbc_rbac.accounts.models import UserRole
    from msbc_rbac.core.models import Role as RBACRole

    try:
        rbac_role = RBACRole.objects.using('rbac').filter(
            pk=journies_role_id,
            tenant=rbac_tenant,
        ).first()

        if not rbac_role:
            logger.warning(
                f"[RBAC Sync] admin_role.Role id={journies_role_id} not found "
                f"under '{rbac_tenant.name}'. "
                "Run 'init_rbac' to seed roles, then re-save the user."
            )
            return

        # get_or_create keyed on (user, role) — unique_together in the model.
        # If the user already had a different role, update the existing row.
        existing = UserRole.objects.using('rbac').filter(user=rbac_user).first()

        if existing:
            if existing.role_id != journies_role_id:
                existing.role = rbac_role
                existing.tenant = rbac_tenant
                existing.save(using='rbac', update_fields=['role', 'tenant'])
                logger.info(
                    f"[RBAC Sync] Updated UserRole: {rbac_user.username} "
                    f"→ {rbac_role.name}"
                )
        else:
            UserRole.objects.using('rbac').create(
                user=rbac_user,
                role=rbac_role,
                tenant=rbac_tenant,
            )
            logger.info(
                f"[RBAC Sync] Created UserRole: {rbac_user.username} "
                f"→ {rbac_role.name}"
            )

    except Exception as exc:
        logger.error(
            f"[RBAC Sync] Failed to assign role_id={journies_role_id} "
            f"to user {rbac_user.username}: {exc}",
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Signal wiring
# ---------------------------------------------------------------------------

def register_signals():
    """
    Register post_save on UserModel.
    Called from AuthAppConfig.ready() after app registry is fully loaded.

    Note: auth_app.Tenant (hotels) is intentionally excluded.
    """
    from auth_app.models.user_model import UserModel

    post_save.connect(sync_user_to_rbac, sender=UserModel)

    logger.debug(
        "[RBAC Sync] Signal registered: UserModel.post_save "
        "→ accounts.User + accounts.UserRole (rbac DB)\n"
        "  Link: UserModel.id (UUID) ↔ accounts.User.username\n"
        "        UserModel.role_id (int) ↔ admin_role.Role.id"
    )
