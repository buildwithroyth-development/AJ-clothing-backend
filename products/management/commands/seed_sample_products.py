import os
from django.core.management.base import BaseCommand
from products.models import Category, Product

SAMPLE_DATA = [
    {"name": "Everyday Tee", "category": "Tops", "colour": "Ivory", "size": "M", "price": 799, "stock": 15},
    {"name": "Everyday Tee", "category": "Tops", "colour": "Cocoa", "size": "L", "price": 799, "stock": 9},
    {"name": "Polo T-shirt", "category": "Tops", "colour": "Navy", "size": "L", "price": 899, "stock": 20},
    {"name": "Graphic Tee", "category": "Tops", "colour": "White", "size": "M", "price": 699, "stock": 18},
    {"name": "Oversized Tee", "category": "Tops", "colour": "Black", "size": "XL", "price": 999, "stock": 12},
    {"name": "Striped Tee", "category": "Tops", "colour": "Grey", "size": "S", "price": 749, "stock": 15},
    {"name": "Relaxed Denim", "category": "Bottoms", "colour": "Indigo", "size": "32", "price": 1499, "stock": 8},
    {"name": "Slim Fit Chino Pant", "category": "Bottoms", "colour": "Beige", "size": "30", "price": 1399, "stock": 14},
    {"name": "Formal Trouser", "category": "Bottoms", "colour": "Charcoal", "size": "34", "price": 1699, "stock": 10},
    {"name": "Cargo Pant", "category": "Bottoms", "colour": "Olive", "size": "32", "price": 1799, "stock": 9},
    {"name": "Cotton Jogger Pant", "category": "Bottoms", "colour": "Black", "size": "36", "price": 1099, "stock": 18},
    {"name": "Linen Shirt", "category": "Shirts", "colour": "White", "size": "M", "price": 1199, "stock": 4},
    {"name": "Oxford Shirt", "category": "Shirts", "colour": "Sky Blue", "size": "L", "price": 1399, "stock": 12},
    {"name": "Checked Shirt", "category": "Shirts", "colour": "Red", "size": "XL", "price": 999, "stock": 10},
    {"name": "Denim Shirt", "category": "Shirts", "colour": "Indigo", "size": "M", "price": 1599, "stock": 8},
    {"name": "Formal Shirt", "category": "Shirts", "colour": "Black", "size": "S", "price": 1299, "stock": 16},
    {"name": "Classic Kurta", "category": "Ethnic", "colour": "Maroon", "size": "L", "price": 1299, "stock": 7},
    {"name": "Festive Saree", "category": "Ethnic", "colour": "Gold", "size": "Free", "price": 2499, "stock": 13},
    {"name": "Cotton Kurta", "category": "Ethnic", "colour": "Cream", "size": "M", "price": 999, "stock": 15},
    {"name": "Printed Kurta", "category": "Ethnic", "colour": "Blue", "size": "XL", "price": 1499, "stock": 11},
    {"name": "Festive Silk Kurta", "category": "Ethnic", "colour": "Mustard", "size": "L", "price": 2299, "stock": 6},
    {"name": "Short Kurta", "category": "Ethnic", "colour": "Green", "size": "S", "price": 1199, "stock": 13},
    {"name": "Cotton Saree", "category": "Ethnic", "colour": "Pink", "size": "Free", "price": 1299, "stock": 12},
    {"name": "Silk Saree", "category": "Ethnic", "colour": "Royal Blue", "size": "Free", "price": 3499, "stock": 7},
    {"name": "Printed Saree", "category": "Ethnic", "colour": "Green", "size": "Free", "price": 1599, "stock": 16},
    {"name": "Chiffon Saree", "category": "Ethnic", "colour": "Peach", "size": "Free", "price": 1999, "stock": 10},
]

class Command(BaseCommand):
    help = 'Seed database with sample products and categories from POS system'

    def handle(self, *args, **options):
        self.stdout.write("Seeding categories and products...")
        categories = {}
        for cat_name in ["Tops", "Bottoms", "Shirts", "Ethnic"]:
            cat, created = Category.objects.get_or_create(name=cat_name)
            categories[cat_name] = cat
            if created:
                self.stdout.write(f"Created category: {cat_name}")

        created_count = 0
        for item in SAMPLE_DATA:
            cat = categories.get(item["category"])
            prod, created = Product.objects.get_or_create(
                name=item["name"],
                colour=item["colour"],
                size=item["size"],
                defaults={
                    "category": cat,
                    "price": item["price"],
                    "stock": item["stock"],
                    "description": f"{item['name']} in {item['colour']}, size {item['size']}"
                }
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {created_count} sample products! Total products in DB: {Product.objects.count()}"))
