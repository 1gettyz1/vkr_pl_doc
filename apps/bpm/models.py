import json

from django.db import models


class BusinessProcessTemplate(models.Model):
    """Шаблон БП: последовательность документов и общая привязка к процессу Django."""

    bpt_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    legacy_process = models.ForeignKey(
        "processes.Processes",
        on_delete=models.PROTECT,
        related_name="business_templates",
        help_text="Процесс из базовой модели: нужен для совместимости с Documents.process_id",
    )
    objects_dictionary = models.ForeignKey(
        "ReferenceDictionary",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bpm_templates_as_objects",
        help_text="Справочник объектов: запись при запуске БП становится производственным объектом документов.",
    )

    class Meta:
        db_table = "BusinessProcessTemplates"

    def __str__(self):
        return self.name


class ProcessDocumentTemplate(models.Model):
    """Шаг шаблона БП: какой тип документа выпускается на этом шаге (DOCX + реквизиты типа)."""

    pdt_id = models.BigAutoField(primary_key=True)
    business_process_template = models.ForeignKey(
        BusinessProcessTemplate,
        on_delete=models.CASCADE,
        related_name="document_templates",
    )
    step_order = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    document_type = models.ForeignKey(
        "templates_cfg.DocumentTypes",
        on_delete=models.PROTECT,
        related_name="process_document_templates",
    )

    class Meta:
        db_table = "ProcessDocumentTemplates"
        ordering = ("business_process_template", "step_order")
        unique_together = (("business_process_template", "step_order"),)

    def __str__(self):
        return f"{self.business_process_template.name}: {self.step_order}. {self.name}"


class ReferenceDictionary(models.Model):
    """Справочник (например подразделения → подписант, должность…)."""

    dictionary_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    selection_column_key = models.CharField(
        max_length=64,
        blank=True,
        help_text="Колонка, по значению которой оператор выбирает запись; также формируется внутренний код строки.",
    )

    class Meta:
        db_table = "ReferenceDictionaries"
        verbose_name_plural = "reference dictionaries"

    def __str__(self):
        return self.name


class DictionaryColumn(models.Model):
    """Колонка справочника = ключ в JSON payload записей."""

    column_id = models.BigAutoField(primary_key=True)
    dictionary = models.ForeignKey(
        ReferenceDictionary,
        on_delete=models.CASCADE,
        related_name="columns",
    )
    key = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "DictionaryColumns"
        ordering = ("dictionary", "sort_order", "key")
        unique_together = (("dictionary", "key"),)

    def __str__(self):
        return f"{self.dictionary.name}.{self.key}"


class DictionaryRecord(models.Model):
    """Запись справочника: ключ подстановки + JSON-поля."""

    record_id = models.BigAutoField(primary_key=True)
    dictionary = models.ForeignKey(
        ReferenceDictionary,
        on_delete=models.CASCADE,
        related_name="records",
    )
    lookup_key = models.CharField(max_length=255, db_index=True)
    payload_json = models.TextField(default="{}")  # {"signer_name": "…", "signer_position": "…"}

    class Meta:
        db_table = "DictionaryRecords"
        unique_together = (("dictionary", "lookup_key"),)

    def __str__(self):
        return f"{self.dictionary.name}: {self.lookup_key}"

    def payload(self):
        try:
            return json.loads(self.payload_json or "{}")
        except json.JSONDecodeError:
            return {}


