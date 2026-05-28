from django.db import models


class DocumentTypes(models.Model):
    document_type_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    template_file = models.FileField(upload_to="doc_templates/", null=True, blank=True)
    template_html = models.TextField(blank=True)
    has_table_template = models.BooleanField(
        default=False,
        help_text="В DOCX есть повторяющаяся таблица: две подряд строки с одинаковыми плейсхолдерами; ключи не дублируются в каталоге полей.",
    )
    table_anchor_json = models.TextField(
        blank=True,
        default="",
        help_text="JSON: индекс таблицы и две строки-шаблона, например {\"table_idx\":0,\"row0\":1,\"row1\":2}.",
    )

    class Meta:
        db_table = "DocumentTypes"

    def __str__(self):
        return self.name


class ProductionObjects(models.Model):
    object_id = models.BigAutoField(primary_key=True)
    object_type = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    source_record = models.ForeignKey(
        "bpm.DictionaryRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_objects",
        help_text="Если задано — объект создан из записи справочника.",
    )

    class Meta:
        db_table = "ProductionObjects"

    def __str__(self):
        return self.name
