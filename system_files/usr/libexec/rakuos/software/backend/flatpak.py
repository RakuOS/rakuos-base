"""
flatpak.py — Flatpak package management
"""

import subprocess
import json
from typing import Optional


def get_installed_flatpaks() -> list[dict]:
    """Return list of installed Flatpaks."""
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application,name,version,description,origin"],
            capture_output=True, text=True
        )
        apps = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                apps.append({
                    "id": parts[0].strip(),
                    "name": parts[1].strip() if len(parts) > 1 else parts[0],
                    "version": parts[2].strip() if len(parts) > 2 else "",
                    "summary": parts[3].strip() if len(parts) > 3 else "",
                    "origin": parts[4].strip() if len(parts) > 4 else "flathub",
                    "source": "flatpak",
                    "installed": True,
                    "icon": "",
                    "screenshots": [],
                    "categories": [],
                    "pkg_name": parts[0].strip(),
                })
        return apps
    except Exception:
        return []


def is_flatpak_installed(app_id: str) -> bool:
    installed = get_installed_flatpaks()
    return any(a["id"] == app_id for a in installed)


def search_flatpaks(query: str, limit: int = 30) -> list[dict]:
    """Search Flathub for apps."""
    try:
        result = subprocess.run(
            ["flatpak", "search", "--columns=application,name,version,description,origin", query],
            capture_output=True, text=True, timeout=15
        )
        apps = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].strip():
                app_id = parts[0].strip()
                apps.append({
                    "id": app_id,
                    "name": parts[1].strip() if len(parts) > 1 else app_id,
                    "version": parts[2].strip() if len(parts) > 2 else "",
                    "summary": parts[3].strip() if len(parts) > 3 else "",
                    "origin": parts[4].strip() if len(parts) > 4 else "flathub",
                    "source": "flatpak",
                    "installed": is_flatpak_installed(app_id),
                    "icon": "",
                    "screenshots": [],
                    "categories": [],
                    "pkg_name": app_id,
                })
            if len(apps) >= limit:
                break
        return apps
    except Exception:
        return []


def install_flatpak_stream(app_id: str):
    """Generator that yields output lines from flatpak install."""
    try:
        proc = subprocess.Popen(
            ["flatpak", "install", "-y", "flathub", app_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait()
        yield f"__done__{proc.returncode}"
    except Exception as e:
        yield f"Error: {e}"
        yield "__done__1"


def remove_flatpak_stream(app_id: str):
    """Generator that yields output lines from flatpak remove."""
    try:
        proc = subprocess.Popen(
            ["flatpak", "remove", "-y", app_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait()
        yield f"__done__{proc.returncode}"
    except Exception as e:
        yield f"Error: {e}"
        yield "__done__1"


def get_flatpak_updates() -> list[dict]:
    """Return list of Flatpaks with available updates."""
    try:
        result = subprocess.run(
            ["flatpak", "remote-ls", "--updates", "--app",
             "--columns=application,name,version"],
            capture_output=True, text=True, timeout=20
        )
        apps = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                apps.append({
                    "id": parts[0].strip(),
                    "name": parts[1].strip(),
                    "version": parts[2].strip() if len(parts) > 2 else "",
                    "source": "flatpak",
                })
        return apps
    except Exception:
        return []


def update_all_flatpaks_stream():
    """Generator that yields output from flatpak update."""
    try:
        proc = subprocess.Popen(
            ["flatpak", "update", "-y"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait()
        yield f"__done__{proc.returncode}"
    except Exception as e:
        yield f"Error: {e}"
        yield "__done__1"
