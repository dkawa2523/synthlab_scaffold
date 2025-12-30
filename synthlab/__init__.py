from __future__ import annotations

from pathlib import Path

__all__ = ["__version__"]
__version__ = "0.0.0"

_pkg_root = Path(__file__).resolve().parent
_src_pkg = _pkg_root.parent / "src" / "synthlab"
if _src_pkg.is_dir():
    __path__.append(str(_src_pkg))
