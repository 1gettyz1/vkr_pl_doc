"""UI справочников: список, детализация с колонками, API поиска записей."""

import json

from django.db import IntegrityError
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.logs.services import write_operation_log
from apps.users.ui_permissions import LoginRequiredRoleMixin

from .dict_keys import slug_base, unique_lookup_key
from .models import DictionaryColumn, DictionaryRecord, ReferenceDictionary


class DictionaryAccessPermission:
    """Доступ к карточке справочника (чтение + записи)."""

    allowed_roles = {"ADMIN", "SPECIALIST", "OPERATOR"}


class DictionaryStructurePermission:
    """Изменение структуры справочника (без оператора)."""

    allowed_roles = {"ADMIN", "SPECIALIST"}


class DictionaryRecordsSearchJsonView(LoginRequiredRoleMixin, View):
    """Поиск записей справочника для оператора (динамический фильтр)."""

    allowed_roles = {"ADMIN", "SPECIALIST", "OPERATOR"}

    def get(self, request, dictionary_id):
        d = get_object_or_404(ReferenceDictionary, dictionary_id=dictionary_id)
        q = (request.GET.get("q") or "").strip()
        qs = DictionaryRecord.objects.filter(dictionary_id=dictionary_id).order_by("lookup_key")[:80]
        if q:
            qs = (
                DictionaryRecord.objects.filter(dictionary_id=dictionary_id)
                .filter(Q(lookup_key__icontains=q) | Q(payload_json__icontains=q))
                .order_by("lookup_key")[:80]
            )
        pk_col = _primary_column_key(d)
        out = []
        for r in qs:
            payload = r.payload()
            display = (payload.get(pk_col) or "").strip() if pk_col else ""
            label = f"{display} — {r.lookup_key}" if display else r.lookup_key
            out.append({"id": r.record_id, "lookup_key": r.lookup_key, "label": label[:200]})
        return JsonResponse({"results": out})


class UIDictionaryHomeView(LoginRequiredRoleMixin, View):
    allowed_roles = DictionaryAccessPermission.allowed_roles

    def get(self, request):
        rows = []
        for d in ReferenceDictionary.objects.all().order_by("name"):
            rows.append(
                {
                    "dictionary": d,
                    "col_count": d.columns.count(),
                    "rec_count": d.records.count(),
                }
            )
        return render(request, "ui/bpm/specialist/dictionaries_home.html", {"rows": rows})

    def post(self, request):
        action = request.POST.get("action", "")
        if action == "delete_dict" and request.enterprise_user.role_id.role_name in DictionaryStructurePermission.allowed_roles:
            d = ReferenceDictionary.objects.get(dictionary_id=request.POST["dictionary_id"])
            name = d.name
            d.delete()
            write_operation_log(user=request.enterprise_user, operation_result=f"Удалён справочник «{name}».")
            return redirect("ui-bpm-dictionaries")
        return redirect("ui-bpm-dictionaries")


class UIDictionaryCreateView(LoginRequiredRoleMixin, View):
    allowed_roles = DictionaryStructurePermission.allowed_roles

    def get(self, request):
        return render(request, "ui/bpm/specialist/dictionary_create.html", {})

    def post(self, request):
        name = request.POST.get("name", "").strip()
        if not name:
            return render(request, "ui/bpm/specialist/dictionary_create.html", {"error": "Укажите название"})
        d = ReferenceDictionary.objects.create(name=name)
        write_operation_log(user=request.enterprise_user, operation_result=f"Создан справочник «{name}».")
        return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)


def _primary_column_key(d: ReferenceDictionary) -> str:
    if getattr(d, "selection_column_key", None):
        return d.selection_column_key
    first = d.columns.order_by("sort_order", "key").first()
    return first.key if first else ""


def _derive_lookup_key(d: ReferenceDictionary, payload: dict, exclude_record_id: int | None) -> str:
    pk_col = _primary_column_key(d)
    raw = (payload.get(pk_col) or "").strip() if pk_col else ""
    base = slug_base(raw) if raw else ""
    if not base:
        base = slug_base(json.dumps(payload, sort_keys=True)[:80]) or "row"
    return unique_lookup_key(d.dictionary_id, base, exclude_record_id)


def _sync_payload_keys_for_dictionary(d: ReferenceDictionary):
    keys = list(d.columns.values_list("key", flat=True))
    for rec in d.records.all():
        data = rec.payload()
        changed = False
        for k in keys:
            if k not in data:
                data[k] = ""
                changed = True
        if changed:
            rec.payload_json = json.dumps(data, ensure_ascii=False)
            rec.save(update_fields=["payload_json"])


def _payload_from_post(request, d: ReferenceDictionary, record_id=None, prefix_new=False):
    keys = list(d.columns.order_by("sort_order", "key").values_list("key", flat=True))
    data = {}
    if not keys:
        return data
    if prefix_new:
        p = "newcell_"
    elif record_id:
        p = f"cell_{record_id}_"
    else:
        p = "newcell_"
    for k in keys:
        data[k] = (request.POST.get(f"{p}{k}", "") or "").strip()
    return data


