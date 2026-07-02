from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_nvidiasettings_workbook_build_model_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="nvidiasettings",
            name="model_catalog",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="nvidiasettings",
            name="model_roles",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="nvidiasettings",
            name="model_catalog_refreshed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nvidiasettings",
            name="model_catalog_last_error",
            field=models.TextField(blank=True),
        ),
    ]
