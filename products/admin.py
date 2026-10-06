from django.contrib import admin
from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'price', 'stock', 'colour', 'size', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'colour', 'size']
    search_fields = ['name', 'sku', 'colour']
    ordering = ['-created_at']
    list_editable = ['price', 'stock', 'is_active']
