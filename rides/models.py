from django.db import models
from django.conf import settings
from django.utils import timezone


class Ride(models.Model):
    STATUS_EN_ROUTE = "en-route"
    STATUS_PICKUP = "pickup"
    STATUS_DROPOFF = "dropoff"

    STATUS_CHOICES = [
        (STATUS_EN_ROUTE, "En Route"),
        (STATUS_PICKUP, "Pickup"),
        (STATUS_DROPOFF, "Dropoff"),
    ]

    id_ride = models.AutoField(primary_key=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Two FKs to the same User table — Django requires distinct related_names.
    id_rider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="rides_as_rider",
        db_column="id_rider",
    )
    id_driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="rides_as_driver",
        db_column="id_driver",
    )

    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    dropoff_latitude = models.FloatField()
    dropoff_longitude = models.FloatField()
    pickup_time = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "ride"

    def __str__(self):
        return f"Ride {self.id_ride} [{self.status}]"


class RideEvent(models.Model):
    """
    Append-only event log for a ride. The two descriptions that matter for
    reporting are 'Status changed to pickup' and 'Status changed to dropoff'.
    """

    id_ride_event = models.AutoField(primary_key=True)
    id_ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name="ride_events",
        db_column="id_ride",
    )
    description = models.CharField(max_length=255)

    # We intentionally avoid auto_now_add here. auto_now_add silently drops
    # any value passed to created_at at save time, making it impossible to
    # seed historical data or write deterministic tests. default=timezone.now
    # gives the same auto-set-on-create behaviour in production while still
    # allowing explicit values when needed.
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "ride_event"
        indexes = [
            # Composite index covers the per-ride 24-hour filter used in
            # todays_ride_events. Handles both the IN-list on id_ride and
            # the range filter on created_at in a single index scan.
            models.Index(
                fields=["id_ride", "created_at"],
                name="idx_ride_event_ride_created",
            ),
        ]

    def __str__(self):
        return f"RideEvent {self.id_ride_event} — {self.description}"
