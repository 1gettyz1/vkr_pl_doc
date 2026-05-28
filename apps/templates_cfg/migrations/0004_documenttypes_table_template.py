# Generated manually for table template support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("templates_cfg", "0003_reference_columns_and_selections"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypes",
            name="has_table_template",
            field=models.BooleanField(
                default=False,
                help_text="В DOCX есть повторяющаяся таблица: две подряд строки с одинаковыми плейсхолдерами; ключи не дублируются в каталоге полей.",
            ),
        ),
        migrations.AddField(
            model_name="documenttypes",
            name="table_anchor_json",
            field=models.TextField(
                blank=True,
                default="",
                help_text='JSON: индекс таблицы и две строки-шаблона, например {"table_idx":0,"row0":1,"row1":2}.',
            ),
        ),
    ]
