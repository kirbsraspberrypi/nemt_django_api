"""
Management command: python manage.py seed_data

Creates a realistic dataset for local development and manual testing.
Matches the driver names from the assessment's sample SQL report output
(Chris H, Howard Y, Randy W) so you can verify the bonus query immediately.

Safe to run multiple times — checks for existing data first.
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import User
from rides.models import Ride, RideEvent


STATUSES = [Ride.STATUS_EN_ROUTE, Ride.STATUS_PICKUP, Ride.STATUS_DROPOFF]


class Command(BaseCommand):
    help = "Seed the database with sample users, rides, and ride events."

    def handle(self, *args, **options):
        self._create_users()
        self._create_rides()
        self.stdout.write(self.style.SUCCESS("Seed data created successfully."))

    def _create_users(self):
        users_data = [
            {
                "email": "admin@wingz.test",
                "first_name": "Admin",
                "last_name": "User",
                "role": User.ROLE_ADMIN,
                "phone_number": "555-0000",
            },
            {
                "email": "chris.h@wingz.test",
                "first_name": "Chris",
                "last_name": "H",
                "role": User.ROLE_DRIVER,
                "phone_number": "555-0001",
            },
            {
                "email": "howard.y@wingz.test",
                "first_name": "Howard",
                "last_name": "Y",
                "role": User.ROLE_DRIVER,
                "phone_number": "555-0002",
            },
            {
                "email": "randy.w@wingz.test",
                "first_name": "Randy",
                "last_name": "W",
                "role": User.ROLE_DRIVER,
                "phone_number": "555-0003",
            },
            {
                "email": "alice@wingz.test",
                "first_name": "Alice",
                "last_name": "Rider",
                "role": User.ROLE_RIDER,
                "phone_number": "555-0010",
            },
            {
                "email": "bob@wingz.test",
                "first_name": "Bob",
                "last_name": "Rider",
                "role": User.ROLE_RIDER,
                "phone_number": "555-0011",
            },
        ]

        for data in users_data:
            if not User.objects.filter(email=data["email"]).exists():
                User.objects.create_user(password="testpass123", **data)
                self.stdout.write(f"  Created user: {data['email']}")
            else:
                self.stdout.write(f"  Skipped (exists): {data['email']}")

    def _create_rides(self):
        if Ride.objects.exists():
            self.stdout.write("  Rides already exist — skipping ride creation.")
            return

        drivers = list(User.objects.filter(role=User.ROLE_DRIVER))
        riders = list(User.objects.filter(role=User.ROLE_RIDER))
        now = timezone.now()

        rides_created = 0
        for i in range(30):
            # Spread pickup times across the past 90 days so the bonus SQL
            # query produces results across multiple months.
            pickup_time = now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23))

            ride = Ride.objects.create(
                status=random.choice(STATUSES),
                id_rider=random.choice(riders),
                id_driver=random.choice(drivers),
                pickup_latitude=37.7749 + random.uniform(-0.15, 0.15),
                pickup_longitude=-122.4194 + random.uniform(-0.15, 0.15),
                dropoff_latitude=37.7749 + random.uniform(-0.15, 0.15),
                dropoff_longitude=-122.4194 + random.uniform(-0.15, 0.15),
                pickup_time=pickup_time,
            )

            # Pickup event — a few minutes after the scheduled pickup_time.
            pickup_event_time = pickup_time + timedelta(minutes=random.randint(3, 15))
            RideEvent.objects.create(
                id_ride=ride,
                description="Status changed to pickup",
                created_at=pickup_event_time,
            )

            # Dropoff event — 30 to 150 minutes later, so roughly half the
            # rides exceed the 1-hour threshold in the bonus SQL report.
            dropoff_minutes = random.randint(30, 150)
            RideEvent.objects.create(
                id_ride=ride,
                description="Status changed to dropoff",
                created_at=pickup_event_time + timedelta(minutes=dropoff_minutes),
            )

            rides_created += 1

        self.stdout.write(f"  Created {rides_created} rides with pickup and dropoff events.")
