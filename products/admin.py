from django.contrib import admin
from .models import Category, Product, StockMovement, Sale, SaleItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'stock', 'colour', 'size', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'colour', 'size']
    search_fields = ['name', 'colour']
    ordering = ['-created_at']
    list_editable = ['price', 'stock', 'is_active']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['product', 'change', 'reason', 'created_at']
    list_filter = ['reason', 'created_at']
    search_fields = ['product__name', 'reason']


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['bill_number', 'customer_name', 'customer_mobile', 'total', 'payment_method', 'created_at']
    list_filter = ['payment_method', 'created_at']
    search_fields = ['bill_number', 'customer_name', 'customer_mobile']
    inlines = [SaleItemInline]
