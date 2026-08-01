from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chatbot", "0002_message_gateway_metadata")]

    operations = [
        migrations.AddField(
            model_name="message",
            name="answer_status",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="message",
            name="citations",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="message",
            name="generation_diagnostics",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="message",
            name="index_version_id",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="message",
            name="safety_related",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="message",
            name="status",
            field=models.CharField(
                choices=[
                    ("complete", "Complete"),
                    ("blocked", "Blocked by safety controls"),
                    ("error", "Provider error"),
                    ("abstained", "Insufficient approved evidence"),
                ],
                default="complete",
                max_length=16,
            ),
        ),
    ]
