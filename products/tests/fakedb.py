"""A tiny in-memory stand-in for ``firebase_admin.db`` (reference/get/set/update/delete/push/transaction)."""
import copy


def _parts(path):
    return [p for p in str(path).split('/') if p]


class FakeRef:
    def __init__(self, db, path):
        self._db = db
        self._path = '/'.join(_parts(path))

    @property
    def key(self):
        parts = _parts(self._path)
        return parts[-1] if parts else None

    def get(self):
        return copy.deepcopy(self._db._read(self._path))

    def set(self, value):
        self._db._write(self._path, value)

    def delete(self):
        self._db._write(self._path, None)

    def update(self, values):
        self._db._before_update(self._path, values)
        for k, v in values.items():
            self._db._write('/'.join(filter(None, [self._path, k])), v)

    def push(self):
        self._db._push_count += 1
        return FakeRef(self._db, '/'.join(filter(None, [self._path, f'-K{self._db._push_count:06d}'])))

    def transaction(self, fn):
        new = fn(self.get())  # exceptions propagate and nothing is written, like firebase_admin
        self._db._write(self._path, new)
        return new


class FakeDB:
    def __init__(self, initial=None):
        self.root = copy.deepcopy(initial) if initial else {}
        self._push_count = 0
        self.fail_next_update = False

    def reference(self, path='/'):
        return FakeRef(self, path)

    def _before_update(self, path, values):
        if self.fail_next_update:
            self.fail_next_update = False
            raise RuntimeError('simulated network failure')

    def _read(self, path):
        node = self.root
        for part in _parts(path):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def _write(self, path, value):
        parts = _parts(path)
        if not parts:
            self.root = copy.deepcopy(value) or {}
            return
        node = self.root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = copy.deepcopy(value)
