from django.db import models


class Documents(models.Model):
    STATUS_CHOICES = (
        ("draft", "draft"),
        ("filled", "filled"),
        ("generated", "generated"),
        ("archived", "archived"),
    )

    document_id = models.BigAutoField(primary_key=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)
    document_type_id = models.ForeignKey("templates_cfg.DocumentTypes", on_delete=models.PROTECT, related_name="documents")
    object_id = models.ForeignKey("templates_cfg.ProductionObjects", on_delete=models.PROTECT, related_name="documents")
    user_id = models.ForeignKey("users.Users", on_delete=models.PROTECT, related_name="documents")
    process_id = models.ForeignKey("processes.Processes", on_delete=models.PROTECT, related_name="documents")
    generated_html = models.TextField(blank=True)
    generated_file = models.FileField(upload_to="generated_docs/", null=True, blank=True)
    table_rows_json = models.TextField(
        default="[]",
        blank=True,
        help_text="JSON-массив строк таблицы: [{\"col_key\": \"значение\", ...}, ...] для шаблонов с таблицей.",
    )

    class Meta:
        db_table = "Documents"
        ordering = ("-created_at",)


class DocumentLinks(models.Model):
    doc_link_id = models.BigAutoField(primary_key=True)
    source_document_id = models.ForeignKey(Documents, on_delete=models.CASCADE, related_name="outgoing_links")
    target_document_id = models.ForeignKey(Documents, on_delete=models.CASCADE, related_name="incoming_links")
    step_id = models.ForeignKey("processes.ProcessSteps", on_delete=models.PROTECT, related_name="document_links")
    description = models.TextField(blank=True)

    class Meta:
        db_table = "DocumentLinks"
