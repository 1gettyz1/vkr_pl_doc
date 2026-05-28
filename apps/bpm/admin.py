from django.contrib import admin

from .models import (
    BusinessProcessInstance,
    BusinessProcessTemplate,
    DictionaryColumn,
    DictionaryRecord,
    FieldSourceRule,
    InstanceDictionarySelection,
    ProcessDocumentInstance,
    ProcessDocumentTemplate,
    ReferenceDictionary,
)


@admin.register(BusinessProcessTemplate)
class BusinessProcessTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "legacy_process")


@admin.register(ProcessDocumentTemplate)
class ProcessDocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("business_process_template", "step_order", "name", "document_type")


@admin.register(BusinessProcessInstance)
class BusinessProcessInstanceAdmin(admin.ModelAdmin):
    list_display = ("business_process_template", "user", "status", "current_step_order", "created_at")


@admin.register(ProcessDocumentInstance)
class ProcessDocumentInstanceAdmin(admin.ModelAdmin):
    list_display = ("business_process_instance", "process_document_template", "document")


@admin.register(ReferenceDictionary)
class ReferenceDictionaryAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(DictionaryColumn)
class DictionaryColumnAdmin(admin.ModelAdmin):
    list_display = ("dictionary", "key", "title", "sort_order")


@admin.register(DictionaryRecord)
class DictionaryRecordAdmin(admin.ModelAdmin):
    list_display = ("dictionary", "lookup_key")


@admin.register(InstanceDictionarySelection)
class InstanceDictionarySelectionAdmin(admin.ModelAdmin):
    list_display = ("business_process_instance", "dictionary", "record")


@admin.register(FieldSourceRule)
class FieldSourceRuleAdmin(admin.ModelAdmin):
    list_display = ("process_document_template", "requisite", "source_type")
