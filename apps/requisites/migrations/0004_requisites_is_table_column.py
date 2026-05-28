# Generated manually for table column requisites

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("requisites", "0003_requisites_placeholder_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="requisites",
            name="is_table_column",
            field=models.BooleanField(
                default=False,
                help_text="Поле относится к повторяющимся строкам таблицы в DOCX (значения хранятся в Documents.table_rows_json).",
            ),
        ),
    ]
