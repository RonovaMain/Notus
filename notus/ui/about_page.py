"""About page."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import AUTHOR, REPO_URL, __version__, paths
from ..i18n import tr


class AboutPage(QWidget):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.addStretch(1)
        card = QFrame()
        card.setObjectName("Card")
        card.setMaximumWidth(640)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(10)
        logo = QLabel()
        pm = QPixmap(str(paths.asset("icon.png")))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        name = QLabel("Notus")
        name.setObjectName("Title")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)
        ver = QLabel("%s %s" % (tr("Version"), __version__))
        ver.setObjectName("Muted")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)
        desc = QLabel(tr("A private, offline chat for GGUF language models that also runs on old hardware: "
                         "CPUs without AVX2 and Pascal-era NVIDIA cards such as the GTX 1050 Ti."))
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(desc)
        links = QLabel("<b>%s:</b> %s<br><b>GitHub:</b> <a href='%s'>%s</a>" % (tr("Developer"), AUTHOR, REPO_URL, REPO_URL))
        links.setTextFormat(Qt.TextFormat.RichText)
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(links)
        credits = QLabel(tr("Built with llama.cpp (MIT) and Qt / PyQt6 (GPL-3.0). Released under GPL-3.0."))
        credits.setObjectName("Muted")
        credits.setWordWrap(True)
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(credits)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
