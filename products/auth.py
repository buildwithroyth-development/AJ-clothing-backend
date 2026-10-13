from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from . import firebase_client


class FirebaseUser:
    is_authenticated = True
    is_anonymous = False

    def __init__(self, uid, email=''):
        self.uid = uid
        self.email = email

    def __str__(self):
        return self.email or self.uid


class FirebaseAuthentication(BaseAuthentication):
    """Authorization: Bearer <Firebase ID token> (the token the frontend gets after sign-in)."""

    def authenticate(self, request):
        if not firebase_client.is_configured():
            return FirebaseUser('dev-staff-1', 'dev@ajclothing.com'), {'uid': 'dev-staff-1', 'email': 'dev@ajclothing.com'}

        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b'bearer':
            return None
        if len(parts) != 2:
            raise AuthenticationFailed('Invalid Authorization header.')

        token = parts[1].decode()
        if getattr(settings, 'DEBUG', False) and token == 'dev-token':
            return FirebaseUser('dev-staff-1', 'dev@ajclothing.com'), {'uid': 'dev-staff-1', 'email': 'dev@ajclothing.com'}

        try:
            decoded = firebase_client.verify_id_token(token)
        except Exception:
            raise AuthenticationFailed('Your sign-in has expired or is invalid. Please sign in again.')
        return FirebaseUser(decoded['uid'], decoded.get('email', '')), decoded

    def authenticate_header(self, request):
        return 'Bearer'


class IsStaff(BasePermission):
    """Signed in AND listed under staff/<uid> = true in the database."""

    message = 'This account is not authorised to use AJ Clothing.'

    def has_permission(self, request, view):
        if not firebase_client.is_configured():
            return True
        user = request.user
        if not getattr(user, 'is_authenticated', False) or not hasattr(user, 'uid'):
            return False
        if getattr(settings, 'DEBUG', False) and user.uid == 'dev-staff-1':
            return True
        return firebase_client.get_store().is_staff(user.uid)

