"""
Автозаполнение полей документа в контексте экземпляра БП и правил FieldSourceRule.
Дополняет (не заменяет полностью) логику RequisiteLinks из DocumentAutofillService.
"""

from __future__ import annotations

import json
from typing import Any

from apps.documents.models import Documents
from apps.logs.services import write_operation_log
from apps.requisites.models import RequisiteLinks, RequisiteValues, Requisites

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


def resolve_objects_dictionary_id(bpt: BusinessProcessTemplate, required_list: list) -> int | None:
    """Какой справочник считать «объектами», если в шаблоне не задано явно."""
    if bpt.objects_dictionary_id:
        return bpt.objects_dictionary_id
    for d in required_list:
        keys = set(
            DictionaryColumn.objects.filter(dictionary_id=d.dictionary_id).values_list("key", flat=True)
        )
        if "name" in keys and "object_type" in keys:
            return d.dictionary_id
    return None


def dictionaries_for_operator_startup(bpt: BusinessProcessTemplate):
    """Справочники, которые оператор должен выбрать при запуске (объекты + все из правил полей)."""
    ids = set()
    if bpt.objects_dictionary_id:
        ids.add(bpt.objects_dictionary_id)
    for did in (
        FieldSourceRule.objects.filter(
            process_document_template__business_process_template=bpt,
            source_type=FieldSourceRule.SOURCE_DICTIONARY,
        )
        .exclude(dictionary_id__isnull=True)
        .values_list("dictionary_id", flat=True)
        .distinct()
    ):
        ids.add(did)
    return ReferenceDictionary.objects.filter(dictionary_id__in=ids).order_by("name")


def _get_previous_document_for_step(
    instance: BusinessProcessInstance,
    source_pdt: ProcessDocumentTemplate,
) -> Documents | None:
    slot = (
        ProcessDocumentInstance.objects.filter(
            business_process_instance=instance,
            process_document_template=source_pdt,
        )
        .select_related("document")
        .first()
    )
    return slot.document if slot else None


