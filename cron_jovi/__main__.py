import os

# The AppImage's libraries are loaded by now, and must not reach the commands workflows run.
if os.environ.get("APPIMAGE"):
    for name in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONNOUSERSITE"):
        os.environ.pop(name, None)

from .cli import main  # noqa: E402

raise SystemExit(main())
