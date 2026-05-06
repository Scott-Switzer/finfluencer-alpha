"""Compatibility shim for running `python -m finfluencer_alpha` from the repo root."""

from pathlib import Path

_src_pkg = Path(__file__).resolve().parent.parent / "src" / "finfluencer_alpha"
if _src_pkg.exists():
    __path__.append(str(_src_pkg))