def resolve_fields_for_step(
    instance: BusinessProcessInstance,
    pdt: ProcessDocumentTemplate,
    user,
) -> dict[str, Any]:
    """
    Возвращает {fields: [...], warnings: [...]} в том же формате, что DocumentAutofillService.build_document_form.
    """
    doc_type = pdt.document_type
    requisites = Requisites.objects.filter(document_type_id=doc_type).order_by("requisite_id")
    rules = {
        fr.requisite_id: fr
        for fr in FieldSourceRule.objects.select_related(
            "dictionary",
            "source_process_document_template",
            "source_requisite",
        ).filter(process_document_template=pdt)
    }
    link_map = {
        link.target_requisite_id_id: link
        for link in RequisiteLinks.objects.select_related(
            "source_requisite_id",
            "target_requisite_id",
        ).filter(target_requisite_id__in=requisites)
    }

    fields = []
    warnings = []

    ctx = instance.context_dict()
    lookup_key = (instance.dictionary_lookup_key or "").strip()
    dr = getattr(instance, "dictionary_record", None)
    if dr:
        lookup_key = (dr.lookup_key or "").strip()

    for req in requisites:
        field_payload = {
            "requisite_id": req.requisite_id,
            "name": req.name,
            "data_type": req.data_type,
            "is_required": req.is_required,
            "field_kind": req.field_kind,
            "placeholder_key": req.placeholder_key,
            "table_column": getattr(req, "is_table_column", False),
            "value": "",
            "source": "manual",
            "readonly": False,
            "source_document": "",
            "rule_source": "",
            "ui_mode": "manual",
            "ui_hint_ru": "",
        }

        rule = rules.get(req.requisite_id)
        resolved = False

        if rule:
            field_payload["rule_source"] = rule.source_type
            st = rule.source_type

            if st == FieldSourceRule.SOURCE_MANUAL:
                resolved = True

            elif st == FieldSourceRule.SOURCE_DICTIONARY and rule.dictionary and rule.dictionary_field:
                rec = None
                sel = InstanceDictionarySelection.objects.filter(
                    business_process_instance=instance,
                    dictionary_id=rule.dictionary_id,
                ).select_related("record").first()
                if sel:
                    rec = sel.record
                elif dr and dr.dictionary_id == rule.dictionary_id:
                    rec = dr
                elif lookup_key:
                    rec = DictionaryRecord.objects.filter(
                        dictionary=rule.dictionary,
                        lookup_key__iexact=lookup_key,
                    ).first()
                if rec:
                    val = rec.payload().get(rule.dictionary_field)
                    if val is not None and str(val).strip() != "":
                        field_payload["value"] = str(val)
                        field_payload["source"] = "auto"
                        field_payload["readonly"] = req.field_kind == "constant"
                        field_payload["source_document"] = f"Справочник: {rule.dictionary.name}"
                        field_payload["ui_mode"] = "auto_dict"
                        field_payload["ui_hint_ru"] = (
                            f'Заполнено автоматически из справочника «{rule.dictionary.name}» '
                            f'(поле «{rule.dictionary_field}»).'
                        )
                        resolved = True
                if not resolved:
                    warnings.append(
                        f"Поле «{req.name}»: нет данных из справочника «{rule.dictionary.name}» "
                        f"(проверьте выбор записи при запуске БП и поле JSON «{rule.dictionary_field}»)."
                    )

            elif st in (FieldSourceRule.SOURCE_PROCESS_OBJECT, FieldSourceRule.SOURCE_PROCESS_CONTEXT):
                warnings.append(
                    f"Поле «{req.name}»: правило с устаревшим источником — настройте справочник или предыдущий документ в шаблоне БП."
                )
                resolved = False

            elif st == FieldSourceRule.SOURCE_PREVIOUS_DOCUMENT:
                src_pdt = rule.source_process_document_template
                src_req = rule.source_requisite
                if src_pdt and src_req:
                    prev_doc = _get_previous_document_for_step(instance, src_pdt)
                    if prev_doc:
                        rv = RequisiteValues.objects.filter(
                            document_id=prev_doc,
                            requisite_id=src_req,
                        ).first()
                        if rv and rv.value.strip():
                            field_payload["value"] = rv.value
                            field_payload["source"] = "auto"
                            field_payload["readonly"] = req.field_kind == "constant"
                            field_payload["source_document"] = f"{prev_doc.document_type_id.name} (шаг {src_pdt.step_order})"
                            field_payload["ui_mode"] = "auto_prev"
                            field_payload["ui_hint_ru"] = (
                                f'Получено из предыдущего документа «{src_pdt.name}», поле «{src_req.name}».'
                            )
                            resolved = True
                    if not resolved:
                        warnings.append(
                            f"Поле «{req.name}»: не удалось взять значение из предыдущего документа «{src_pdt.name}»."
                        )
                else:
                    warnings.append(f"Поле «{req.name}»: правило previous_document задано неполностью.")

        # Fallback: старые RequisiteLinks, если BPM-правила не заданы или не сработали
        if not rule or not resolved:
            link = link_map.get(req.requisite_id)
            if link and (not rule or rule.source_type == FieldSourceRule.SOURCE_MANUAL):
                source_req = link.source_requisite_id
                source_doc_qs = Documents.objects.filter(document_type_id=source_req.document_type_id)
                ir = link.inheritance_rule or ""
                if ir in {"copy_latest_value", "copy_from_same_process"}:
                    source_doc_qs = source_doc_qs.filter(process_id_id=instance.legacy_process_id)
                if ir in {"copy_latest_value", "copy_from_same_object"}:
                    source_doc_qs = source_doc_qs.filter(object_id_id=instance.production_object_id)
                if ir == "copy_from_same_process_and_object":
                    source_doc_qs = source_doc_qs.filter(
                        process_id_id=instance.legacy_process_id,
                        object_id_id=instance.production_object_id,
                    )
                source_doc_qs = source_doc_qs.order_by("-created_at")
                source_doc = source_doc_qs.first()
                if source_doc:
                    source_value = RequisiteValues.objects.filter(
                        document_id=source_doc,
                        requisite_id=source_req,
                    ).first()
                    if source_value and source_value.value.strip():
                        field_payload["value"] = source_value.value
                        field_payload["source"] = "auto"
                        field_payload["readonly"] = req.field_kind == "constant"
                        field_payload["source_document"] = f"{source_doc.document_type_id.name} #{source_doc.document_id}"
                        field_payload["ui_mode"] = "auto_link"
                        field_payload["ui_hint_ru"] = "Значение подставлено по связи реквизитов между типами документов."

        fields.append(field_payload)

    return {"fields": fields, "warnings": warnings}


def get_or_create_document_for_step(
    instance: BusinessProcessInstance,
    pdt: ProcessDocumentTemplate,
    *,
    log_user=None,
):
    """Возвращает (ProcessDocumentInstance, Documents), создавая документ при необходимости."""
    slot = (
        ProcessDocumentInstance.objects.filter(
            business_process_instance=instance,
            process_document_template=pdt,
        )
        .select_related("document")
        .first()
    )
    if slot:
        return slot, slot.document

    document = Documents.objects.create(
        document_type_id=pdt.document_type,
        object_id=instance.production_object,
        user_id=instance.user,
        process_id=instance.legacy_process,
        status="draft",
    )
    if getattr(pdt.document_type, "has_table_template", False):
        document.table_rows_json = json.dumps([{}], ensure_ascii=False)
        document.save(update_fields=["table_rows_json"])
    slot = ProcessDocumentInstance.objects.create(
        business_process_instance=instance,
        process_document_template=pdt,
        document=document,
    )
    if log_user:
        write_operation_log(
            user=log_user,
            document=document,
            operation_result=(
                f'В экземпляре БП «{instance.business_process_template.name}» создан документ '
                f'«{pdt.document_type.name}» (шаг «{pdt.name}»).'
            ),
        )
    return slot, document
