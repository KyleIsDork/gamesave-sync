"""Entry point for frozen (PyInstaller) builds.

PyInstaller runs the target script as ``__main__`` with no parent package, so
``gamesync/__main__.py``'s relative imports (``from . import APP_NAME``) raise
``ImportError`` in a frozen build even though they are correct for
``python -m gamesync``. This shim imports the package absolutely instead.
"""

from gamesync.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
