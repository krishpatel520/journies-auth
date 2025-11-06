# Generated migration for TokenBlacklist model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_app', '0002_usermodel_date_joined_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TokenBlacklist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.UUIDField(db_index=True)),
                ('revoked_at', models.DateTimeField(auto_now_add=True)),
                ('reason', models.CharField(default='logout', max_length=50)),
            ],
            options={
                'db_table': 'journies_token_blacklist',
            },
        ),
        migrations.AddIndex(
            model_name='tokenblacklist',
            index=models.Index(fields=['user_id', 'revoked_at'], name='journies_to_user_id_b8e5a5_idx'),
        ),
    ]