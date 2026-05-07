from rest_framework import serializers

from users.serializers import UserSerializer
from .models import Ride, RideEvent


class RideEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideEvent
        fields = ["id_ride_event", "description", "created_at"]


class RideSerializer(serializers.ModelSerializer):
    """
    Read serializer for the ride list/detail endpoints.

    rider and driver are full nested User objects (sourced from the FK fields)
    so the consumer gets everything they need without a second request.

    todays_ride_events reads from the _todays_events_cache attribute that the
    viewset's Prefetch populates. We never touch ride_events.all() here, so
    the full ride_event table is never loaded.
    """

    rider = UserSerializer(source="id_rider", read_only=True)
    driver = UserSerializer(source="id_driver", read_only=True)
    todays_ride_events = serializers.SerializerMethodField()

    class Meta:
        model = Ride
        fields = [
            "id_ride",
            "status",
            "id_rider",
            "id_driver",
            "rider",
            "driver",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
            "todays_ride_events",
        ]
        # The FK integer fields are read-only on this serializer — writes go
        # through RideWriteSerializer which accepts them as writable IDs.
        read_only_fields = ["id_ride", "id_rider", "id_driver"]

    def get_todays_ride_events(self, obj):
        # _todays_events_cache is set by the Prefetch(to_attr=...) in the
        # viewset. The fallback to an empty list keeps this safe if the
        # serializer is ever called without the prefetch (e.g. in unit tests
        # that construct a Ride object directly).
        events = getattr(obj, "_todays_events_cache", None)
        if events is None:
            events = []
        return RideEventSerializer(events, many=True).data


class RideWriteSerializer(serializers.ModelSerializer):
    """
    Used for POST, PUT, and PATCH. Accepts id_rider and id_driver as
    integer FK values and validates they reference existing users.
    """

    class Meta:
        model = Ride
        fields = [
            "status",
            "id_rider",
            "id_driver",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
        ]
