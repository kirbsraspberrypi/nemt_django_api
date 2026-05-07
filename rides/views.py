from datetime import timedelta

from django.db.models import Prefetch
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from .filters import RideFilter
from .models import Ride, RideEvent
from .serializers import RideSerializer, RideWriteSerializer


def _haversine_sql(lat: float, lng: float) -> str:
    """
    Returns a raw SQL expression that computes the great-circle distance
    in kilometres between a ride's pickup location and the given coordinate.

    Columns are table-qualified (ride.pickup_latitude / ride.pickup_longitude)
    to prevent ambiguity if Django ever introduces a JOIN in the queryset.

    We use the Haversine formula entirely in SQL so that ORDER BY happens
    inside the database — never in Python. On a large ride table, pulling
    all rows into memory to sort them would be unusable.

    If PostGIS is available in your deployment environment, replacing this
    with ST_Distance and a GIST spatial index will be significantly faster.
    """
    r = 6371  # Earth radius in km
    return f"""
        {r} * 2 * ASIN(SQRT(
            POWER(SIN(RADIANS(ride.pickup_latitude  - ({lat}))  / 2), 2) +
            COS(RADIANS({lat})) *
            COS(RADIANS(ride.pickup_latitude)) *
            POWER(SIN(RADIANS(ride.pickup_longitude - ({lng})) / 2), 2)
        ))
    """


class RideViewSet(viewsets.ModelViewSet):
    """
    Full CRUD surface for Ride, plus the optimised list endpoint.

    Query budget for GET /rides/:
      Query 1 — COUNT(*) for pagination total
      Query 2 — SELECT ride + rider + driver (select_related joins User twice)
      Query 3 — SELECT ride_events WHERE id_ride IN (...) AND created_at >= 24h ago

    The Prefetch queryset is pre-filtered, so we never load the full
    ride_event table into memory regardless of how large it grows.
    """

    filter_backends = [DjangoFilterBackend]
    filterset_class = RideFilter

    def get_queryset(self):
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)

        todays_events_prefetch = Prefetch(
            "ride_events",
            queryset=RideEvent.objects.filter(created_at__gte=twenty_four_hours_ago),
            to_attr="_todays_events_cache",
        )

        qs = (
            Ride.objects
            .select_related("id_rider", "id_driver")
            .prefetch_related(todays_events_prefetch)
        )

        return self._apply_ordering(qs)

    def _apply_ordering(self, qs):
        sort = self.request.query_params.get("sort")

        if sort == "pickup_time":
            return qs.order_by("pickup_time")

        if sort == "distance":
            lat = self.request.query_params.get("lat")
            lng = self.request.query_params.get("lng")

            if not lat or not lng:
                raise ValidationError(
                    "Both 'lat' and 'lng' query params are required when sorting by distance."
                )

            try:
                lat = float(lat)
                lng = float(lng)
            except ValueError:
                raise ValidationError("'lat' and 'lng' must be valid floating-point numbers.")

            # extra(select=...) injects the Haversine expression as a named
            # column so we can reference it in ORDER BY. annotate() with
            # RawSQL would also work but extra() is more concise here and
            # equally safe since lat/lng are validated floats, not raw strings.
            return qs.extra(
                select={"distance": _haversine_sql(lat, lng)}
            ).order_by("distance")

        # Default: newest pickups first
        return qs.order_by("-pickup_time")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return RideWriteSerializer
        return RideSerializer
