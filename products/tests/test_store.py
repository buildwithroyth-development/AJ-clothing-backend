import unittest

from products.services import (
    NotFound, OutOfStock, Store, ValidationFailure,
)
from products.tests.fakedb import FakeDB


def product(pid, name='Tee', colour='Red', size='M', price=100, stock=10, category='Tops'):
    return {
        'id': pid, 'name': name, 'category': category, 'category_name': category,
        'colour': colour, 'size': size, 'price': price, 'stock': stock, 'is_active': True,
    }


def make_store(*products, **extra):
    root = {'products': {str(p['id']): p for p in products}}
    root.update(extra)
    db = FakeDB(root)
    return Store(db), db


class ProductTests(unittest.TestCase):
    def test_create_logs_initial_stock_and_creates_category(self):
        store, db = make_store()
        p = store.create_product({'name': ' Polo ', 'category': 'Tops', 'colour': 'Navy', 'size': 'L',
                                  'price': '899.50', 'stock': 5})
        self.assertEqual((p['id'], p['name'], p['price'], p['stock']), (1, 'Polo', 899.5, 5))
        self.assertEqual(store.product_history(p['id'])[0]['reason'], 'Initial stock')
        self.assertEqual([c['name'] for c in store.list_categories()], ['Tops'])

    def test_create_requires_fields(self):
        store, _ = make_store()
        for missing in ('name', 'category', 'colour', 'size', 'price'):
            data = {'name': 'A', 'category': 'B', 'colour': 'C', 'size': 'D', 'price': 1}
            data.pop(missing)
            with self.assertRaises(ValidationFailure, msg=missing):
                store.create_product(data)

    def test_duplicate_rejected_only_when_all_five_fields_match(self):
        store, _ = make_store(product(1, 'Rohith', 'Black', 'M', price=500, category='Pant'))
        same = {'name': 'rohith', 'category': 'PANT', 'colour': 'BLACK', 'size': 'm', 'price': '500.00'}
        with self.assertRaises(ValidationFailure):
            store.create_product(same)
        # Each single difference makes it a NEW product, not a duplicate
        for change in ({'category': 'Kurtha'}, {'price': 550}, {'colour': 'Blue'},
                       {'size': 'L'}, {'name': 'Rohit'}):
            created = store.create_product({**same, **change})
            self.assertNotEqual(created['id'], 1, msg=str(change))
        self.assertEqual(store.get_product(1)['stock'], 10)

    def test_reported_example_pant_vs_kurtha(self):
        store, _ = make_store()
        pant = store.create_product({'name': 'Rohith', 'category': 'pant', 'size': 'M',
                                     'colour': 'Black', 'price': 500, 'stock': 5})
        kurtha = store.create_product({'name': 'Rohith', 'category': 'Kurtha', 'size': 'M',
                                       'colour': 'Black', 'price': 500, 'stock': 3})
        self.assertNotEqual(pant['id'], kurtha['id'])
        self.assertEqual(store.get_product(pant['id'])['stock'], 5)
        self.assertEqual(kurtha['stock'], 3)

    def test_new_ids_continue_after_existing_ones(self):
        store, _ = make_store(product(1700000000000))
        p = store.create_product({'name': 'X', 'category': 'C', 'colour': 'c', 'size': 's', 'price': 1})
        self.assertEqual(p['id'], 1700000000001)

    def test_negative_price_and_stock_rejected(self):
        store, _ = make_store()
        base = {'name': 'A', 'category': 'B', 'colour': 'C', 'size': 'D'}
        with self.assertRaises(ValidationFailure):
            store.create_product({**base, 'price': -1})
        with self.assertRaises(ValidationFailure):
            store.create_product({**base, 'price': 1, 'stock': -3})

    def test_update_stock_logs_movement(self):
        store, _ = make_store(product(1, stock=10))
        store.update_product(1, {'stock': 7})
        store.update_product(1, {'stock': 12})
        deltas = sorted(m['change'] for m in store.product_history(1))
        self.assertEqual(deltas, [-3, 5])
        self.assertEqual(store.get_product(1)['stock'], 12)

    def test_update_cannot_create_duplicate(self):
        store, _ = make_store(product(1, 'Tee', 'Red', 'M'), product(2, 'Tee', 'Red', 'L'))
        with self.assertRaises(ValidationFailure):
            store.update_product(2, {'size': 'M'})  # now identical to product 1 (same price too)
        store.update_product(2, {'size': 'M', 'price': 120})  # different price -> allowed
        store.update_product(2, {'category': 'Kurtha'})  # different category -> allowed
        self.assertEqual(store.get_product(2)['price'], 120)

    def test_restock(self):
        store, _ = make_store(product(1, stock=2))
        self.assertEqual(store.restock(1, 5)['stock'], 7)
        with self.assertRaises(ValidationFailure):
            store.restock(1, 0)
        with self.assertRaises(NotFound):
            store.restock(99, 1)

    def test_delete(self):
        store, _ = make_store(product(1))
        store.delete_product(1)
        with self.assertRaises(NotFound):
            store.get_product(1)
        with self.assertRaises(NotFound):
            store.delete_product(1)


