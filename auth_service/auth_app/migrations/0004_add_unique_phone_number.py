# Add unique constraint to phone_number field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_app', '0003_tokenblacklist'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usermodel',
            name='phone_number',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
    ]