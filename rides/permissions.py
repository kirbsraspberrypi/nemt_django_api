from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """
    Grants access only to authenticated users whose role is 'admin'.
    This is intentionally separate from Django's is_staff/is_superuser flags
    so that role management stays within the application layer.
    """

    message = "Only users with the admin role can access this API."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )
