from django import template

register = template.Library()

ROLE_LABELS = {
    "ADMIN": "Администратор",
    "SPECIALIST": "Специалист по автоматизации",
    "OPERATOR": "Оператор",
}

STATUS_LABELS = {
    "draft": "Черновик",
    "filled": "Заполнен",
    "generated": "Сформирован",
    "archived": "Архивирован",
}


@register.filter
def role_ru(value):
    return ROLE_LABELS.get(value, value)


@register.filter
def status_ru(value):
    return STATUS_LABELS.get(value, value)


@register.filter
def lookupdict(d, key):
    if not key or not isinstance(d, dict):
        return ""
    v = d.get(key)
    return "" if v is None else v
