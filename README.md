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

A RESTful API for managing ride information, built with Django and Django REST Framework.

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+

### Installation

```
git clone https://github.com/kirbsraspberrypi/nemt_django_api.git
cd nemt_django_api

python3 -m venv env
source env/bin/activate      # Windows: venv\Scripts\activate

pip3 install -r requirements.txt

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

---

# Wingz Ride API — Endpoint Testing Guide

All commands below assume the server is running at `http://127.0.0.1:8000/`.  
Run these from a second terminal while `python3 manage.py runserver` is active.

---

## 0. Setup — Store Your Token as a Variable

Get your token once and store it so you don't paste it on every command.

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin@wingz.test", "password": "testpass123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")

echo $TOKEN
```

---

## 1. Authentication

### 1.1 Get token — valid admin credentials
```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin@wingz.test", "password": "testpass123"}'
```
**Expected:** `200 OK` with `{"token": "..."}`

---

### 1.2 Get token — wrong password
```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin@wingz.test", "password": "wrongpassword"}'
```
**Expected:** `400 Bad Request`
```json
{"non_field_errors": ["Unable to log in with provided credentials."]}
```

---

### 1.3 Get token — non-existent user
```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "nobody@wingz.test", "password": "testpass123"}'
```
**Expected:** `400 Bad Request`

---

### 1.4 Access API with no token
```bash
curl -s http://127.0.0.1:8000/api/rides/
```
**Expected:** `401 Unauthorized`
```json
{"detail": "Authentication credentials were not provided."}
```

---

### 1.5 Access API with invalid token
```bash
curl -s http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token invalidtokenstring"
```
**Expected:** `401 Unauthorized`
```json
{"detail": "Invalid token."}
```

---

### 1.6 Access API with a non-admin token (rider or driver)
```bash
# First get a rider token
RIDER_TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice@wingz.test", "password": "testpass123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")

# Then use it — should be denied
curl -s http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $RIDER_TOKEN"
```
**Expected:** `403 Forbidden`
```json
{"detail": "Only users with the admin role can access this API."}
```

---

## 2. Rides — List

### 2.1 Default list (newest pickup_time first)
```bash
curl -s http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — paginated list, `todays_ride_events` present on each ride.

---

### 2.2 Pagination — page 1, 5 per page
```bash
curl -s "http://127.0.0.1:8000/api/rides/?page=1&page_size=5" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — `count`, `next`, `previous`, and 5 results.

---

### 2.3 Pagination — page 2
```bash
curl -s "http://127.0.0.1:8000/api/rides/?page=2&page_size=5" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — next 5 results.

---

### 2.4 Pagination — page beyond last page
```bash
curl -s "http://127.0.0.1:8000/api/rides/?page=9999&page_size=10" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found`
```json
{"detail": "Invalid page."}
```

---

### 2.5 Pagination — page_size exceeds max (100)
```bash
curl -s "http://127.0.0.1:8000/api/rides/?page_size=999" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — returns max 100 results, ignores the excess.

---

### 2.6 Pagination — invalid page value
```bash
curl -s "http://127.0.0.1:8000/api/rides/?page=abc" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found`
```json
{"detail": "Invalid page."}
```

---

## 3. Rides — Filtering

### 3.1 Filter by status — en-route
```bash
curl -s "http://127.0.0.1:8000/api/rides/?status=en-route" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — only rides with `status = "en-route"`.

---

### 3.2 Filter by status — pickup
```bash
curl -s "http://127.0.0.1:8000/api/rides/?status=pickup" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — only rides with `status = "pickup"`.

---

### 3.3 Filter by status — dropoff
```bash
curl -s "http://127.0.0.1:8000/api/rides/?status=dropoff" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — only rides with `status = "dropoff"`.

---

### 3.4 Filter by status — case insensitive
```bash
curl -s "http://127.0.0.1:8000/api/rides/?status=EN-ROUTE" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — same results as lowercase `en-route`.

---

### 3.5 Filter by status — invalid value
```bash
curl -s "http://127.0.0.1:8000/api/rides/?status=flying" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — empty results list (no match, not an error).
```json
{"count": 0, "next": null, "previous": null, "results": []}
```

---

