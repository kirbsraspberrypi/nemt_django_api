# NEMT Ride API

This project is for NEMT Ride API only.

---

## Submission

This project is submitted as a GitHub repository. The commit history shows the progression of the implementation in meaningful, working increments:

1. Initial project setup — Django project structure, settings, `.env` config
2. User model — custom `AbstractBaseUser` with email login and role field
3. Ride and RideEvent models — with composite index on `(id_ride, created_at)`
4. Serializers — nested read serializers, write serializers with password hashing
5. Authentication — `IsAdminRole` permission class
6. Ride List API — filtering, sorting (pickup_time + Haversine distance), pagination
7. Performance — filtered `Prefetch` for `todays_ride_events`, `select_related` for users
8. Seed data management command — realistic test data matching the sample SQL report
9. Bonus SQL — trip duration report grouped by month and driver

Each commit represents a stable, working state of the project. No WIP or squashed commits.

A RESTful API for managing ride information, built with Django and Django REST Framework.

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+

### Installation

```
git clone <your-repo-url>
cd nemt_django_api

python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env          # then edit .env with your DB credentials

python3 manage.py migrate

python3 manage.py createsuperuser   # create your first admin user

# Optional: load sample data (drivers, riders, 30 rides with events)
python3 manage.py seed_data

python3 manage.py runserver
```

### Environment variables

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | `change-me-in-production` | Must be overridden in production |
| `DEBUG` | `True` | Set to `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list |
| `DB_NAME` | `nemt_django_api` | PostgreSQL database name |
| `DB_USER` | `postgres` | |
| `DB_PASSWORD` | `postgres` | |
| `DB_HOST` | `localhost` | |
| `DB_PORT` | `5432` | |

---

## Authentication

All endpoints require a valid token belonging to a user with `role = "admin"`.

**Obtain a token:**
```
POST /api/auth/token/
Content-Type: application/json

{"username": "admin@nemt_django_api.test", "password": "testpass123"}
```

**Use it in requests:**
```
Authorization: Token <your-token-here>
```

Non-admin tokens (riders, drivers) will receive a `403 Forbidden`.

---

## API Endpoints

### Rides — `/api/rides/`

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/rides/` | List rides (paginated, filterable, sortable) |
| `POST` | `/api/rides/` | Create a ride |
| `GET` | `/api/rides/{id}/` | Retrieve a single ride |
| `PUT` | `/api/rides/{id}/` | Replace a ride |
| `PATCH` | `/api/rides/{id}/` | Partial update |
| `DELETE` | `/api/rides/{id}/` | Delete a ride |

#### Filtering

| Query param | Example | Description |
|---|---|---|
| `status` | `?status=en-route` | Filter by ride status. Values: `en-route`, `pickup`, `dropoff` |
| `rider_email` | `?rider_email=alice@nemt_django_api.test` | Filter by the rider's email address |

#### Sorting

| Query param | Example | Description |
|---|---|---|
| `sort=pickup_time` | `?sort=pickup_time` | Ascending by scheduled pickup time |
| `sort=distance` | `?sort=distance&lat=37.77&lng=-122.41` | Ascending by distance from a GPS coordinate |

When using `sort=distance`, both `lat` and `lng` are required. Omitting either returns `400`.

Default sort (no `sort` param): newest `pickup_time` first.

#### Pagination

| Query param | Default | Max |
|---|---|---|
| `page` | `1` | — |
| `page_size` | `10` | `100` |

#### Sample response — `GET /api/rides/`

```json
{
  "count": 30,
  "next": "http://localhost:8000/api/rides/?page=2",
  "previous": null,
  "results": [
    {
      "id_ride": 1,
      "status": "en-route",
      "id_rider": 4,
      "id_driver": 2,
      "rider": {
        "id_user": 4,
        "email": "alice@nemt_django_api.test",
        "first_name": "Alice",
        "last_name": "Rider",
        "phone_number": "555-0010",
        "role": "rider"
      },
      "driver": {
        "id_user": 2,
        "email": "chris.h@nemt_django_api.test",
        "first_name": "Chris",
        "last_name": "H",
        "phone_number": "555-0001",
        "role": "driver"
      },
      "pickup_latitude": 37.821,
      "pickup_longitude": -122.397,
      "dropoff_latitude": 37.751,
      "dropoff_longitude": -122.443,
      "pickup_time": "2024-04-01T14:30:00Z",
      "todays_ride_events": [
        {
          "id_ride_event": 12,
          "description": "Status changed to pickup",
          "created_at": "2024-04-01T14:37:00Z"
        }
      ]
    }
  ]
}
```

`todays_ride_events` contains only events created in the last 24 hours. It will be an empty list for rides with no recent activity.

---

