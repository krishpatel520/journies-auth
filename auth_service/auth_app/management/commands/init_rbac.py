import logging
from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Initialize the global RBAC tenant and baseline roles in the '
        'rbac_project database.\n\n'
        'Architecture note: The entire journies application is a SINGLE tenant '
        'in RBAC ("Journies Global Project"). Individual hotels inside journies '
        '(auth_app.Tenant) are journies-internal and have no RBAC bearing. '
        'This command always targets the "rbac" database — never the journies DB.'
    )

    def handle(self, *args, **kwargs):
        # Import inside handle() to avoid AppRegistryNotReady
        from msbc_rbac.core.models import Tenant, Role

        try:
            with transaction.atomic(using='rbac'):
                # ── 1. Create / get the single platform-level RBAC Tenant ───
                # The entire journies service = 1 tenant in RBAC.
                # This is independent of how many hotels exist inside journies.
                tenant, created = Tenant.objects.using('rbac').get_or_create(
                    name='Journies Global Project',
                    defaults={'is_active': True},
                )
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Created RBAC tenant '{tenant.name}' (id={tenant.pk})"
                        )
                    )
                else:
                    self.stdout.write(
                        f"  Using existing RBAC tenant '{tenant.name}' (id={tenant.pk})"
                    )

                # ── 2. Seed baseline roles for all Journies service tiers ───
                # These roles apply across ALL journies endpoints regardless of
                # which hotel a user belongs to in the journies business layer.
                roles_data = [
                    {
                        'name': 'owner',
                        'display_name': 'Owner',
                        'description': (
                            'Master account for subscription, billing, '
                            'and full access control.'
                        ),
                    },
                    {
                        'name': 'regional_manager',
                        'display_name': 'Regional Manager',
                        'description': (
                            'Oversees a set of hotels across a region or '
                            'specific brand cluster.'
                        ),
                    },
                    {
                        'name': 'general_manager',
                        'display_name': 'General Manager',
                        'description': 'Operational head for one hotel.',
                    },
                    {
                        'name': 'department_head',
                        'display_name': 'Department Head',
                        'description': (
                            'Manages a functional area '
                            '(Housekeeping, F&B, Maintenance).'
                        ),
                    },
                    {
                        'name': 'team_member',
                        'display_name': 'Team Member',
                        'description': 'Execution-level user for day-to-day tasks.',
                    },
                ]

                role_fields = [f.name for f in Role._meta.get_fields()]
                created_count = 0

                for r_data in roles_data:
                    defaults = {}
                    if 'display_name' in role_fields:
                        defaults['display_name'] = r_data['display_name']
                    if 'description' in role_fields:
                        defaults['description'] = r_data['description']

                    role, r_created = Role.objects.using('rbac').get_or_create(
                        name=r_data['name'],
                        tenant=tenant,
                        defaults=defaults,
                    )
                    if r_created:
                        created_count += 1
                        self.stdout.write(f"  ✓ Created role '{role.name}'")
                    else:
                        self.stdout.write(f"  · Existing role '{role.name}'")

            # ── 3. Bust the signal cache so next user save resolves the
            #        freshly seeded tenant correctly.
            try:
                from auth_app.signals import _bust_rbac_tenant_cache
                _bust_rbac_tenant_cache()
            except Exception:
                pass  # Non-critical; cache will refresh on next request

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ RBAC initialised successfully.\n"
                    f"  Tenant   : 'Journies Global Project' (id={tenant.pk})\n"
                    f"  Roles    : {len(roles_data)} ensured ({created_count} newly created)\n"
                    f"  Database : rbac_project (all writes used using='rbac')\n"
                    f"\n  Note: Individual journies hotels (auth_app.Tenant) are NOT\n"
                    f"  synced to RBAC — they have no bearing on RBAC configuration."
                )
            )

        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(f"✗ Failed to initialise RBAC: {exc}")
            )
            logger.error("init_rbac failed", exc_info=True)
            raise