### 3.6 Filter by rider email — exact match
```bash
curl -s "http://127.0.0.1:8000/api/rides/?rider_email=alice@wingz.test" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — only rides where the rider's email matches.

---

### 3.7 Filter by rider email — case insensitive
```bash
curl -s "http://127.0.0.1:8000/api/rides/?rider_email=ALICE@WINGZ.TEST" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — same results as lowercase.

---

### 3.8 Filter by rider email — no match
```bash
curl -s "http://127.0.0.1:8000/api/rides/?rider_email=nobody@nowhere.com" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — empty results list.

---

### 3.9 Combined filter — status + rider_email
```bash
curl -s "http://127.0.0.1:8000/api/rides/?status=en-route&rider_email=alice@wingz.test" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — only rides matching both conditions.

---

## 4. Rides — Sorting

### 4.1 Sort by pickup_time (ascending)
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=pickup_time" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — oldest pickup first. Confirm `pickup_time` values increase across results.

---

### 4.2 Sort by distance from a GPS point
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=distance&lat=37.7749&lng=-122.4194" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — rides ordered by distance from San Francisco city centre, closest first.

---

### 4.3 Sort by distance — missing lat
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=distance&lng=-122.4194" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `400 Bad Request`
```json
{"detail": "Both 'lat' and 'lng' query params are required when sorting by distance."}
```

---

### 4.4 Sort by distance — missing lng
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=distance&lat=37.7749" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `400 Bad Request`
```json
{"detail": "Both 'lat' and 'lng' query params are required when sorting by distance."}
```

---

### 4.5 Sort by distance — missing both lat and lng
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=distance" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `400 Bad Request`

---

### 4.6 Sort by distance — non-numeric lat/lng
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=distance&lat=abc&lng=xyz" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `400 Bad Request`
```json
{"detail": "'lat' and 'lng' must be valid floating-point numbers."}
```

---

### 4.7 Sort by distance — extreme coordinates (still valid)
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=distance&lat=90.0&lng=180.0" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — valid coordinates, results ordered by distance from that point.

---

### 4.8 Sort — unrecognised sort value (falls back to default)
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=random" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — returns default sort (newest pickup first).

---

### 4.9 Sort + filter + pagination combined
```bash
curl -s "http://127.0.0.1:8000/api/rides/?sort=pickup_time&status=en-route&page=1&page_size=5" \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — filtered by status, sorted by pickup_time, 5 per page.

---

## 5. Rides — Retrieve

### 5.1 Retrieve a single ride
```bash
curl -s http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — single ride object with nested `rider`, `driver`, and `todays_ride_events`.

---

### 5.2 Retrieve a ride — ID does not exist
```bash
curl -s http://127.0.0.1:8000/api/rides/99999/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found`
```json
{"detail": "No Ride matches the given query."}
```

---

### 5.3 Retrieve a ride — non-integer ID
```bash
curl -s http://127.0.0.1:8000/api/rides/abc/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found`

---

## 6. Rides — Create

### 6.1 Create a valid ride
```bash
curl -s -X POST http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "en-route",
    "id_rider": 5,
    "id_driver": 2,
    "pickup_latitude": 37.7749,
    "pickup_longitude": -122.4194,
    "dropoff_latitude": 37.7600,
    "dropoff_longitude": -122.4400,
    "pickup_time": "2024-06-01T09:00:00Z"
  }'
```
**Expected:** `201 Created` — returns the new ride object with assigned `id_ride`.

---

### 6.2 Create ride — missing required field (status)
```bash
curl -s -X POST http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id_rider": 5,
    "id_driver": 2,
    "pickup_latitude": 37.7749,
    "pickup_longitude": -122.4194,
    "dropoff_latitude": 37.7600,
    "dropoff_longitude": -122.4400,
    "pickup_time": "2024-06-01T09:00:00Z"
  }'
```
**Expected:** `400 Bad Request`
```json
{"status": ["This field is required."]}
```

---

### 6.3 Create ride — invalid status value
```bash
curl -s -X POST http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "flying",
    "id_rider": 5,
    "id_driver": 2,
    "pickup_latitude": 37.7749,
    "pickup_longitude": -122.4194,
    "dropoff_latitude": 37.7600,
    "dropoff_longitude": -122.4400,
    "pickup_time": "2024-06-01T09:00:00Z"
  }'
```
**Expected:** `400 Bad Request`
```json
{"status": ["\"flying\" is not a valid choice."]}
```

---