### Users — `/api/users/`

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/users/` | List users |
| `POST` | `/api/users/` | Create a user |
| `GET` | `/api/users/{id}/` | Retrieve a user |
| `PUT` | `/api/users/{id}/` | Replace a user |
| `PATCH` | `/api/users/{id}/` | Partial update |
| `DELETE` | `/api/users/{id}/` | Delete a user |

Password is write-only on create/update and never appears in any response.

---

## Design Decisions

### Custom User model

The spec defines `email` as the user identifier and adds a `role` field that Django's default `User` model doesn't have. Extending `AbstractBaseUser` from the start avoids the painful migration path that comes from trying to swap out the auth model after the initial migration has run.

The `role` field drives API access control entirely at the application level. It is intentionally decoupled from Django's `is_staff` and `is_superuser` flags so that Django admin access and API access can be managed independently.

### Query optimisation — `todays_ride_events`

The assessment explicitly flags that `ride_event` will be a very large table. The naive approach — serializing `ride.ride_events.all()` — would generate one additional query per ride on the page and load every historical event. Both are unacceptable.

The solution is a filtered `Prefetch`:

```python
Prefetch(
    "ride_events",
    queryset=RideEvent.objects.filter(created_at__gte=now - timedelta(hours=24)),
    to_attr="_todays_events_cache",
)
```

Django translates this into a single query:

```sql
SELECT * FROM ride_event
WHERE id_ride IN (<ids of rides on this page>)
  AND created_at >= <24 hours ago>
```

The serializer reads from `_todays_events_cache` directly. The full `ride_event` table is never touched.

**Total queries for `GET /api/rides/`: 3** — one count, one for rides + users via `select_related`, one for today's events via `Prefetch`.

### Distance sorting

The Haversine formula is injected as raw SQL via `queryset.extra(select={"distance": ...})` so `ORDER BY distance` executes inside PostgreSQL. This is important: if sorting happened in Python, Django would have to load every ride into memory before returning a page — completely defeating pagination.

Columns are table-qualified (`ride.pickup_latitude`) to prevent ambiguity if a JOIN is ever added to the queryset.

For a production deployment with millions of rows, adding PostGIS and an `ST_Distance` spatial index would improve this further.

### `RideEvent.created_at` — why not `auto_now_add`

`auto_now_add=True` silently discards any value you pass to `created_at` at save time. That makes seeding historical data for local development impossible and makes deterministic test setup painful. Using `default=timezone.now` gives identical behaviour in production (field is set automatically on creation) while still allowing explicit values when needed.

### Database indexes

- `ride.pickup_time` — single-column index supports `ORDER BY pickup_time` sorting.
- `ride_event(id_ride, created_at)` — composite index supports the 24-hour Prefetch filter. PostgreSQL can satisfy the `WHERE id_ride IN (...) AND created_at >= ?` predicate entirely from this index without touching the heap for most rows.

---

## Bonus SQL — Trips Over 1 Hour by Month and Driver

The `ride` table has no stored duration column. Trip duration is derived by finding the two `ride_event` rows for each ride — `'Status changed to pickup'` and `'Status changed to dropoff'` — and subtracting their `created_at` timestamps.

```sql
SELECT
    TO_CHAR(re_pickup.created_at AT TIME ZONE 'UTC', 'YYYY-MM') AS month,
    u.first_name || ' ' || LEFT(u.last_name, 1)                 AS driver,
    COUNT(*)                                                      AS count_of_trips_gt_1hr
FROM ride r
JOIN "user" u
    ON u.id_user = r.id_driver
JOIN ride_event re_pickup
    ON  re_pickup.id_ride     = r.id_ride
    AND re_pickup.description = 'Status changed to pickup'
JOIN ride_event re_dropoff
    ON  re_dropoff.id_ride     = r.id_ride
    AND re_dropoff.description = 'Status changed to dropoff'
WHERE
    re_dropoff.created_at - re_pickup.created_at > INTERVAL '1 hour'
GROUP BY
    TO_CHAR(re_pickup.created_at AT TIME ZONE 'UTC', 'YYYY-MM'),
    u.id_user,
    u.first_name,
    u.last_name
ORDER BY
    month  ASC,
    driver ASC;
```

The full query is also saved at `trips_over_1hr_by_month_driver.sql`.

---

## Project Structure

```
nemt_django_api/
├── manage.py
├── requirements.txt
├── .env.example
├── trips_over_1hr_by_month_driver.sql
│
├── wingz_project/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── users/
│   ├── migrations/
│   │   └── 0001_initial.py
│   ├── __init__.py
│   ├── admin.py
│   ├── models.py          # AbstractBaseUser with role field, email login
│   ├── serializers.py     # Read + write serializers, password hashing
│   ├── urls.py
│   └── views.py
│
└── rides/
    ├── migrations/
    │   ├── 0001_initial.py
    │   └── 0002_initial.py
    ├── management/
    │   └── commands/
    │       └── seed_data.py
    ├── __init__.py
    ├── admin.py
    ├── filters.py          # django-filter: status, rider_email
    ├── models.py           # Ride, RideEvent with composite index
    ├── pagination.py       # PageNumberPagination, page_size param
    ├── permissions.py      # IsAdminRole
    ├── serializers.py      # Nested user objects + todays_ride_events
    ├── urls.py
    └── views.py            # RideViewSet: filtering, sorting, 3-query budget
```
