from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


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
    search_fields = ['name', 'sku', 'colour', 'size', 'description', 'category__name']
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
            return data  # pass through — serializer handles FK lookup

        # Freeform string — look up or create
        name = str(raw).strip()
        if name:
            cat, _ = Category.objects.get_or_create(
                name__iexact=name,
                defaults={'name': name},
            )
            return {**data, 'category': cat.id}

        return {**data, 'category': None}

    def _resolve_sku(self, data, is_update=False):
        raw = data.get('sku')
        if raw is not None and str(raw).strip():
            data['sku'] = str(raw).strip()
            return data

        # If it's an update and sku was not sent or sent empty, set to None if sent
        if is_update:
            if 'sku' in data:
                data['sku'] = None
            return data

        # Auto-generate SKU for new products when not provided
        name = data.get('name', 'PRD')
        colour = data.get('colour', '')
        size = data.get('size', '')
        import re, random, string
        clean_name = re.sub(r'[^A-Z0-9]', '', (name or 'PRD').upper())[:4] or 'PRD'
        clean_col = re.sub(r'[^A-Z0-9]', '', (colour or '').upper())[:3]
        clean_size = re.sub(r'[^A-Z0-9]', '', (size or '').upper())[:2]
        parts = [clean_name]
        if clean_col:
            parts.append(clean_col)
        if clean_size:
            parts.append(clean_size)

        for _ in range(10):
            rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            candidate = '-'.join(parts + [rand])
            if not Product.objects.filter(sku=candidate).exists():
                data['sku'] = candidate
                return data

        data['sku'] = None
        return data

    def create(self, request, *args, **kwargs):
        data = self._resolve_category(request.data.copy())
        data = self._resolve_sku(data, is_update=False)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=201)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        data = self._resolve_category(request.data.copy())
        data = self._resolve_sku(data, is_update=True)
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
