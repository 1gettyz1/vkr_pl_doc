from django.db import models


class OperationLog(models.Model):
    operation_id = models.BigAutoField(primary_key=True)
    document_id = models.ForeignKey("documents.Documents", on_delete=models.CASCADE, related_name="operation_logs", null=True, blank=True)
    step_id = models.ForeignKey("processes.ProcessSteps", on_delete=models.PROTECT, related_name="operation_logs", null=True, blank=True)
    user_id = models.ForeignKey("users.Users", on_delete=models.PROTECT, related_name="operation_logs")
    operation_datetime = models.DateTimeField(auto_now_add=True)
    operation_result = models.TextField()

    class Meta:
        db_table = "OperationLog"
        ordering = ("-operation_datetime",)
