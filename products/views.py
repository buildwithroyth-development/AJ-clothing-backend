from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Category, Product, StockMovement
from .serializers import CategorySerializer, ProductSerializer, StockMovementSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """Return all active products under a specific category."""
        category = self.get_object()
        prods = category.products.filter(is_active=True)
        serializer = ProductSerializer(prods, many=True)
        return Response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related('category').all()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active', 'colour', 'size']
    search_fields = ['name', 'colour', 'size', 'description', 'category__name']
    ordering_fields = ['name', 'price', 'stock', 'created_at']

    def _resolve_category(self, data):
        """
        Accept either:
          - category: <int id>     — use existing category by ID
          - category: "<name str>" — look up or create by name
          - category: null / ""    — no category
        Returns a copy of data with category resolved to an int ID or None.
        """
        raw = data.get('category')
        if not raw:
            return {**data, 'category': None}

        # Already an integer ID
        if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
            return data

        # Freeform string — look up or create
        name = str(raw).strip()
        if name:
            cat, _ = Category.objects.get_or_create(
                name__iexact=name,
                defaults={'name': name},
            )
            return {**data, 'category': cat.id}

        return {**data, 'category': None}

    def create(self, request, *args, **kwargs):
        data = self._resolve_category(request.data.copy())
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        # Log initial stock if stock was provided
        if instance.stock > 0:
            try:
                StockMovement.objects.create(
                    product=instance,
                    change=instance.stock,
                    reason='Initial stock',
                )
            except Exception:
                pass

        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        old_stock = instance.stock
        data = self._resolve_category(request.data.copy())
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()

        # Log stock adjustment if stock changed
        if 'stock' in data:
            delta = updated.stock - old_stock
            if delta != 0:
                try:
                    StockMovement.objects.create(
                        product=updated,
                        change=delta,
                        reason='Stock adjusted' if delta < 0 else 'Stock added',
                    )
                except Exception:
                    pass

        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        """Add stock units to an existing product and record in stock history."""
        instance = self.get_object()
        try:
            amount = int(request.data.get('amount', 0))
        except (ValueError, TypeError):
            return Response({'error': 'Invalid amount.'}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({'error': 'Amount must be greater than 0.'}, status=status.HTTP_400_BAD_REQUEST)

        instance.stock += amount
        instance.save(update_fields=['stock', 'updated_at'])

        try:
            StockMovement.objects.create(
                product=instance,
                change=amount,
                reason=request.data.get('reason', 'Stock added (Restock)'),
            )
        except Exception:
            pass

        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Return stock movement history for this product."""
        instance = self.get_object()
        try:
            movements = instance.stock_history.all()[:50]
            serializer = StockMovementSerializer(movements, many=True)
            return Response(serializer.data)
        except Exception:
            return Response([])
