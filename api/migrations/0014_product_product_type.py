from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0013_notification_payment_paymentevent_userevent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="product_type",
            field=models.CharField(
                choices=[("product", "Producto digital"), ("workshop", "Taller")],
                db_index=True,
                default="product",
                max_length=20,
            ),
        ),
    ]
