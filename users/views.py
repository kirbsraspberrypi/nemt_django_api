from rest_framework import viewsets

from .models import User
from .serializers import UserSerializer, UserWriteSerializer


class UserViewSet(viewsets.ModelViewSet):
    # Explicit ordering avoids UnorderedObjectListWarning when pagination
    # is applied and keeps results deterministic across requests.
    queryset = User.objects.all().order_by("id_user")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return UserWriteSerializer
        return UserSerializer
