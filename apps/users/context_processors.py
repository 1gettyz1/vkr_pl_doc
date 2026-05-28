from apps.users.permissions import get_request_user


def current_enterprise_user(request):
    return {"current_enterprise_user": get_request_user(request)}
