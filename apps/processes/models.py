from django.db import models


class Processes(models.Model):
    process_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "Processes"

    def __str__(self):
        return self.name


class ProcessSteps(models.Model):
    step_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    step_order = models.PositiveIntegerField()
    process_id = models.ForeignKey(Processes, on_delete=models.CASCADE, related_name="steps")

    class Meta:
        db_table = "ProcessSteps"
        unique_together = ("process_id", "step_order")
        ordering = ("process_id", "step_order")

    def __str__(self):
        return f"{self.process_id.name}: {self.name}"
