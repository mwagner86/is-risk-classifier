from django.db import migrations

from apps.core.db import CREATE_FUNCTIONS, DROP_FUNCTIONS


class Migration(migrations.Migration):
    initial = True
    dependencies: list[tuple[str, str]] = []
    operations = [migrations.RunSQL(sql=CREATE_FUNCTIONS, reverse_sql=DROP_FUNCTIONS)]
