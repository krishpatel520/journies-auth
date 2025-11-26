# Generated migration to add Compass service fields and status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_app', '0008_remove_tenant_plan_usermodel_is_onboarding_complete_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermodel',
            name='role_id',
            field=models.BigIntegerField(blank=True, help_text='Role ID from Compass service', null=True),
        ),
        migrations.AddField(
            model_name='usermodel',
            name='invited_by_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='usermodel',
            name='status',
            field=models.CharField(max_length=20, default='pending', help_text='User status: pending, active, suspended'),
        ),
    ]
