from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def get_version() -> str:
    """Return the application version stored in the repository VERSION file."""
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


__version__ = get_version()
