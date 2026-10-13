"""
Business logic for the AJ Clothing API.

Everything lives in Firebase Realtime Database:

    products/{id}                    product + variant (name, colour, size), price, stock
    categories/{id}                  {id, name}
    sales/{id}                       a finished bill (never edited afterwards)
    stock_movements/{productId}/{id} append-only stock history
    counters/bills, counters/products  sequential ids
    staff/{uid}                      true for each signed-in user allowed to use the app

This module deliberately has NO Django imports. It only needs an object with the
``firebase_admin.db`` interface (``db.reference(path)``), so it can be tested with
an in-memory fake.
"""
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MOBILE_RE = re.compile(r'^[+\d ()-]{7,20}$')
CENT = Decimal('0.01')


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class StoreError(Exception):
    status = 400

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


class ValidationFailure(StoreError):
    status = 400


class NotFound(StoreError):
    status = 404


class OutOfStock(StoreError):
    status = 409


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _to_list(val):
    """Firebase returns either a dict or (for 0..n keys) a list; normalise to a list."""
    if not val:
        return []
    items = val if isinstance(val, list) else list(val.values())
    return [i for i in items if i]


def _money(value, field):
    if isinstance(value, bool):
        raise ValidationFailure('Enter a valid amount.', field)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationFailure('Enter a valid amount.', field)
    if not d.is_finite():
        raise ValidationFailure('Enter a valid amount.', field)
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _store_number(d):
    """Decimal -> int when whole, else float (what Firebase stores/returns as JSON)."""
    return int(d) if d == d.to_integral_value() else float(d)


def _whole(value, field, minimum=0):
    if isinstance(value, bool):
        raise ValidationFailure('Enter a whole number.', field)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationFailure('Enter a whole number.', field)
    if not d.is_finite() or d != d.to_integral_value():
        raise ValidationFailure('Enter a whole number.', field)
    n = int(d)
    if n < minimum:
        raise ValidationFailure(f'Must be at least {minimum}.', field)
    return n


def _text(value, field, max_len, required=False):
    s = '' if value is None else str(value).strip()
    if required and not s:
        raise ValidationFailure('This field is required.', field)
    if len(s) > max_len:
        raise ValidationFailure(f'Must be {max_len} characters or fewer.', field)
    return s


def _same(a, b):
    return (a or '').strip().lower() == (b or '').strip().lower()


