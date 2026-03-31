"""
management/commands/cleanup_journies_db.py

Removes orphaned RBAC tables from the journies (auth_service / default)
database.  These tables were created before the database router was in place
and now live in the wrong database.

Usage:
    # Preview what would be dropped (safe — no changes made)
    python manage.py cleanup_journies_db --dry-run

    # Actually drop the tables (prompts for confirmation)
    python manage.py cleanup_journies_db

    # Drop without confirmation (CI / scripts)
    python manage.py cleanup_journies_db --force
"""
import logging
from django.core.management.base import BaseCommand
from django.db import connections

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table names that belong ONLY in rbac_project, never in auth_service.
# These correspond to msbc_rbac.accounts and msbc_rbac.core models.
# ---------------------------------------------------------------------------
RBAC_TABLES = [
    # msbc_rbac.accounts tables
    'accounts_user',
    'accounts_user_groups',
    'accounts_user_user_permissions',
    'accounts_userapiblock',
    'accounts_userrole',
    # msbc_rbac.core tables
    'tenant',
    'admin_module',
    'admin_sub_module',
    'admin_mod_submodule_mapping',
    'admin_role',
    'admin_permission',
    'admin_role_permission_mapping',
    'admin_api_details',
    'admin_api_operation',
    'admin_tenant_api_operation',
    'admin_tenant_module',
    'core_tenantapipermission',
]

# Migration records for RBAC apps to remove from journies django_migrations table
RBAC_APP_LABELS = ('accounts', 'core')


class Command(BaseCommand):
    help = (
        'Remove orphaned RBAC tables from the journies (auth_service) database. '
        'Run AFTER adding the DATABASE_ROUTERS setting. '
        'Safe to run multiple times — only targets tables that actually exist.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List tables that WOULD be dropped without actually dropping them.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip the confirmation prompt and drop tables immediately.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        # ── 1. Detect which RBAC tables actually exist in the journies DB ───
        conn = connections['default']
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename
                FROM   pg_tables
                WHERE  schemaname = 'public'
                ORDER BY tablename
                """
            )
            existing_tables = {row[0] for row in cursor.fetchall()}

        orphaned_tables = [t for t in RBAC_TABLES if t in existing_tables]

        # ── 2. Check for orphaned migration records ──────────────────────────
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM django_migrations WHERE app = ANY(%s)",
                [list(RBAC_APP_LABELS)],
            )
            orphaned_migration_count = cursor.fetchone()[0]

        total = len(orphaned_tables)

        if total == 0 and orphaned_migration_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    '✓ auth_service DB is clean — no orphaned RBAC tables or '
                    'migration records found.'
                )
            )
            return

        # ── 3. Report ────────────────────────────────────────────────────────
        self.stdout.write(
            self.style.WARNING(
                f'\nFound {total} orphaned RBAC table(s) in auth_service DB:'
            )
        )
        for table in orphaned_tables:
            size = self._table_size(conn, table)
            self.stdout.write(f'  • {table:<45} {size}')

        if orphaned_migration_count:
            self.stdout.write(
                self.style.WARNING(
                    f'\nFound {orphaned_migration_count} orphaned migration '
                    f"record(s) in django_migrations for apps: "
                    f"{', '.join(RBAC_APP_LABELS)}"
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    '\n[DRY RUN] No changes were made. '
                    'Run without --dry-run to drop the tables above.'
                )
            )
            return

        # ── 4. Confirm ───────────────────────────────────────────────────────
        if not force:
            self.stdout.write(
                '\nThis will DROP the tables above from the auth_service '
                'database (CASCADE). Data will be permanently lost.\n'
            )
            confirm = input("Type 'yes' to proceed: ").strip().lower()
            if confirm != 'yes':
                self.stdout.write(self.style.ERROR('Aborted — no changes made.'))
                return

        # ── 5. Drop tables ───────────────────────────────────────────────────
        dropped = []
        failed = []
        with conn.cursor() as cursor:
            for table in orphaned_tables:
                try:
                    cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
                    dropped.append(table)
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Dropped: {table}')
                    )
                except Exception as exc:
                    failed.append(table)
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Failed to drop {table}: {exc}')
                    )

        # ── 6. Remove orphaned migration records ─────────────────────────────
        deleted_migrations = 0
        if orphaned_migration_count:
            with conn.cursor() as cursor:
                cursor.execute(
                    'DELETE FROM django_migrations WHERE app = ANY(%s)',
                    [list(RBAC_APP_LABELS)],
                )
                deleted_migrations = cursor.rowcount
            self.stdout.write(
                self.style.SUCCESS(
                    f'  ✓ Removed {deleted_migrations} orphaned migration record(s) '
                    f"for apps: {', '.join(RBAC_APP_LABELS)}"
                )
            )

        # ── 7. Summary ───────────────────────────────────────────────────────
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Cleanup complete.\n'
                f'  Tables dropped   : {len(dropped)}\n'
                f'  Tables failed    : {len(failed)}\n'
                f'  Migration records removed: {deleted_migrations}\n'
            )
        )
        if failed:
            self.stdout.write(
                self.style.ERROR(
                    f"  The following tables could not be dropped: {', '.join(failed)}\n"
                    f'  Check for active connections or FK dependencies and retry.'
                )
            )
            logger.warning('cleanup_journies_db: failed to drop tables: %s', failed)

        self.stdout.write(
            '\nNext step: run database migrations against both databases:\n'
            '  python manage.py migrate --database=default\n'
            '  python manage.py migrate --database=rbac\n'
        )

    @staticmethod
    def _table_size(conn, table: str) -> str:
        """Human-readable size of a table, or '—' if not accessible."""
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_size_pretty(pg_total_relation_size(%s))",
                    [table],
                )
                row = cursor.fetchone()
                return row[0] if row else '—'
        except Exception:
            return '—'
