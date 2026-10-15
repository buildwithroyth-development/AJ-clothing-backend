# AJ-clothing-backend

API for AJ Clothing, built with Django + Django REST Framework. All data lives in **Firebase Realtime Database**, reached through the Firebase Admin SDK:

```
React app  ──(Firebase ID token)──▶  this API  ──(Admin SDK)──▶  Realtime Database
```

The app signs staff in with Firebase Authentication and sends the resulting ID token as `Authorization: Bearer <token>`. The API verifies it, checks that the user is listed under `staff/<uid>` in the database, and then does the work. The database rules deny all direct client access, so this API is the only way in.

## Setup

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows;  macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill it in. You need a **service-account key**: Firebase console → Project settings → Service accounts → *Generate new private key*. Put the whole JSON on one line in `FIREBASE_SERVICE_ACCOUNT_JSON` (or set `GOOGLE_APPLICATION_CREDENTIALS` to the file path locally). Never commit the key.
3. Make sure at least one staff user exists: Authentication → Users, then add `staff/<UID>` = `true` in Realtime Database.
4. Run:
   ```bash
   python manage.py runserver
   ```
   `GET /` returns `{"status": "ok", "firebase_configured": true}` when the credentials are present.

### Deploying on Vercel
Set `FIREBASE_DATABASE_URL`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `ALLOWED_HOSTS` (your API domain) and optionally `CORS_ALLOWED_ORIGINS` as project environment variables. Leave `DEBUG` unset.

## Who can sign in

People register in the app (Create account) and must verify their email. **Once the email is verified they can use the app straight away**, with no approval step.

To require approval instead, set `AUTO_APPROVE_VERIFIED_USERS=False`. Then only these users get in:

1. Anyone listed under `staff/<uid>` = `true` in Realtime Database.
2. Verified users whose email is in `STAFF_EMAILS` (comma separated).

Everyone else sees "Waiting for approval".

If Firebase is not configured the API **refuses requests** (HTTP 503). The built-in demo user and in-memory data exist only for local development, when `DEBUG=True` and no Firebase credentials are set.

## Endpoints (all under `/api/v1/`, all require a staff token)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `categories/` | List categories |
| GET / POST | `products/` | List / create a product (name + colour + size must be unique) |
| GET / PATCH / DELETE | `products/<id>/` | Read / edit / remove a product; changing `stock` logs a movement |
| POST | `products/<id>/restock/` | `{"amount": 5, "reason": "..."}` adds stock |
| GET | `products/<id>/history/` | Stock movements for a product |
| GET / POST | `sales/` | List bills / create a bill |
| GET | `sales/<id>/` | One bill |
| GET | `stock_movements/` | Latest movements across all products. `?since=<ISO time>` keeps only newer ones (the dashboard sends the start of today), `?limit=<n>` (default 10, max 200) |
| GET | `me/` | Any signed-in user: `{email, email_verified, approved}` (used by the app to show the right screen) |

A bill is created with `{"items": [{"id": 12, "qty": 2}], "discount_percent": 10, "round_off": true, "total": 1200, "payment_method": "Cash", "customer_name": "Asha", "customer_mobile": "9876543210", "customer_email": ""}`. `customer_name` and `customer_mobile` are required, `customer_email` is optional, and `discount_percent` must be between 0 and 100 (otherwise the bill is rejected). Prices and totals are **recomputed on the server** from the live product records; any prices sent by the client are ignored. `total` is only used when `round_off` is true.

### How billing stays consistent
Stock is deducted per product in a transaction (never below zero), the bill number comes from an atomic counter, and the sale plus its stock movements are written in one multi-path update. If any step fails, the stock already deducted is put back. Sales and stock history are never edited or deleted by the API.

## Tests
The business logic (`products/services.py`) has no Django dependency and is tested against an in-memory fake of Firebase:
```bash
python -m unittest products.tests.test_store
```
