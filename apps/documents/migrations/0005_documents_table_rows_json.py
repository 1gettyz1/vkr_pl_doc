# Generated manually for table row data on documents

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0004_documents_generated_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="documents",
            name="table_rows_json",
            field=models.TextField(
                blank=True,
                default="[]",
                help_text='JSON-массив строк таблицы: [{"col_key": "значение", ...}, ...] для шаблонов с таблицей.',
            ),
        ),
    ]
