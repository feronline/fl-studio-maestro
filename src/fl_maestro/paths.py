"""Where things live on disk: Maestro projects and FL Studio's user data folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _windows_documents() -> Path | None:
    """Resolve the real Documents folder (handles OneDrive redirection and localized names)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        fid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                   (wintypes.BYTE * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        return None
    return None


def documents_dir() -> Path:
    if sys.platform == "win32":
        found = _windows_documents()
        if found:
            return found
    return Path.home() / "Documents"


def fl_user_dir() -> Path:
    """FL Studio user data folder (override with FL_MAESTRO_FL_USER_DIR)."""
    override = os.environ.get("FL_MAESTRO_FL_USER_DIR")
    if override:
        return Path(override)
    return documents_dir() / "Image-Line" / "FL Studio"


def hardware_dir() -> Path:
    return fl_user_dir() / "Settings" / "Hardware"


def pianoroll_scripts_dir() -> Path:
    return fl_user_dir() / "Settings" / "Piano roll scripts"


def projects_root() -> Path:
    """Maestro project sessions (override with FL_MAESTRO_HOME)."""
    override = os.environ.get("FL_MAESTRO_HOME")
    return Path(override) if override else Path.home() / "FLMaestro"


def output_dir(explicit: str | None = None) -> Path:
    """Where finished files go: the given folder, else FL_MAESTRO_OUTPUT_DIR, else the folder
    Claude Code was opened in (CLAUDE_PROJECT_DIR, then the server's working directory)."""
    for candidate in (explicit, os.environ.get("FL_MAESTRO_OUTPUT_DIR"), os.environ.get("CLAUDE_PROJECT_DIR")):
        if candidate:
            path = Path(candidate).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return path
    return Path.cwd()
