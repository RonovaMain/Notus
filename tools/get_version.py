"""Print the app version from notus/__init__.py (used by the CI workflows)."""
import pathlib
import re

src = (pathlib.Path(__file__).resolve().parent.parent / "notus" / "__init__.py").read_text(encoding="utf-8")
print(re.search(r'__version__\s*=\s*"([^"]+)"', src).group(1))
