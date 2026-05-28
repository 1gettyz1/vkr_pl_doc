from rest_framework.permissions import BasePermission

from apps.users.models import Users


def get_request_user(request):
    params = getattr(request, "query_params", getattr(request, "GET", {}))
    user_id = request.session.get("user_id") or request.headers.get("X-User-Id") or params.get("user_id")
    if not user_id:
        return None
    try:
        return Users.objects.select_related("role_id").get(user_id=user_id)
    except Users.DoesNotExist:
        return None


class RoleBasedPermission(BasePermission):
    allowed_roles = set()

    def has_permission(self, request, view):
        if not self.allowed_roles:
            return True
        enterprise_user = get_request_user(request)
        if not enterprise_user:
            return False
        request.enterprise_user = enterprise_user
        return enterprise_user.role_id.role_name in self.allowed_roles
