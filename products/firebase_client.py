"""Firebase Admin SDK setup (lazy, so importing this module never needs credentials)."""
import json
import os

from .services import Store

_store = None


def _ensure_app():
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    database_url = os.environ.get('FIREBASE_DATABASE_URL')
    if not database_url:
        raise RuntimeError('FIREBASE_DATABASE_URL is not set.')

    raw = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    if raw:
        cred = credentials.Certificate(json.loads(raw))
    else:
        # Falls back to GOOGLE_APPLICATION_CREDENTIALS (path to a key file) or the platform default.
        cred = credentials.ApplicationDefault()
    return firebase_admin.initialize_app(cred, {'databaseURL': database_url})


def is_configured():
    return bool(
        os.environ.get('FIREBASE_DATABASE_URL')
        and (os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
    )


def verify_id_token(token):
    from firebase_admin import auth

    _ensure_app()
    return auth.verify_id_token(token)


def get_store():
    global _store
    if _store is None:
        from firebase_admin import db

        _ensure_app()
        _store = Store(db)
    return _store
