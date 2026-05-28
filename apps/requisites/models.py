from django.db import models


class Requisites(models.Model):
    FIELD_KIND_CHOICES = (("constant", "constant"), ("variable", "variable"))
    DATA_TYPE_CHOICES = (
        ("text", "text"),
        ("number", "number"),
        ("date", "date"),
        ("select", "select"),
        ("boolean", "boolean"),
    )

    requisite_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=30, choices=DATA_TYPE_CHOICES, default="text")
    is_required = models.BooleanField(default=False)
    field_kind = models.CharField(max_length=20, choices=FIELD_KIND_CHOICES, default="variable")
    placeholder_key = models.CharField(max_length=255, blank=True)
    is_table_column = models.BooleanField(
        default=False,
        help_text="Поле относится к повторяющимся строкам таблицы в DOCX (значения хранятся в Documents.table_rows_json).",
    )
    document_type_id = models.ForeignKey("templates_cfg.DocumentTypes", on_delete=models.CASCADE, related_name="requisites")

    class Meta:
        db_table = "Requisites"


class RequisiteValues(models.Model):
    value_id = models.BigAutoField(primary_key=True)
    document_id = models.ForeignKey("documents.Documents", on_delete=models.CASCADE, related_name="requisite_values")
    requisite_id = models.ForeignKey(Requisites, on_delete=models.CASCADE, related_name="values")
    value = models.TextField(blank=True)

    class Meta:
        db_table = "RequisiteValues"
        unique_together = ("document_id", "requisite_id")


class RequisiteLinks(models.Model):
    req_link_id = models.BigAutoField(primary_key=True)
    source_requisite_id = models.ForeignKey(Requisites, on_delete=models.CASCADE, related_name="source_links")
    target_requisite_id = models.ForeignKey(Requisites, on_delete=models.CASCADE, related_name="target_links")
    inheritance_rule = models.CharField(max_length=100, default="copy_if_empty")

    class Meta:
        db_table = "RequisiteLinks"
