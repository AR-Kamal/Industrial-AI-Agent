from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chatbot", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="error_code",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="message",
            name="model_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="message",
            name="provider",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="message",
            name="status",
            field=models.CharField(
                choices=[
                    ("complete", "Complete"),
                    ("blocked", "Blocked by safety controls"),
                    ("error", "Provider error"),
                ],
                default="complete",
                max_length=16,
            ),
        ),
    ]
