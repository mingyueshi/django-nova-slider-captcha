from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nova_slider_captcha", "0002_ratelimitstate")]

    operations = [
        migrations.AddField(
            model_name="challenge", name="max_attempts",
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="challenge", name="tolerance",
            field=models.PositiveSmallIntegerField(default=4),
        ),
    ]
