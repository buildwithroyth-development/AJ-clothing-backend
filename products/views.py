from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import FirebaseAuthentication, IsSignedIn, IsStaff, is_approved
from .firebase_client import get_store
from .services import StoreError


class StoreView(APIView):
    authentication_classes = [FirebaseAuthentication]
    permission_classes = [IsStaff]

    @property
    def store(self):
        return get_store()

    def handle_exception(self, exc):
        if isinstance(exc, StoreError):
            body = {exc.field: [exc.message]} if exc.field else {'error': exc.message}
            return Response(body, status=exc.status)
        return super().handle_exception(exc)

    @staticmethod
    def body(request):
        data = request.data
        return data if isinstance(data, dict) else {}


class CategoryList(StoreView):
    def get(self, request):
        return Response(self.store.list_categories())


class ProductList(StoreView):
    def get(self, request):
        return Response(self.store.list_products())

    def post(self, request):
        return Response(self.store.create_product(self.body(request)), status=201)


class ProductDetail(StoreView):
    def get(self, request, pid):
        return Response(self.store.get_product(pid))

    def patch(self, request, pid):
        return Response(self.store.update_product(pid, self.body(request)))

    def delete(self, request, pid):
        self.store.delete_product(pid)
        return Response(status=204)


class ProductRestock(StoreView):
    def post(self, request, pid):
        data = self.body(request)
        return Response(self.store.restock(pid, data.get('amount'), data.get('reason')))


class ProductHistory(StoreView):
    def get(self, request, pid):
        return Response(self.store.product_history(pid))


class SaleList(StoreView):
    def get(self, request):
        return Response(self.store.list_sales())

    def post(self, request):
        created_by = getattr(request.user, 'email', '') or getattr(request.user, 'uid', '')
        return Response(self.store.create_sale(self.body(request), created_by=created_by), status=201)


class SaleDetail(StoreView):
    def get(self, request, sale_id):
        return Response(self.store.get_sale(sale_id))


class StockMovementList(StoreView):
    def get(self, request):
        """?since=<ISO time> keeps only movements from then on (the app sends the start of today);
        ?limit=<n> caps the number returned (default 10, max 200)."""
        try:
            limit = max(1, min(200, int(request.query_params.get('limit', 10))))
        except ValueError:
            limit = 10
        since = request.query_params.get('since') or None
        return Response(self.store.recent_movements(limit=limit, since=since))


class Me(StoreView):
    """Who am I, and may I use the shop data? Works for any signed-in user so the app can
    show the right screen (approved / verify e-mail / waiting for approval)."""

    permission_classes = [IsSignedIn]

    def get(self, request):
        claims = request.auth if isinstance(request.auth, dict) else {}
        return Response({
            'uid': request.user.uid,
            'email': request.user.email,
            'email_verified': bool(claims.get('email_verified')),
            'approved': bool(is_approved(request.user.uid, claims)),
        })