### 6.4 Create ride — id_rider does not exist
```bash
curl -s -X POST http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "en-route",
    "id_rider": 99999,
    "id_driver": 2,
    "pickup_latitude": 37.7749,
    "pickup_longitude": -122.4194,
    "dropoff_latitude": 37.7600,
    "dropoff_longitude": -122.4400,
    "pickup_time": "2024-06-01T09:00:00Z"
  }'
```
**Expected:** `400 Bad Request`
```json
{"id_rider": ["Invalid pk \"99999\" - object does not exist."]}
```

---

### 6.5 Create ride — invalid pickup_time format
```bash
curl -s -X POST http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "en-route",
    "id_rider": 5,
    "id_driver": 2,
    "pickup_latitude": 37.7749,
    "pickup_longitude": -122.4194,
    "dropoff_latitude": 37.7600,
    "dropoff_longitude": -122.4400,
    "pickup_time": "not-a-date"
  }'
```
**Expected:** `400 Bad Request`
```json
{"pickup_time": ["Datetime has wrong format."]}
```

---

### 6.6 Create ride — empty body
```bash
curl -s -X POST http://127.0.0.1:8000/api/rides/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```
**Expected:** `400 Bad Request` — all required fields listed as errors.

---

## 7. Rides — Update

### 7.1 Full update (PUT) — valid
```bash
curl -s -X PUT http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "pickup",
    "id_rider": 5,
    "id_driver": 2,
    "pickup_latitude": 37.7749,
    "pickup_longitude": -122.4194,
    "dropoff_latitude": 37.7600,
    "dropoff_longitude": -122.4400,
    "pickup_time": "2024-06-01T09:00:00Z"
  }'
```
**Expected:** `200 OK` — returns the updated ride object.

---

### 7.2 Full update (PUT) — missing field
```bash
curl -s -X PUT http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "pickup"
  }'
```
**Expected:** `400 Bad Request` — remaining required fields listed as errors.

---

### 7.3 Partial update (PATCH) — update status only
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "dropoff"}'
```
**Expected:** `200 OK` — only status changed, all other fields unchanged.

---

### 7.4 Partial update (PATCH) — update pickup_time only
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pickup_time": "2024-12-01T08:00:00Z"}'
```
**Expected:** `200 OK`

---

### 7.5 Update — ride ID does not exist
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/rides/99999/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "dropoff"}'
```
**Expected:** `404 Not Found`

---

## 8. Rides — Delete

### 8.1 Delete a ride — valid ID
```bash
curl -s -X DELETE http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `204 No Content` — empty body.

---

### 8.2 Delete a ride — ID does not exist
```bash
curl -s -X DELETE http://127.0.0.1:8000/api/rides/99999/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found`

---

### 8.3 Delete a ride — confirm it's gone
```bash
curl -s http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found` (after deleting ride 1 above).

---

## 9. Users — List & Retrieve

### 9.1 List all users
```bash
curl -s http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — paginated list. Password field is NOT present in any user object.

---

### 9.2 Retrieve a single user
```bash
curl -s http://127.0.0.1:8000/api/users/1/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `200 OK` — single user object, no password field.

---

### 9.3 Retrieve a user — ID does not exist
```bash
curl -s http://127.0.0.1:8000/api/users/99999/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found`

---

## 10. Users — Create

### 10.1 Create a valid user
```bash
curl -s -X POST http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newdriver@wingz.test",
    "password": "securepass123",
    "first_name": "New",
    "last_name": "Driver",
    "phone_number": "555-9999",
    "role": "driver"
  }'
```
**Expected:** `201 Created` — user object returned, no password in response.

---

### 10.2 Create user — duplicate email
```bash
curl -s -X POST http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@wingz.test",
    "password": "securepass123",
    "first_name": "Duplicate",
    "last_name": "Admin",
    "phone_number": "555-0000",
    "role": "admin"
  }'
```
**Expected:** `400 Bad Request`
```json
{"email": ["user with this email already exists."]}
```

---

### 10.3 Create user — password too short (min 8 chars)
```bash
curl -s -X POST http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "shortpass@wingz.test",
    "password": "abc",
    "first_name": "Short",
    "last_name": "Pass",
    "role": "rider"
  }'
```
**Expected:** `400 Bad Request`
```json
{"password": ["Ensure this field has at least 8 characters."]}
```

---

