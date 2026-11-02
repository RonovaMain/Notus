"""A tiny permissive stand-in for PyQt6, used by tests/smoke_mock.py to execute the UI code without Qt.

It catches NameError / typos in *our* attributes (snake_case names that were never assigned) / wrong call
signatures of our own functions. It does NOT validate real Qt API usage.
"""
from __future__ import annotations

import sys


class _MMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return M()


class M(metaclass=_MMeta):
    """Accepts any call / attribute / operator."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls_mod = type(self).__module__
        # our own classes (not PyQt6.*) must not have undefined snake_case attributes -> real bug
        if not cls_mod.startswith("PyQt6") and "_" in name and not name.startswith("_"):
            raise AttributeError("%s has no attribute %r (typo or missing assignment?)" % (type(self).__name__, name))
        sig = Sig()
        object.__setattr__(self, name, sig)          # cache so connect()/emit() talk to the same object
        return sig

    def __call__(self, *a, **k):
        return M()

    def count(self):
        return 0

    def __or__(self, o): return M()
    __ror__ = __and__ = __rand__ = __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __or__
    def __int__(self): return 0
    def __index__(self): return 0
    def __float__(self): return 0.0
    def __bool__(self): return True
    def __iter__(self): return iter(())
    def __len__(self): return 0
    def __lt__(self, o): return False
    __le__ = __gt__ = __ge__ = __lt__
    def __format__(self, spec): return "0"
    def __str__(self): return "<M>"
    def __hash__(self): return id(self)


def _call_slot(f, args):
    """PyQt lets a slot take fewer arguments than the signal provides - emulate that."""
    import inspect
    try:
        params = list(inspect.signature(f).parameters.values())
    except (TypeError, ValueError):
        return f(*args)
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return f(*args)
    n = len([p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
    return f(*args[:n])


class Sig(M):
    def __init__(self, *a):
        self._slots = []

    def connect(self, f):
        self._slots.append(f)

    def disconnect(self, *a):
        self._slots.clear()

    def emit(self, *a):
        for f in list(self._slots):
            _call_slot(f, a)


class _SigDesc:
    def __set_name__(self, owner, name):
        self.attr = "_sig_" + name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        d = obj.__dict__
        if self.attr not in d:
            d[self.attr] = Sig()
        return d[self.attr]


def pyqtSignal(*a, **k):
    return _SigDesc()


class W(M):
    """Stateful widget base (visibility, enabled, blockSignals, text/value storage)."""

    def __init__(self, *a, **k):
        self.__dict__["_blocked"] = False
        self.__dict__["_visible"] = True
        self.__dict__["_enabled"] = True
        self.__dict__["_text"] = a[0] if a and isinstance(a[0], str) else ""

    def blockSignals(self, b):
        old = self._blocked
        self.__dict__["_blocked"] = bool(b)
        return old

    def signalsBlocked(self): return self._blocked
    def setVisible(self, v): self.__dict__["_visible"] = bool(v)
    def show(self): self.__dict__["_visible"] = True
    def hide(self): self.__dict__["_visible"] = False
    def isVisible(self): return self._visible
    def setEnabled(self, v): self.__dict__["_enabled"] = bool(v)
    def isEnabled(self): return self._enabled
    def text(self): return self._text
    def setText(self, t): self.__dict__["_text"] = str(t)
    def deleteLater(self): pass
    def closeEvent(self, e): pass
    def resizeEvent(self, e): pass
    def keyPressEvent(self, e): pass
    def insertFromMimeData(self, s): pass
    def canInsertFromMimeData(self, s): return False
    def paintEvent(self, e): pass
    def setParent(self, p): pass
    def parent(self): return M()

    def _emit(self, name, *args):
        if not self._blocked:
            getattr(self, name).emit(*args)


class _Items(W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.__dict__["_items"] = []          # [(text, data)]
        self.__dict__["_idx"] = -1

    def addItem(self, text, data=None):
        self._items.append((text, data))
        if self._idx < 0:
            self.__dict__["_idx"] = 0

    def addItems(self, texts):
        for t in texts:
            self.addItem(t)

    def clear(self):
        self.__dict__["_items"] = []
        self.__dict__["_idx"] = -1

    def count(self): return len(self._items)
    def currentIndex(self): return self._idx
    def currentText(self): return self._items[self._idx][0] if 0 <= self._idx < len(self._items) else self._text
    def currentData(self, *a): return self._items[self._idx][1] if 0 <= self._idx < len(self._items) else None
    def findData(self, d): return next((i for i, (_t, x) in enumerate(self._items) if x == d), -1)
    def findText(self, t): return next((i for i, (x, _d) in enumerate(self._items) if x == t), -1)

    def setCurrentIndex(self, i):
        if i != self._idx and -1 <= i < len(self._items):
            self.__dict__["_idx"] = i
            self._emit("currentIndexChanged", i)

    def setCurrentText(self, t):
        i = self.findText(t)
        if i >= 0:
            self.setCurrentIndex(i)
        else:
            self.__dict__["_text"] = t
            self._emit("currentTextChanged", t)


class QComboBox(_Items):
    pass


class QListWidgetItem(M):
    def __init__(self, text="", *a):
        self._text, self._data = text, {}

    def text(self): return self._text
    def setText(self, t): self._text = t
    def data(self, role=None): return self._data.get(id(role) if not isinstance(role, int) else role)
    def setData(self, role, v): self._data[id(role) if not isinstance(role, int) else role] = v


class QListWidget(W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.__dict__["_list"] = []
        self.__dict__["_row"] = -1

    def addItem(self, it): self._list.append(it)
    def clear(self): self.__dict__["_list"] = []; self.__dict__["_row"] = -1
    def count(self): return len(self._list)
    def item(self, i): return self._list[i]
    def currentRow(self): return self._row
    def currentItem(self): return self._list[self._row] if 0 <= self._row < len(self._list) else None

    def setCurrentRow(self, r):
        self.__dict__["_row"] = r
        self._emit("currentRowChanged", r)

    def setCurrentItem(self, it):
        if it in self._list:
            self.__dict__["_row"] = self._list.index(it)


class _Valued(W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.__dict__["_v"] = 0
        self.__dict__["_lo"], self.__dict__["_hi"] = 0, 99

    def value(self): return self._v
    def setRange(self, lo, hi): self.__dict__["_lo"], self.__dict__["_hi"] = lo, hi; self.__dict__["_v"] = min(max(self._v, lo), hi)
    def setMinimum(self, lo): self.__dict__["_lo"] = lo
    def setMaximum(self, hi): self.__dict__["_hi"] = hi

    def setValue(self, v):
        v = min(max(v, self._lo), self._hi)
        if v != self._v:
            self.__dict__["_v"] = v
            self._emit("valueChanged", v)


class QSpinBox(_Valued):
    def setValue(self, v): super().setValue(int(v))


class QDoubleSpinBox(_Valued):
    pass


class QSlider(_Valued):
    pass


class QCheckBox(W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.__dict__["_on"] = False

    def isChecked(self): return self._on

    def setChecked(self, b):
        if bool(b) != self._on:
            self.__dict__["_on"] = bool(b)
            self._emit("toggled", bool(b))


class QPushButton(QCheckBox):
    pass


class QLineEdit(W):
    def setText(self, t):
        if str(t) != self._text:
            self.__dict__["_text"] = str(t)
            self._emit("textChanged", str(t))


class QPlainTextEdit(W):
    def toPlainText(self): return self._text
    def clear(self): self.setPlainText("")

    def setPlainText(self, t):
        if t != self._text:
            self.__dict__["_text"] = t
            self._emit("textChanged")


class QLabel(W):
    pass


class QFileDialog(M):
    @staticmethod
    def getOpenFileNames(*a, **k): return ([], "")
    @staticmethod
    def getOpenFileName(*a, **k): return ("", "")
    @staticmethod
    def getSaveFileName(*a, **k): return ("", "")
    @staticmethod
    def getExistingDirectory(*a, **k): return ""


class QInputDialog(M):
    @staticmethod
    def getText(*a, **k): return ("", False)


class QTimer(M):
    def __init__(self, *a, **k):
        self.timeout = Sig()

    @staticmethod
    def singleShot(ms, f=None, *a):
        if callable(f):
            f()

    def setInterval(self, ms): pass
    def setSingleShot(self, b): pass
    def start(self, *a): pass
    def stop(self): pass


class QThread(M):
    def __init__(self, *a, **k):
        pass

    def start(self, *a): pass          # threads are not run in the mock
    def wait(self, *a): return True
    def isRunning(self): return False
    def msleep(self, ms): pass


class QApplication(M):
    _inst = None

    def __init__(self, *a, **k):
        QApplication._inst = self

    @staticmethod
    def instance(): return QApplication._inst
    @staticmethod
    def clipboard(): return M()
    @staticmethod
    def setOverrideCursor(*a): pass
    @staticmethod
    def restoreOverrideCursor(*a): pass
    def exec(self): return 0


class QObject(M):
    def __init__(self, *a, **k):
        pass


class QProcess(M):
    class ProcessState: NotRunning = 0
    class ProcessChannelMode: MergedChannels = 1
    class ProcessError: FailedToStart = 2

    def __init__(self, *a, **k):
        self._running = False

    def start(self, *a): self._running = True
    def state(self): return 1 if self._running else 0
    def processId(self): return 4321
    def kill(self): self._running = False
    terminate = kill
    def waitForFinished(self, *a): self._running = False; return True
    def readAllStandardOutput(self): return b""


SPECIAL = {k: v for k, v in dict(
    QComboBox=QComboBox, QListWidgetItem=QListWidgetItem, QListWidget=QListWidget, QSpinBox=QSpinBox,
    QDoubleSpinBox=QDoubleSpinBox, QSlider=QSlider, QCheckBox=QCheckBox, QPushButton=QPushButton, QLineEdit=QLineEdit,
    QPlainTextEdit=QPlainTextEdit, QLabel=QLabel, QFileDialog=QFileDialog, QInputDialog=QInputDialog, QTimer=QTimer,
    QThread=QThread, QApplication=QApplication, QObject=QObject, QProcess=QProcess, pyqtSignal=pyqtSignal,
).items()}
_cache: dict = {}


class MetaM(_MMeta):
    """Class-level attribute access (e.g. QPalette.ColorRole.Window) returns a permissive object."""

    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return M()


def getter(modname):
    def __getattr__(name):
        if name in SPECIAL:
            return SPECIAL[name]
        if name.startswith("__"):
            raise AttributeError(name)
        if name in ("Qt",):
            return M()
        if name not in _cache:
            _cache[name] = MetaM(name, (W,), {"__module__": "PyQt6." + modname})
        return _cache[name]
    return __getattr__
