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
| GET | `stock_movements/` | Latest 10 movements across all products |

A bill is created with `{"items": [{"id": 12, "qty": 2}], "discount_percent": 10, "round_off": true, "total": 1200, "payment_method": "Cash", "customer_name": "", "customer_mobile": ""}`. Prices and totals are **recomputed on the server** from the live product records; any prices sent by the client are ignored. `total` is only used when `round_off` is true.

### How billing stays consistent
Stock is deducted per product in a transaction (never below zero), the bill number comes from an atomic counter, and the sale plus its stock movements are written in one multi-path update. If any step fails, the stock already deducted is put back. Sales and stock history are never edited or deleted by the API.

## Tests
The business logic (`products/services.py`) has no Django dependency and is tested against an in-memory fake of Firebase:
```bash
python -m unittest products.tests.test_store
```