class UIDictionaryDetailView(LoginRequiredRoleMixin, View):
    allowed_roles = DictionaryAccessPermission.allowed_roles

    def get(self, request, dictionary_id):
        d = get_object_or_404(
            ReferenceDictionary.objects.prefetch_related("columns", "records"),
            dictionary_id=dictionary_id,
        )
        columns = list(d.columns.order_by("sort_order", "key"))
        records_data = []
        for r in d.records.order_by("lookup_key"):
            records_data.append({"record": r, "cells": r.payload()})
        role_name = request.enterprise_user.role_id.role_name
        return render(
            request,
            "ui/bpm/specialist/dictionary_detail.html",
            {
                "dictionary": d,
                "columns": columns,
                "records_data": records_data,
                "error": request.GET.get("error", ""),
                "can_manage_structure": role_name in DictionaryStructurePermission.allowed_roles,
            },
        )

    def post(self, request, dictionary_id):
        d = get_object_or_404(ReferenceDictionary, dictionary_id=dictionary_id)
        action = request.POST.get("action", "")

        if action == "rename" and request.enterprise_user.role_id.role_name in DictionaryStructurePermission.allowed_roles:
            d.name = request.POST.get("name", d.name).strip() or d.name
            d.save(update_fields=["name"])
            write_operation_log(user=request.enterprise_user, operation_result=f"Переименован справочник «{d.name}».")
            return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)

        if action == "set_selection_column" and request.enterprise_user.role_id.role_name in DictionaryStructurePermission.allowed_roles:
            key = request.POST.get("selection_column_key", "").strip()
            if key and d.columns.filter(key=key).exists():
                d.selection_column_key = key
                d.save(update_fields=["selection_column_key"])
                for rec in d.records.all():
                    pl = rec.payload()
                    rec.lookup_key = _derive_lookup_key(d, pl, rec.record_id)
                    rec.save(update_fields=["lookup_key"])
                write_operation_log(
                    user=request.enterprise_user,
                    operation_result=f"Для «{d.name}» задано главное поле выбора: {key}.",
                )
            return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)

        if action == "add_column" and request.enterprise_user.role_id.role_name in DictionaryStructurePermission.allowed_roles:
            key = request.POST.get("col_key", "").strip()
            title = request.POST.get("col_title", "").strip() or key
            if key and not d.columns.filter(key=key).exists():
                nxt = (d.columns.aggregate(m=Max("sort_order"))["m"] or 0) + 1
                DictionaryColumn.objects.create(dictionary=d, key=key, title=title, sort_order=nxt)
                _sync_payload_keys_for_dictionary(d)
                if not d.selection_column_key:
                    d.selection_column_key = key
                    d.save(update_fields=["selection_column_key"])
                write_operation_log(user=request.enterprise_user, operation_result=f"Добавлена колонка «{key}» в «{d.name}».")
            return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)

        if action == "delete_column" and request.enterprise_user.role_id.role_name in DictionaryStructurePermission.allowed_roles:
            DictionaryColumn.objects.filter(column_id=request.POST.get("column_id"), dictionary=d).delete()
            write_operation_log(user=request.enterprise_user, operation_result=f"Удалена колонка в справочнике «{d.name}».")
            return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)

        if action == "add_record":
            payload = _payload_from_post(request, d, prefix_new=True)
            if not payload:
                return redirect(f"/ui/bpm/dictionaries/{d.dictionary_id}/?error=Добавьте+колонки")
            try:
                lk = _derive_lookup_key(d, payload, None)
                DictionaryRecord.objects.create(
                    dictionary=d,
                    lookup_key=lk,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
                write_operation_log(user=request.enterprise_user, operation_result=f"Добавлена запись в «{d.name}».")
            except IntegrityError:
                return redirect(f"/ui/bpm/dictionaries/{d.dictionary_id}/?error=Запись+с+таким+кодом+уже+есть")
            return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)

        if action == "save_record":
            rid = request.POST.get("record_id")
            rec = get_object_or_404(DictionaryRecord, record_id=rid, dictionary=d)
            payload = _payload_from_post(request, d, record_id=rid)
            try:
                rec.lookup_key = _derive_lookup_key(d, payload, rec.record_id)
                rec.payload_json = json.dumps(payload, ensure_ascii=False)
                rec.save()
                write_operation_log(user=request.enterprise_user, operation_result=f"Обновлена запись в «{d.name}».")
            except IntegrityError:
                return redirect(f"/ui/bpm/dictionaries/{d.dictionary_id}/?error=Конфликт+уникальности")
            return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)

        if action == "delete_record":
            rec = DictionaryRecord.objects.get(record_id=request.POST["record_id"], dictionary=d)
            lk = rec.lookup_key
            rec.delete()
            write_operation_log(user=request.enterprise_user, operation_result=f"Удалена запись «{lk}» из «{d.name}».")
            return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)

        return redirect("ui-bpm-dictionary-detail", dictionary_id=d.dictionary_id)
