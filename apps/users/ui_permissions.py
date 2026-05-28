from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from apps.users.permissions import get_request_user


class LoginRequiredRoleMixin:
    allowed_roles = None

    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        user = get_request_user(request)
        if not user:
            return redirect("login-page")
        request.enterprise_user = user
        if self.allowed_roles and user.role_id.role_name not in self.allowed_roles:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)
