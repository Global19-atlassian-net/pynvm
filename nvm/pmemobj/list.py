import collections
import sys

from .compat import recursive_repr, abc

from _pmem import ffi    # XXX refactor to make this import unneeded?

# XXX: refactor to allocate this instead of hardcoding it.
LIST_POBJPTR_ARRAY_TYPE_NUM = 30


class PersistentList(abc.MutableSequence):
    """Persistent version of the 'list' type."""

    # XXX locking!
    # XXX All bookkeeping attrs should be _v_xxxx so that all other attrs
    #     (other than _p_mm) can be made persistent.

    def __init__(self, *args, **kw):
        if not args:
            return
        if len(args) != 1:
            raise TypeError("PersistentList takes at most 1"
                            " argument, {} given".format(len(args)))
        self.extend(args[0])

    def _p_new(self, manager):
        mm = self._p_mm = manager
        with mm.transaction():
            # XXX Will want to implement a freelist here, like CPython
            self._p_oid = mm.zalloc(ffi.sizeof('PListObject'))
            ob = ffi.cast('PObject *', mm.direct(self._p_oid))
            ob.ob_type = mm._get_type_code(PersistentList)
        self._body = ffi.cast('PListObject *', mm.direct(self._p_oid))

    def _p_resurrect(self, manager, oid):
        mm = self._p_mm = manager
        self._p_oid = oid
        self._body = ffi.cast('PListObject *', mm.direct(oid))

    # Methods and properties needed to implement the ABC required methods.

    @property
    def _size(self):
        return ffi.cast('PVarObject *', self._body).ob_size

    @property
    def _allocated(self):
        return self._body.allocated

    @property
    def _items(self):
        mm = self._p_mm
        ob_items = mm.otuple(self._body.ob_items)
        if ob_items == mm.OID_NULL:
            return None
        return ffi.cast('PObjPtr *', mm.direct(ob_items))

    def _resize(self, newsize):
        # Note that resize does *not* set self._size.  That needs to be done by
        # the caller such that that the we never expose invalid item cells.
        # The size field is covered by a snapshot done here, though.
        mm = self._p_mm
        allocated = self._allocated
        # Only realloc if we don't have enough space already.
        if (allocated >= newsize and newsize >= allocated >> 1):
            assert self._items != None or newsize == 0
            with mm.transaction():
                ob = ffi.cast('PVarObject *', self._body)
                mm.snapshot_range(ffi.addressof(ob, 'ob_size'),
                                  ffi.sizeof('size_t'))
                ob.ob_size = newsize
            return
        # We use CPython's overallocation algorithm.
        new_allocated = (newsize >> 3) + (3 if newsize < 9 else 6) + newsize
        if newsize == 0:
            new_allocated = 0
        items = self._items
        with mm.transaction():
            if items is None:
                items = mm.zalloc(new_allocated * ffi.sizeof('PObjPtr'),
                                  type_num=LIST_POBJPTR_ARRAY_TYPE_NUM)
            else:
                items = mm.zrealloc(self._body.ob_items,
                                   new_allocated * ffi.sizeof('PObjPtr'),
                                   LIST_POBJPTR_ARRAY_TYPE_NUM)
            mm.snapshot_range(self._body, ffi.sizeof('PListObject'))
            self._body.ob_items = items
            self._body.allocated = new_allocated

    def insert(self, index, value):
        mm = self._p_mm
        size = self._size
        newsize = size + 1
        with mm.transaction():
            self._resize(newsize)
            if index < 0:
                index += size
                if index < 0:
                    index = 0
            if index > size:
                index = size
            items = self._items
            mm.snapshot_range(items + index,
                              ffi.offsetof('PObjPtr *', newsize))
            for i in range(size, index, -1):
                items[i] = items[i-1]
            v_oid = mm.persist(value)
            mm.incref(v_oid)
            items[index] = v_oid
            ffi.cast('PVarObject *', self._body).ob_size = newsize

    def _normalize_index(self, index):
        try:
            index = int(index)
        except TypeError:
            # Assume it is a slice
            # XXX fixme
            raise NotImplementedError("Slicing not yet implemented")
        if index < 0:
            index += self._size
        if index < 0 or index >= self._size:
            raise IndexError(index)
        return index

    def __setitem__(self, index, value):
        mm = self._p_mm
        index = self._normalize_index(index)
        items = self._items
        with mm.transaction():
            v_oid = mm.persist(value)
            mm.snapshot_range(ffi.addressof(items, index),
                              ffi.sizeof('PObjPtr *'))
            mm.xdecref(items[index])
            items[index] = v_oid
            mm.incref(v_oid)

    def __delitem__(self, index):
        mm = self._p_mm
        index = self._normalize_index(index)
        size = self._size
        newsize = size - 1
        items = self._items
        with mm.transaction():
            ffi.cast('PVarObject *', self._body).ob_size = newsize
            # We can't completely hide the process of transformation...this
            # really needs a lock (or translation to GIL-locked C).
            mm.snapshot_range(ffi.addressof(items, index),
                              ffi.offsetof('PObjPtr *', size))
            oid = mm.otuple(items[index])
            for i in range(index, newsize):
                items[i] = items[i+1]
            mm.decref(oid)
            self._resize(newsize)

    def __getitem__(self, index):
        index = self._normalize_index(index)
        items = self._items
        return self._p_mm.resurrect(items[index])

    def __len__(self):
        return self._size

    # Additional list methods not provided by the ABC.

    @recursive_repr()
    def __repr__(self):
        return "{}([{}])".format(self.__class__.__name__,
                                 ', '.join("{!r}".format(x) for x in self))

    def __eq__(self, other):
        if not (isinstance(other, PersistentList) or
                isinstance(other, list)):
            return NotImplemented
        if len(self) != len(other):
            return False
        for i in range(len(self)):
            if self[i] != other[i]:
                return False
        return True

    if sys.version_info[0] < 3:
        def __ne__(self, other):
            return not self == other

    def clear(self):
        mm = self._p_mm
        if self._size == 0:
            return
        items = self._items
        with mm.transaction():
            size = self._size
            # Set size to zero now so we never have an invalid state.
            ffi.cast('PVarObject *', self._body).ob_size = 0
            for i in range(size):
                # Grab oid in tuple form so the assignment can't change it
                oid = mm.otuple(items[i])
                items[i] = mm.OID_NULL
                mm.decref(oid)
            self._resize(0)

    # Additional methods required by the pmemobj API.

    def _p_traverse(self):
        items = self._items
        for i in range(len(self)):
            yield items[i]

    def _p_substructures(self):
        return ((self._body.ob_items, LIST_POBJPTR_ARRAY_TYPE_NUM),)

    def _p_deallocate(self):
        self.clear()