### 10.4 Create user — missing email
```bash
curl -s -X POST http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "password": "securepass123",
    "first_name": "No",
    "last_name": "Email",
    "role": "rider"
  }'
```
**Expected:** `400 Bad Request`
```json
{"email": ["This field is required."]}
```

---

### 10.5 Create user — invalid role value
```bash
curl -s -X POST http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "badrole@wingz.test",
    "password": "securepass123",
    "first_name": "Bad",
    "last_name": "Role",
    "role": "superuser"
  }'
```
**Expected:** `400 Bad Request`
```json
{"role": ["\"superuser\" is not a valid choice."]}
```

---

## 11. Users — Update

### 11.1 Full update (PUT)
```bash
curl -s -X PUT http://127.0.0.1:8000/api/users/2/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "chris.h@wingz.test",
    "password": "newpassword123",
    "first_name": "Chris",
    "last_name": "H",
    "phone_number": "555-1111",
    "role": "driver"
  }'
```
**Expected:** `200 OK`

---

### 11.2 Partial update (PATCH) — phone number only
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/users/2/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "555-8888"}'
```
**Expected:** `200 OK` — only phone_number changed.

---

### 11.3 Partial update (PATCH) — change role to admin
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/users/5/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```
**Expected:** `200 OK`

---

### 11.4 Update user — ID does not exist
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/users/99999/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "555-0000"}'
```
**Expected:** `404 Not Found`

---

## 12. Users — Delete

### 12.1 Delete a user — valid ID
```bash
curl -s -X DELETE http://127.0.0.1:8000/api/users/6/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `204 No Content`

---

### 12.2 Delete a user — ID does not exist
```bash
curl -s -X DELETE http://127.0.0.1:8000/api/users/99999/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `404 Not Found`

---

## 13. todays_ride_events Field — Edge Cases

### 13.1 Ride with events in the last 24 hours
```bash
curl -s http://127.0.0.1:8000/api/rides/1/ \
  -H "Authorization: Token $TOKEN"
```
**Expected:** `todays_ride_events` contains events. Example:
```json
"todays_ride_events": [
  {
    "id_ride_event": 1,
    "description": "Status changed to pickup",
    "created_at": "2024-06-01T09:05:00Z"
  }
]
```

---

### 13.2 Ride with no events in the last 24 hours
For rides whose events are older than 24 hours (most seeded rides), `todays_ride_events` must be empty — not null, not missing.

```bash
curl -s http://127.0.0.1:8000/api/rides/?sort=pickup_time \
  -H "Authorization: Token $TOKEN"
```
**Expected:** Oldest rides show:
```json
"todays_ride_events": []
```

---

## 14. Quick Reference

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | OK — successful GET, PUT, PATCH |
| `201` | Created — successful POST |
| `204` | No Content — successful DELETE |
| `400` | Bad Request — validation error |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — valid token but not admin role |
| `404` | Not Found — resource doesn't exist |

### All Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| `POST` | `/api/auth/token/` | Obtain auth token |
| `GET` | `/api/rides/` | List rides |
| `POST` | `/api/rides/` | Create a ride |
| `GET` | `/api/rides/{id}/` | Retrieve a ride |
| `PUT` | `/api/rides/{id}/` | Full update a ride |
| `PATCH` | `/api/rides/{id}/` | Partial update a ride |
| `DELETE` | `/api/rides/{id}/` | Delete a ride |
| `GET` | `/api/users/` | List users |
| `POST` | `/api/users/` | Create a user |
| `GET` | `/api/users/{id}/` | Retrieve a user |
| `PUT` | `/api/users/{id}/` | Full update a user |
| `PATCH` | `/api/users/{id}/` | Partial update a user |
| `DELETE` | `/api/users/{id}/` | Delete a user |

### Query Parameters for `GET /api/rides/`

| Param | Example | Description |
|-------|---------|-------------|
| `status` | `?status=en-route` | Filter by status. Values: `en-route`, `pickup`, `dropoff` |
| `rider_email` | `?rider_email=alice@wingz.test` | Filter by rider email (case-insensitive) |
| `sort` | `?sort=pickup_time` | Sort ascending by pickup time |
| `sort` | `?sort=distance&lat=37.77&lng=-122.41` | Sort by distance from GPS point |
| `page` | `?page=2` | Page number (default: 1) |
| `page_size` | `?page_size=5` | Results per page (default: 10, max: 100) |