class SaleTests(unittest.TestCase):
    def test_sale_deducts_stock_logs_movements_and_numbers_bills(self):
        store, _ = make_store(product(1, price=100, stock=10), product(2, 'Jeans', price=250, stock=5))
        s1 = store.create_sale({'items': [{'id': 1, 'qty': 2}, {'id': 2, 'qty': 1}]}, created_by='a@x.in')
        self.assertEqual(s1['bill_number'], 'AJ-000001')
        self.assertEqual((s1['subtotal'], s1['total']), (450, 450))
        self.assertEqual(s1['created_by'], 'a@x.in')
        self.assertEqual(store.get_product(1)['stock'], 8)
        self.assertEqual(store.get_product(2)['stock'], 4)
        self.assertEqual(store.product_history(1)[0]['reason'], 'Sold (AJ-000001)')
        s2 = store.create_sale({'items': [{'id': 1, 'qty': 1}]})
        self.assertEqual(s2['bill_number'], 'AJ-000002')
        self.assertEqual(len(store.list_sales()), 2)
        self.assertEqual(store.get_sale(s1['id'])['bill_number'], 'AJ-000001')

    def test_client_prices_and_totals_are_ignored(self):
        store, _ = make_store(product(1, price=100, stock=10))
        sale = store.create_sale({'items': [{'id': 1, 'qty': 3, 'price': 1, 'name': 'Hacked'}],
                                  'subtotal': 1, 'total': 1, 'discount': 99})
        self.assertEqual(sale['items'][0]['price'], 100)
        self.assertEqual(sale['items'][0]['name'], 'Tee')
        self.assertEqual((sale['subtotal'], sale['total']), (300, 300))

    def test_discount_percent_and_rounding(self):
        store, _ = make_store(product(1, price=333.33, stock=10))
        sale = store.create_sale({'items': [{'id': 1, 'qty': 1}], 'discount_percent': 10})
        self.assertEqual((sale['discount'], sale['after_discount'], sale['total']), (33.33, 300, 300))
        sale = store.create_sale({'items': [{'id': 1, 'qty': 1}], 'discount_percent': 10,
                                  'round_off': True, 'total': 295})
        self.assertEqual((sale['total'], sale['rounding_adjustment']), (295, -5))

    def test_manual_total_ignored_unless_round_off(self):
        store, _ = make_store(product(1, price=100, stock=10))
        sale = store.create_sale({'items': [{'id': 1, 'qty': 1}], 'total': 5})
        self.assertEqual(sale['total'], 100)

    def test_discount_clamped_to_0_100(self):
        store, _ = make_store(product(1, price=100, stock=10))
        self.assertEqual(store.create_sale({'items': [{'id': 1, 'qty': 1}], 'discount_percent': 250})['total'], 0)
        self.assertEqual(store.create_sale({'items': [{'id': 1, 'qty': 1}], 'discount_percent': -5})['total'], 100)

    def test_duplicate_lines_are_merged(self):
        store, _ = make_store(product(1, stock=5))
        sale = store.create_sale({'items': [{'id': 1, 'qty': 2}, {'id': 1, 'qty': 2}]})
        self.assertEqual(len(sale['items']), 1)
        self.assertEqual(sale['items'][0]['qty'], 4)
        self.assertEqual(store.get_product(1)['stock'], 1)

    def test_out_of_stock_changes_nothing_even_for_earlier_lines(self):
        store, db = make_store(product(1, stock=10), product(2, 'Jeans', stock=1))
        with self.assertRaises(OutOfStock) as ctx:
            store.create_sale({'items': [{'id': 1, 'qty': 4}, {'id': 2, 'qty': 3}]})
        self.assertIn('Only 1 units available for Jeans', ctx.exception.message)
        self.assertEqual(store.get_product(1)['stock'], 10)
        self.assertEqual(store.get_product(2)['stock'], 1)
        self.assertEqual(store.list_sales(), [])
        self.assertIsNone(db.reference('stock_movements').get())

    def test_unknown_product_rejected_and_stock_restored(self):
        store, _ = make_store(product(1, stock=10))
        with self.assertRaises(NotFound):
            store.create_sale({'items': [{'id': 1, 'qty': 2}, {'id': 404, 'qty': 1}]})
        self.assertEqual(store.get_product(1)['stock'], 10)

    def test_write_failure_restores_stock(self):
        store, db = make_store(product(1, stock=10))
        db.fail_next_update = True
        with self.assertRaises(RuntimeError):
            store.create_sale({'items': [{'id': 1, 'qty': 4}]})
        self.assertEqual(store.get_product(1)['stock'], 10)
        self.assertEqual(store.list_sales(), [])

    def test_validation(self):
        store, _ = make_store(product(1, stock=10))
        for bad in ({}, {'items': []}, {'items': ['x']}, {'items': [{'qty': 1}]},
                    {'items': [{'id': 1, 'qty': 0}]}, {'items': [{'id': 1, 'qty': 1.5}]},
                    {'items': [{'id': 1, 'qty': 1}], 'customer_mobile': 'abc'}):
            with self.assertRaises(ValidationFailure, msg=str(bad)):
                store.create_sale(bad)
        self.assertEqual(store.get_product(1)['stock'], 10)

    def test_bill_numbers_continue_after_existing_sales(self):
        existing = {'a': {'bill_number': 'AJ-000001', 'created_at': '2026-01-01'},
                    'b': {'bill_number': 'AJ-000002', 'created_at': '2026-01-02'}}
        store, _ = make_store(product(1, stock=10), sales=existing)
        self.assertEqual(store.create_sale({'items': [{'id': 1, 'qty': 1}]})['bill_number'], 'AJ-000003')

    def test_recent_movements_newest_first(self):
        store, _ = make_store(product(1, stock=10))
        store.create_sale({'items': [{'id': 1, 'qty': 1}]})
        store.restock(1, 3)
        rows = store.recent_movements()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['productName'], 'Tee')


class StaffTests(unittest.TestCase):
    def test_is_staff(self):
        store, _ = make_store(staff={'u1': True, 'u2': False})
        self.assertTrue(store.is_staff('u1'))
        self.assertFalse(store.is_staff('u2'))
        self.assertFalse(store.is_staff('nobody'))
        self.assertFalse(store.is_staff(''))


if __name__ == '__main__':
    unittest.main()
