# Generated manually for removing sku from Product model
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_stockmovement'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='sku',
        ),
    ]
