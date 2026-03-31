"""
auth_service/db_router.py

Database Router — enforces strict separation between the journies (auth_service)
database and the rbac_project database.

Routing table:
  app_label                        | database
  ---------------------------------|----------
  'core'    (msbc_rbac.core)       | 'rbac'
  'accounts' (msbc_rbac.accounts)  | 'rbac'
  everything else (auth_app, etc.) | 'default'

This prevents Django from creating RBAC tables inside the journies DB.
It also allows UUID-based loose coupling between auth_app.UserModel (default DB)
and accounts.UserRole (rbac DB) without database-level FK constraints.
"""

import logging

logger = logging.getLogger(__name__)

# App labels owned by the msbc_rbac package
RBAC_APP_LABELS = frozenset({'core', 'accounts'})

# App labels that belong exclusively to the journies (default) database
JOURNIES_APP_LABELS = frozenset({'auth_app', 'admin', 'contenttypes', 'sessions', 'messages'})


class RBACDatabaseRouter:
    """
    Routes msbc_rbac models (core.* and accounts.*) to the 'rbac' database
    and keeps all auth_app models in the 'default' (auth_service) database.

    Enforces a clean separation so `python manage.py migrate` applied to the
    default database never creates RBAC tables there, and vice-versa.
    """

    def db_for_read(self, model, **hints):
        """Point reads to the correct database."""
        if model._meta.app_label in RBAC_APP_LABELS:
            return 'rbac'
        return 'default'

    def db_for_write(self, model, **hints):
        """Point writes to the correct database."""
        if model._meta.app_label in RBAC_APP_LABELS:
            return 'rbac'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations only within the same database context.

        Returning False for cross-database links prevents Django's schema
        editor from attempting to create database-level foreign key constraints
        between `accounts` tables and `auth_app` tables during `migrate` and
        the test runner setup.
        """
        db1 = 'rbac' if obj1._meta.app_label in RBAC_APP_LABELS else 'default'
        db2 = 'rbac' if obj2._meta.app_label in RBAC_APP_LABELS else 'default'
        return db1 == db2

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Control which database each app's migrations run against.

        - RBAC apps  → 'rbac' database only
        - Django core apps → Both databases (msbc_rbac relies on auth_group, etc.)
        - All others → 'default' database only
        """
        if app_label == 'auth_app':
            # Allow auth_app to migrate to both databases (including 'rbac') to satisfy the
            # swappable_dependency(settings.AUTH_USER_MODEL) generated inside msbc_rbac migrations.
            return True

        if app_label in RBAC_APP_LABELS:
            return db == 'rbac'
            
        # Core Django framework apps must migrate to BOTH databases because
        # msbc_rbac.accounts.User inherits from PermissionsMixin.
        if app_label in {'auth', 'contenttypes'}:
            return True
            
        return db == 'default'
