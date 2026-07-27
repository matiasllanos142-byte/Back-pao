from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0015_merge_product_pushdevice"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer_phone",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="order",
            name="promo_code",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="order",
            name="discount_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
