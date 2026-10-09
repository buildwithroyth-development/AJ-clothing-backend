from rest_framework import serializers
from .models import Category, Product, StockMovement


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'product_count', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = ['id', 'change', 'reason', 'created_at']
        read_only_fields = ['id', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    stock_history = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'category_name',
            'price', 'stock', 'colour', 'size', 'description',
            'is_active', 'stock_history', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_stock_history(self, obj):
        try:
            items = obj.stock_history.all()[:25]
            return StockMovementSerializer(items, many=True).data
        except Exception:
            return []

    def validate(self, attrs):
        is_partial = getattr(self, 'partial', False)
        # Required fields: Product Name, Category, Colour, Size, Selling Price
        if not is_partial:
            if not attrs.get('name') or not str(attrs.get('name')).strip():
                raise serializers.ValidationError({'name': 'Product name is required.'})
            if not attrs.get('category'):
                raise serializers.ValidationError({'category': 'Category is required.'})
            if not attrs.get('colour') or not str(attrs.get('colour')).strip():
                raise serializers.ValidationError({'colour': 'Colour is required.'})
            if not attrs.get('size') or not str(attrs.get('size')).strip():
                raise serializers.ValidationError({'size': 'Size is required.'})
            if attrs.get('price') is None or attrs.get('price') < 0:
                raise serializers.ValidationError({'price': 'Selling price is required.'})
        return attrs