def _is_int_like(value):
    return isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit())


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------
class Store:
    def __init__(self, db):
        self.db = db

    def _ref(self, path='/'):
        return self.db.reference(path)

    # ---- auth -------------------------------------------------------------
    def is_staff(self, uid):
        if not uid:
            return False
        return self._ref(f'staff/{uid}').get() is True

    # ---- ids --------------------------------------------------------------
    def _next_number(self, counter, seed):
        """Atomically increment counters/{counter}. `seed` is a callable used only
        the first time, so numbering continues after any data that already exists."""
        ref = self._ref(f'counters/{counter}')
        start = 0 if ref.get() is not None else seed()
        box = {}

        def bump(cur):
            n = (cur if isinstance(cur, int) else start) + 1
            box['n'] = n
            return n

        ref.transaction(bump)
        return box['n']

    # ---- categories -------------------------------------------------------
    def list_categories(self):
        cats = _to_list(self._ref('categories').get())
        if cats:
            return cats
        names = sorted({p.get('category_name') or p.get('category') for p in self.list_products()
                        if p.get('category_name') or p.get('category')})
        return [{'id': i + 1, 'name': n} for i, n in enumerate(names)]

    def _ensure_category(self, name):
        name = (name or '').strip()
        if not name:
            return
        if any(_same(c.get('name'), name) for c in _to_list(self._ref('categories').get())):
            return
        cid = self._next_number(
            'categories',
            lambda: max([int(c['id']) for c in _to_list(self._ref('categories').get())
                         if _is_int_like(c.get('id'))] or [0]),
        )
        self._ref(f'categories/{cid}').set({'id': cid, 'name': name})

    def _resolve_category(self, raw):
        """Accept a category name, or the id of an existing category."""
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return ''
        if _is_int_like(raw):
            for c in _to_list(self._ref('categories').get()):
                if str(c.get('id')) == str(raw).strip():
                    return c.get('name', '')
        return _text(raw, 'category', 120)

    # ---- products ---------------------------------------------------------
    def list_products(self):
        return _to_list(self._ref('products').get())

    def get_product(self, pid):
        product = self._ref(f'products/{pid}').get()
        if not product:
            raise NotFound('Product not found.')
        return product

    def _check_duplicate(self, name, colour, size, exclude_id=None):
        for p in self.list_products():
            if exclude_id is not None and str(p.get('id')) == str(exclude_id):
                continue
            if _same(p.get('name'), name) and _same(p.get('colour'), colour) and _same(p.get('size'), size):
                raise ValidationFailure(
                    f'Product "{name}" ({colour} · Size {size}) already exists '
                    f'(current stock: {p.get("stock", 0)} units). Update the existing product instead.'
                )

    def _movement(self, product_id, product_name, change, reason, extra=None):
        key = self._ref(f'stock_movements/{product_id}').push().key
        value = {
            'id': key,
            'product': int(product_id) if _is_int_like(product_id) else product_id,
            'product_name': product_name,
            'change': change,
            'reason': reason,
            'created_at': _now(),
        }
        if extra:
            value.update(extra)
        return f'stock_movements/{product_id}/{key}', value

    def create_product(self, data):
        name = _text(data.get('name'), 'name', 200, required=True)
        category = self._resolve_category(data.get('category'))
        if not category:
            raise ValidationFailure('Category is required.', 'category')
        colour = _text(data.get('colour'), 'colour', 80, required=True)
        size = _text(data.get('size'), 'size', 30, required=True)
        if data.get('price') in (None, ''):
            raise ValidationFailure('Selling price is required.', 'price')
        price = _money(data.get('price'), 'price')
        if price < 0:
            raise ValidationFailure('Price cannot be negative.', 'price')
        stock = _whole(data.get('stock', 0) if data.get('stock') not in (None, '') else 0, 'stock')
        description = _text(data.get('description'), 'description', 2000)

        self._check_duplicate(name, colour, size)

        pid = self._next_number(
            'products',
            lambda: max([int(p['id']) for p in self.list_products() if _is_int_like(p.get('id'))] or [0]),
        )
        now = _now()
        product = {
            'id': pid,
            'name': name,
            'category': category,
            'category_name': category,
            'colour': colour,
            'size': size,
            'price': _store_number(price),
            'stock': stock,
            'description': description,
            'is_active': data.get('is_active') is not False,
            'created_at': now,
            'updated_at': now,
        }
        writes = {f'products/{pid}': product}
        if stock > 0:
            path, value = self._movement(pid, name, stock, 'Initial stock')
            writes[path] = value
        self._ref('/').update(writes)
        self._ensure_category(category)
        return product

    def update_product(self, pid, data):
        current = self.get_product(pid)
        changes = {}
        if 'name' in data:
            changes['name'] = _text(data['name'], 'name', 200, required=True)
        if 'category' in data:
            category = self._resolve_category(data['category'])
            if not category:
                raise ValidationFailure('Category is required.', 'category')
            changes['category'] = category
            changes['category_name'] = category
        if 'colour' in data:
            changes['colour'] = _text(data['colour'], 'colour', 80, required=True)
        if 'size' in data:
            changes['size'] = _text(data['size'], 'size', 30, required=True)
        if 'price' in data:
            price = _money(data['price'], 'price')
            if price < 0:
                raise ValidationFailure('Price cannot be negative.', 'price')
            changes['price'] = _store_number(price)
        if 'stock' in data:
            changes['stock'] = _whole(data['stock'], 'stock')
        if 'description' in data:
            changes['description'] = _text(data['description'], 'description', 2000)
        if 'is_active' in data:
            changes['is_active'] = bool(data['is_active'])

        self._check_duplicate(
            changes.get('name', current.get('name')),
            changes.get('colour', current.get('colour')),
            changes.get('size', current.get('size')),
            exclude_id=pid,
        )

        box = {}

        def apply(cur):
            if cur is None:
                raise NotFound('Product not found.')
            box['old_stock'] = cur.get('stock', 0)
            new = dict(cur)
            new.update(changes)
            new['updated_at'] = _now()
            box['new'] = new
            return new

        self._ref(f'products/{pid}').transaction(apply)
        updated = box['new']

        if 'stock' in changes and changes['stock'] != box['old_stock']:
            delta = changes['stock'] - box['old_stock']
            path, value = self._movement(
                pid, updated.get('name'), delta, 'Stock added' if delta > 0 else 'Stock adjusted'
            )
            self._ref(path).set(value)
        if 'category' in changes:
            self._ensure_category(changes['category'])
        return updated

    def delete_product(self, pid):
        self.get_product(pid)
        # Past sales keep their own copy of the product details, so history stays intact.
        self._ref(f'products/{pid}').delete()

    def _adjust_stock(self, pid, delta):
        """Add `delta` (may be negative) to a product's stock inside a transaction.
        Never lets stock go below zero. Returns the updated product."""
        box = {}

        def apply(cur):
            if cur is None:
                raise NotFound('A product in this bill no longer exists. Refresh and try again.')
            new_stock = (cur.get('stock') or 0) + delta
            if new_stock < 0:
                raise OutOfStock(
                    f'Only {cur.get("stock", 0)} units available for {cur.get("name")} '
                    f'({cur.get("colour", "")} · Size {cur.get("size", "")}).'
                )
            new = dict(cur)
            new['stock'] = new_stock
            new['updated_at'] = _now()
            box['new'] = new
            return new

        self._ref(f'products/{pid}').transaction(apply)
        return box['new']

    def restock(self, pid, amount, reason=None):
        amount = _whole(amount, 'amount', minimum=1)
        try:
            product = self._adjust_stock(pid, amount)
        except NotFound:
            raise NotFound('Product not found.')
        path, value = self._movement(
            pid, product.get('name'), amount, _text(reason, 'reason', 255) or 'Stock added (Restock)'
        )
        self._ref(path).set(value)
        return product

    def product_history(self, pid, limit=50):
        self.get_product(pid)
        moves = _to_list(self._ref(f'stock_movements/{pid}').get())
        moves.sort(key=lambda m: m.get('created_at', ''), reverse=True)
        return moves[:limit]

    def recent_movements(self, limit=10):
        tree = self._ref('stock_movements').get() or {}
        products = {str(p.get('id')): p for p in self.list_products()}
        out = []
        entries = tree.items() if isinstance(tree, dict) else enumerate(tree)
        for pid, moves in entries:
            for m in _to_list(moves):
                if 'change' not in m:
                    continue
                row = dict(m)
                row['productName'] = m.get('product_name') or products.get(str(pid), {}).get('name') or 'Product'
                out.append(row)
        out.sort(key=lambda m: m.get('created_at', ''), reverse=True)
        return out[:limit]

    # ---- sales ------------------------------------------------------------
    def list_sales(self):
        sales = _to_list(self._ref('sales').get())
        sales.sort(key=lambda s: s.get('created_at', ''), reverse=True)
        return sales

    def get_sale(self, sale_id):
        sale = self._ref(f'sales/{sale_id}').get()
        if not sale:
            raise NotFound('Sale not found.')
        return sale

    def create_sale(self, data, created_by=''):
        """Create a bill.

        1. Merge duplicate cart lines.
        2. Deduct stock per product in a transaction. If any line fails, every
           deduction already made is put back.
        3. Take the next bill number from counters/bills.
        4. Recompute prices and totals from the live product records (the client's
           prices are ignored).
        5. Write the sale and its stock movements in a single multi-path update.
           If that fails, stock is put back.
        """
        raw_items = data.get('items')
        if not isinstance(raw_items, list) or not raw_items:
            raise ValidationFailure('Cannot confirm sale with an empty cart.')

        wanted = {}
        for it in raw_items:
            if not isinstance(it, dict):
                raise ValidationFailure('Invalid item in the bill.')
            pid = it.get('id', it.get('product'))
            if pid in (None, ''):
                raise ValidationFailure('Every item in the bill must be a product from the stock list.')
            qty = _whole(it.get('qty', it.get('quantity', 1)), 'qty', minimum=1)
            wanted[str(pid)] = wanted.get(str(pid), 0) + qty

        customer_name = _text(data.get('customer_name'), 'customer_name', 120)
        customer_mobile = _text(data.get('customer_mobile'), 'customer_mobile', 20)
        if customer_mobile and not MOBILE_RE.match(customer_mobile):
            raise ValidationFailure('Please enter a valid phone number (7–20 digits).', 'customer_mobile')
        payment = _text(data.get('payment_method') or data.get('payment') or 'Cash', 'payment_method', 50)

        pct = Decimal(str(data.get('discount_percent') or 0)) if _is_number(data.get('discount_percent')) else Decimal(0)
        pct = min(Decimal(100), max(Decimal(0), pct))
        round_off = bool(data.get('round_off'))

        deducted = []  # (pid, qty, product after deduction)

        def put_stock_back():
            for pid, qty, _ in deducted:
                try:
                    self._adjust_stock(pid, qty)
                except StoreError:
                    pass

        try:
            for pid, qty in wanted.items():
                deducted.append((pid, qty, self._adjust_stock(pid, -qty)))

            number = self._next_number('bills', lambda: len(_to_list(self._ref('sales').get())))
            bill_number = f'AJ-{number:06d}'

            items = []
            subtotal = Decimal(0)
            for pid, qty, product in deducted:
                price = _money(product.get('price', 0), 'price')
                line = (price * qty).quantize(CENT, rounding=ROUND_HALF_UP)
                subtotal += line
                items.append({
                    'product': int(pid) if _is_int_like(pid) else pid,
                    'name': product.get('name', 'Product'),
                    'colour': product.get('colour', ''),
                    'size': product.get('size', ''),
                    'price': _store_number(price),
                    'qty': qty,
                    'line_total': _store_number(line),
                })
            discount = (subtotal * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
            after_discount = max(Decimal(0), subtotal - discount)

            total = after_discount
            if round_off and data.get('total') not in (None, ''):
                requested = _money(data.get('total'), 'total')
                if requested < 0:
                    raise ValidationFailure('Final amount cannot be negative.', 'total')
                total = requested
            rounding_adjustment = total - after_discount

            now = _now()
            sale_id = self._ref('sales').push().key
            sale = {
                'id': sale_id,
                'bill_number': bill_number,
                'bill': bill_number,
                'customer_name': customer_name,
                'customer_mobile': customer_mobile,
                'items': items,
                'subtotal': _store_number(subtotal),
                'discount_percent': _store_number(pct),
                'discount': _store_number(discount),
                'after_discount': _store_number(after_discount),
                'round_off': round_off,
                'rounding_adjustment': _store_number(rounding_adjustment),
                'total': _store_number(total),
                'payment_method': payment,
                'payment': payment,
                'created_by': created_by,
                'created_at': now,
                'at': now,
            }

            writes = {f'sales/{sale_id}': sale}
            for pid, qty, product in deducted:
                path, value = self._movement(
                    pid, product.get('name'), -qty, f'Sold ({bill_number})', {'bill': bill_number}
                )
                writes[path] = value
            self._ref('/').update(writes)
            return sale
        except Exception:
            put_stock_back()
            raise


def _is_number(value):
    if isinstance(value, bool) or value is None or value == '':
        return False
    try:
        return Decimal(str(value)).is_finite()
    except (InvalidOperation, ValueError):
        return False
