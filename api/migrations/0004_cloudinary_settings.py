from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0003_product_download_filename_product_download_url_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CloudinarySettings",
            fields=[
                ("id", models.CharField(default="cloudinary", max_length=50, primary_key=True, serialize=False)),
                ("cloud_name", models.CharField(max_length=200)),
                ("api_key", models.CharField(max_length=200)),
                ("api_secret_encrypted", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Cloudinary settings",
                "verbose_name_plural": "Cloudinary settings",
                "db_table": "cloudinary_settings",
            },
        ),
    ]
