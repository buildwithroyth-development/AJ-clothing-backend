from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from .models import Category, Product, StockMovement, Sale, SaleItem
from .serializers import CategorySerializer, ProductSerializer, StockMovementSerializer, SaleSerializer


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

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except Exception:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM products_product WHERE id = %s', [instance.id])

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


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.prefetch_related('items').all()
    serializer_class = SaleSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['bill_number', 'customer_name', 'customer_mobile', 'payment_method']
    ordering_fields = ['created_at', 'total']

    def create(self, request, *args, **kwargs):
        data = request.data
        items_data = data.get('items', [])
        if not items_data:
            return Response({'error': 'Cannot confirm sale with an empty cart.'}, status=status.HTTP_400_BAD_REQUEST)

        payment_method = data.get('payment_method') or data.get('payment') or 'Cash'
        customer_name = (data.get('customer_name') or data.get('customerName') or '').strip()
        customer_mobile = (data.get('customer_mobile') or data.get('customerMobile') or '').strip()

        with transaction.atomic():
            last_sale = Sale.objects.order_by('-id').first()
            next_num = (last_sale.id + 1) if last_sale else 1
            bill_number = data.get('bill') or data.get('bill_number') or f"AJ-{next_num:06d}"

            prepared_items = []
            subtotal = 0

            for it in items_data:
                prod_id = it.get('id') or it.get('product') or (it.get('p', {}).get('id') if isinstance(it.get('p'), dict) else None)
                qty = int(it.get('qty') or it.get('quantity') or 1)
                if qty <= 0:
                    continue

                product = None
                if prod_id:
                    try:
                        product = Product.objects.select_for_update().get(id=prod_id)
                    except Product.DoesNotExist:
                        product = None

                p_name = it.get('name') or (product.name if product else 'Product')
                p_colour = it.get('colour') or (product.colour if product else '')
                p_size = it.get('size') or (product.size if product else '')
                p_price = float(it.get('price') or (product.price if product else 0))

                if product:
                    if product.stock < qty:
                        return Response(
                            {'error': f'Only {product.stock} units available for {product.name} ({product.colour} · Size {product.size}).'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    product.stock -= qty
                    product.save(update_fields=['stock', 'updated_at'])

                    StockMovement.objects.create(
                        product=product,
                        change=-qty,
                        reason=f'Sold ({bill_number})',
                    )

                line_total = p_price * qty
                subtotal += line_total
                prepared_items.append({
                    'product': product,
                    'product_name': p_name,
                    'colour': p_colour,
                    'size': p_size,
                    'price': p_price,
                    'quantity': qty,
                    'line_total': line_total,
                })

            subtotal_val = float(data.get('subtotal', subtotal))
            discount_pct_val = float(data.get('discount_percent', data.get('discountPercent', 0)))
            discount_val = float(data.get('discount', 0))
            after_discount_val = float(data.get('afterDiscount', data.get('after_discount', subtotal_val - discount_val)))
            round_off_val = bool(data.get('roundOff', data.get('round_off', False)))
            total_val = float(data.get('total', after_discount_val))
            rounding_adj = float(data.get('roundingAdjustment', data.get('rounding_adjustment', total_val - after_discount_val if round_off_val else 0)))

            sale = Sale.objects.create(
                bill_number=bill_number,
                customer_name=customer_name,
                customer_mobile=customer_mobile,
                subtotal=subtotal_val,
                discount_percent=discount_pct_val,
                discount=discount_val,
                after_discount=after_discount_val,
                round_off=round_off_val,
                rounding_adjustment=rounding_adj,
                total=total_val,
                payment_method=payment_method,
            )

            for p_item in prepared_items:
                SaleItem.objects.create(
                    sale=sale,
                    product=p_item['product'],
                    product_name=p_item['product_name'],
                    colour=p_item['colour'],
                    size=p_item['size'],
                    price=p_item['price'],
                    quantity=p_item['quantity'],
                    line_total=p_item['line_total'],
                )

        return Response(self.get_serializer(sale).data, status=status.HTTP_201_CREATED)

