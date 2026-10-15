"""Firebase Admin SDK setup (lazy, so importing this module never needs credentials)."""
import json
import os

from .services import Store

_store = None


class TokenError(Exception):
    """The sign-in token itself is bad: expired, malformed or revoked."""


class ProjectMismatch(Exception):
    """The token was issued for a different Firebase project than the server's credentials."""


def _ensure_app():
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    database_url = os.environ.get('FIREBASE_DATABASE_URL') or os.environ.get('DATABASE_URL')
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
    try:
        import firebase_admin
    except ImportError:
        return False
    return bool(
        (os.environ.get('FIREBASE_DATABASE_URL') or os.environ.get('DATABASE_URL'))
        and (os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
    )


def verify_id_token(token):
    if not is_configured():
        return {'uid': 'dev-staff-1', 'email': 'dev@ajclothing.com'}

    from firebase_admin import auth

    # Problems starting Firebase (bad key, wrong URL...) are raised as they are: they are
    # configuration errors, not a problem with the person's sign-in.
    _ensure_app()
    try:
        return auth.verify_id_token(token)
    except auth.ExpiredIdTokenError as exc:
        raise TokenError('expired') from exc
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, ValueError) as exc:
        message = str(exc)
        if 'incorrect "aud"' in message or 'incorrect "iss"' in message:
            raise ProjectMismatch(message) from exc
        raise TokenError('invalid') from exc


def app_info():
    """What the health check reports: is the Admin SDK usable, and for which project?
    Only the project id (public) and the kind of error are returned, never details."""
    if not is_configured():
        return {'firebase_configured': False}
    info = {'firebase_configured': True}
    try:
        app = _ensure_app()
        info['firebase_ready'] = True
        info['firebase_project'] = getattr(app, 'project_id', None)
    except Exception as exc:  # noqa: BLE001 - reported by type only
        info['firebase_ready'] = False
        info['firebase_error'] = type(exc).__name__
    return info


def _dev_initial_data():
    return {
        'counters': {'products': 6, 'categories': 3, 'bills': 0},
        'categories': {
            '1': {'id': 1, 'name': 'Pant'},
            '2': {'id': 2, 'name': 'Shirt'},
            '3': {'id': 3, 'name': 'T Shirt'},
        },
        'products': {
            '1': {'id': 1, 'name': 'Denim Jeans', 'category': 1, 'category_name': 'Pant', 'colour': 'Indigo Blue', 'size': '32', 'price': '1499.00', 'stock': 12, 'is_active': True},
            '2': {'id': 2, 'name': 'Slim Chino Pant', 'category': 1, 'category_name': 'Pant', 'colour': 'Khaki', 'size': '34', 'price': '1299.00', 'stock': 8, 'is_active': True},
            '3': {'id': 3, 'name': 'Formal Oxford Shirt', 'category': 2, 'category_name': 'Shirt', 'colour': 'Sky Blue', 'size': 'L', 'price': '1399.00', 'stock': 15, 'is_active': True},
            '4': {'id': 4, 'name': 'Linen Formal Shirt', 'category': 2, 'category_name': 'Shirt', 'colour': 'Classic White', 'size': 'M', 'price': '1499.00', 'stock': 10, 'is_active': True},
            '5': {'id': 5, 'name': 'Crew Neck Tee', 'category': 3, 'category_name': 'T Shirt', 'colour': 'Muted Green', 'size': 'M', 'price': '799.00', 'stock': 20, 'is_active': True},
            '6': {'id': 6, 'name': 'Heavyweight T-Shirt', 'category': 3, 'category_name': 'T Shirt', 'colour': 'Sage', 'size': 'L', 'price': '899.00', 'stock': 14, 'is_active': True},
        },
        'staff': {
            'dev-staff-1': True,
        },
    }


def get_store():
    global _store
    if is_configured():
        from firebase_admin import db
        _ensure_app()
        if _store is None or getattr(_store, 'db', None) != db:
            _store = Store(db)
    elif _store is None:
        from .tests.fakedb import FakeDB
        _store = Store(FakeDB(_dev_initial_data()))
    return _store
