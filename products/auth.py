import logging

from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.permissions import BasePermission

from . import firebase_client

logger = logging.getLogger(__name__)

DEV_UID = 'dev-staff-1'
DEV_EMAIL = 'dev@ajclothing.com'


class ServerNotConfigured(APIException):
    status_code = 503
    default_detail = 'The server is not connected to Firebase yet. Please contact the administrator.'
    default_code = 'not_configured'


class FirebaseUser:
    is_authenticated = True
    is_anonymous = False

    def __init__(self, uid, email=''):
        self.uid = uid
        self.email = email

    def __str__(self):
        return self.email or self.uid


def dev_mode():
    """Local development only: DEBUG on AND Firebase credentials not set.
    In production (DEBUG off) a missing configuration is an error, never an open door."""
    return bool(getattr(settings, 'DEBUG', False)) and not firebase_client.is_configured()


def _email_list(name):
    return {e.strip().lower() for e in str(getattr(settings, name, '') or '').split(',') if e.strip()}


def is_approved(uid, claims):
    """Who may use the shop data.

    1. Anyone listed under staff/<uid> = true in the database (approved by the owner).
    2. A user whose e-mail is verified AND who is either in STAFF_EMAILS or
       AUTO_APPROVE_VERIFIED_USERS is on.
    """
    if dev_mode():
        return True
    if firebase_client.get_store().is_staff(uid):
        return True
    email = str((claims or {}).get('email') or '').lower()
    if not (claims or {}).get('email_verified'):
        return False
    if getattr(settings, 'AUTO_APPROVE_VERIFIED_USERS', False):
        return True
    return bool(email) and email in _email_list('STAFF_EMAILS')


class FirebaseAuthentication(BaseAuthentication):
    """Authorization: Bearer <Firebase ID token> (the token the frontend gets after sign-in)."""

    def authenticate(self, request):
        if dev_mode():
            return FirebaseUser(DEV_UID, DEV_EMAIL), {'uid': DEV_UID, 'email': DEV_EMAIL, 'email_verified': True}

        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b'bearer':
            return None
        if len(parts) != 2:
            raise AuthenticationFailed('Invalid Authorization header.')
        if not firebase_client.is_configured():
            raise ServerNotConfigured()

        try:
            decoded = firebase_client.verify_id_token(parts[1].decode())
        except firebase_client.TokenError as exc:
            logger.warning('Sign-in rejected: token is %s.', exc)
            raise AuthenticationFailed('Your sign-in has expired or is invalid. Please sign in again.')
        except firebase_client.ProjectMismatch as exc:
            logger.error('Sign-in rejected: the app and the server use different Firebase projects (%s).', exc)
            raise ServerNotConfigured(
                'The server is connected to a different Firebase project than the app. '
                'Use a service-account key from the same project as the app.'
            )
        except Exception:  # noqa: BLE001 - configuration or network problem, not the person's fault
            logger.exception('Firebase Admin could not check a sign-in token.')
            raise ServerNotConfigured(
                'The server could not check your sign-in with Firebase. '
                'Check FIREBASE_SERVICE_ACCOUNT_JSON and FIREBASE_DATABASE_URL on the server.'
            )
        return FirebaseUser(decoded['uid'], decoded.get('email', '')), decoded

    def authenticate_header(self, request):
        return 'Bearer'


class IsSignedIn(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request.user, 'uid')


class IsStaff(BasePermission):
    """Signed in AND approved (see is_approved)."""

    message = 'Your account is waiting for approval by the store owner.'

    def has_permission(self, request, view):
        user = request.user
        if not hasattr(user, 'uid'):
            return False
        return is_approved(user.uid, request.auth if isinstance(request.auth, dict) else {})
