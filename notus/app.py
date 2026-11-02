"""Application entry point."""
from __future__ import annotations

import os
import sys
import time
import traceback

from . import APP_NAME, __version__, i18n, paths


def _install_excepthook() -> None:
    def hook(etype, value, tb) -> None:
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            with open(paths.data_dir() / "crash.log", "a", encoding="utf-8") as f:
                f.write("--- %s ---\n%s\n" % (time.ctime(), text))
        except OSError:
            pass
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or "--selftest" in sys.argv:
            try:
                sys.__stderr__.write(text)
            except Exception:
                pass
            os._exit(1)                      # headless self-test: fail fast instead of waiting for a dialog
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, APP_NAME, text[-1800:])
        except Exception:
            pass
        try:
            sys.__excepthook__(etype, value, tb)
        except Exception:
            pass

    sys.excepthook = hook


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    selftest = "--selftest" in argv
    if selftest:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _install_excepthook()

    from PyQt6.QtCore import QLocale, QTimer
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from .store import Store
    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("RonovaDev")
    icon = paths.asset("icon.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    store = Store()
    store.load()
    lang = store.s.language
    if lang == "auto":
        lang = "ru" if QLocale.system().language() == QLocale.Language.Russian else "en"
    i18n.set_language(lang)
    colors = theme.apply(app, store.s.theme, store.s.accent, store.s.font_size)

    win = MainWindow(store, colors)
    win.show()
    if selftest:
        QTimer.singleShot(1500, win.close)
    code = app.exec()
    store.save()
    return code
