"""Человекочитаемые описания правил FieldSourceRule."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.bpm.models import FieldSourceRule, ProcessDocumentTemplate


def rule_summary_line(
    pdt: ProcessDocumentTemplate,
    requisite,
    rule: FieldSourceRule | None,
) -> str:
    """Одна строка вида «Служебная записка.Подписант ← справочник …»."""
    doc_name = pdt.document_type.name
    left = f"{doc_name}.{requisite.name}"
    if not rule:
        return f"{left} ← ручной ввод"
    st = rule.source_type
    if st == "manual":
        return f"{left} ← ручной ввод"
    if st == "dictionary":
        if rule.dictionary_id and rule.dictionary_field:
            return f"{left} ← Справочник «{rule.dictionary.name}».«{rule.dictionary_field}»"
        return f"{left} ← Справочник (укажите справочник и поле JSON)"
    if st == "process_object":
        return f"{left} ← объект БП ({rule.object_field or '?'})"
    if st == "process_context":
        return f"{left} ← контекст процесса «{rule.context_key or '?'}»"
    if st == "previous_document":
        sp = rule.source_process_document_template
        sr = rule.source_requisite
        if sp and sr:
            src_doc = sp.document_type.name
            return f"{left} ← {src_doc}.{sr.name}"
        return f"{left} ← предыдущий документ (задайте шаг и реквизит)"
    return f"{left} ← {st}"