class FieldSourceRule(models.Model):
    """
    Откуда берётся значение реквизита на шаге шаблона БП.
    source_type: manual | dictionary | process_object | previous_document | process_context
    """

    SOURCE_MANUAL = "manual"
    SOURCE_DICTIONARY = "dictionary"
    SOURCE_PROCESS_OBJECT = "process_object"
    SOURCE_PREVIOUS_DOCUMENT = "previous_document"
    SOURCE_PROCESS_CONTEXT = "process_context"

    SOURCE_CHOICES = (
        (SOURCE_MANUAL, "Ручной ввод"),
        (SOURCE_DICTIONARY, "Справочник"),
        (SOURCE_PROCESS_OBJECT, "Объект БП"),
        (SOURCE_PREVIOUS_DOCUMENT, "Предыдущий документ"),
        (SOURCE_PROCESS_CONTEXT, "Контекст процесса"),
    )

    rule_id = models.BigAutoField(primary_key=True)
    process_document_template = models.ForeignKey(
        ProcessDocumentTemplate,
        on_delete=models.CASCADE,
        related_name="field_rules",
    )
    requisite = models.ForeignKey(
        "requisites.Requisites",
        on_delete=models.CASCADE,
        related_name="bpm_field_rules",
    )
    source_type = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)

    dictionary = models.ForeignKey(
        ReferenceDictionary,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_rules",
    )
    dictionary_field = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ключ в JSON записи справочника, напр. signer_name",
    )

    object_field = models.CharField(
        max_length=64,
        blank=True,
        help_text="name | object_type — поле производственного объекта",
    )

    source_process_document_template = models.ForeignKey(
        ProcessDocumentTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rules_as_previous_step",
        help_text="Предыдущий шаг, из документа которого копируем",
    )
    source_requisite = models.ForeignKey(
        "requisites.Requisites",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rules_as_source_requisite",
    )

    context_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ключ в context_json экземпляра БП (process_context)",
    )

    class Meta:
        db_table = "FieldSourceRules"
        unique_together = (("process_document_template", "requisite"),)

    def __str__(self):
        return f"{self.source_type} → {self.requisite.name}"


class InstanceDictionarySelection(models.Model):
    """Выбранные записи справочников при запуске экземпляра БП (оператор выбирает по одной на справочник)."""

    selection_id = models.BigAutoField(primary_key=True)
    business_process_instance = models.ForeignKey(
        "BusinessProcessInstance",
        on_delete=models.CASCADE,
        related_name="dictionary_selections",
    )
    dictionary = models.ForeignKey(
        ReferenceDictionary,
        on_delete=models.CASCADE,
        related_name="instance_selections",
    )
    record = models.ForeignKey(
        "DictionaryRecord",
        on_delete=models.CASCADE,
        related_name="instance_selections",
    )

    class Meta:
        db_table = "InstanceDictionarySelections"
        unique_together = (("business_process_instance", "dictionary"),)

    def __str__(self):
        return f"{self.business_process_instance_id}: {self.dictionary.name} → {self.record.lookup_key}"


class BusinessProcessInstance(models.Model):
    """Запущенный экземпляр БП для оператора."""

    STATUS_DRAFT = "draft"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "draft"),
        (STATUS_IN_PROGRESS, "in_progress"),
        (STATUS_COMPLETED, "completed"),
    )

    bpi_id = models.BigAutoField(primary_key=True)
    instance_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Название экземпляра БП, которое задаёт оператор при запуске.",
    )
    business_process_template = models.ForeignKey(
        BusinessProcessTemplate,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    user = models.ForeignKey("users.Users", on_delete=models.PROTECT, related_name="bpm_instances")
    production_object = models.ForeignKey(
        "templates_cfg.ProductionObjects",
        on_delete=models.PROTECT,
        related_name="bpm_instances",
    )
    legacy_process = models.ForeignKey(
        "processes.Processes",
        on_delete=models.PROTECT,
        related_name="bpm_instances",
        help_text="Дублирует шаблон: для поля Documents.process_id",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)
    current_step_order = models.PositiveIntegerField(default=1)
    context_json = models.TextField(default="{}")
    dictionary_lookup_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ключ поиска в справочнике (например название подразделения)",
    )
    dictionary_record = models.ForeignKey(
        DictionaryRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bpm_instances",
        help_text="Выбранная запись справочника при запуске БП",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "BusinessProcessInstances"
        ordering = ("-created_at",)

    def context_dict(self):
        try:
            return json.loads(self.context_json or "{}")
        except json.JSONDecodeError:
            return {}

    def set_context(self, d: dict):
        self.context_json = json.dumps(d, ensure_ascii=False)
        self.save(update_fields=["context_json"])


class ProcessDocumentInstance(models.Model):
    """Связь экземпляра БП с созданным документом на конкретном шаге."""

    pdi_id = models.BigAutoField(primary_key=True)
    business_process_instance = models.ForeignKey(
        BusinessProcessInstance,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    process_document_template = models.ForeignKey(
        ProcessDocumentTemplate,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    document = models.OneToOneField(
        "documents.Documents",
        on_delete=models.CASCADE,
        related_name="bpm_document_slot",
    )

    class Meta:
        db_table = "ProcessDocumentInstances"
        unique_together = (("business_process_instance", "process_document_template"),)
