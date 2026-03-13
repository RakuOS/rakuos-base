"""
webapps.py — Web App management for RakuOS Software Center.

System catalog:   /usr/share/rakuos/webapps/*.json  (read-only, ships with image)
User installed:   ~/.local/share/rakuos/webapps/*.json
Desktop files:    ~/.local/share/applications/rakuos-webapp-{id}.desktop
Icons:            ~/.local/share/rakuos/webapps/icons/{id}.png (cached from catalog)

Each catalog JSON:
{
  "id":          "netflix",
  "name":        "Netflix",
  "url":         "https://netflix.com",
  "description": "Watch TV shows and movies",
  "summary":     "Streaming entertainment",
  "icon":        "netflix.png",          # relative to catalog dir
  "icon_url":    "https://...",          # fallback remote icon
  "categories":  ["AudioVideo", "Video"],
  "keywords":    ["streaming", "movies", "tv"]
}
"""

import os
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

CATALOG_DIR   = Path("/usr/share/rakuos/webapps")
INSTALL_DIR   = Path.home() / ".local/share/rakuos/webapps"
ICON_DIR      = Path.home() / ".local/share/rakuos/webapps/icons"
DESKTOP_DIR   = Path.home() / ".local/share/applications"
DESKTOP_PREFIX = "rakuos-webapp-"


def _ensure_dirs():
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)


# ── Catalog ───────────────────────────────────────────────────────────────────

def get_catalog() -> list[dict]:
    """Return all web apps from the system catalog."""
    apps = []
    if not CATALOG_DIR.exists():
        return apps
    for path in sorted(CATALOG_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            data["source"]    = "webapp"
            data["installed"] = is_installed(data["id"])
            data["icon_path"] = _resolve_icon(data)
            apps.append(data)
        except Exception as e:
            print(f"[webapps] Failed to read {path}: {e}")
    return apps


def get_catalog_by_id(app_id: str) -> dict | None:
    """Return a single catalog entry by id."""
    path = CATALOG_DIR / f"{app_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        data["source"]    = "webapp"
        data["installed"] = is_installed(app_id)
        data["icon_path"] = _resolve_icon(data)
        return data
    except Exception:
        return None


def _resolve_icon(app: dict) -> str:
    """Return local icon path, downloading from icon_url if needed."""
    app_id   = app.get("id", "")
    icon_name = app.get("icon", "")

    # 1. Check catalog dir first
    if icon_name:
        catalog_icon = CATALOG_DIR / icon_name
        if catalog_icon.exists():
            return str(catalog_icon)

    # 2. Check cached user icon
    cached = ICON_DIR / f"{app_id}.png"
    if cached.exists():
        return str(cached)

    # 3. Download from icon_url
    icon_url = app.get("icon_url", "")
    if icon_url:
        try:
            _ensure_dirs()
            urllib.request.urlretrieve(icon_url, cached)
            return str(cached)
        except Exception as e:
            print(f"[webapps] Failed to download icon for {app_id}: {e}")

    return ""


# ── Install / Uninstall ───────────────────────────────────────────────────────

def is_installed(app_id: str) -> bool:
    return (INSTALL_DIR / f"{app_id}.json").exists()


def get_installed() -> list[dict]:
    """Return all installed web apps with full metadata."""
    apps = []
    if not INSTALL_DIR.exists():
        return apps
    for path in sorted(INSTALL_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            data["installed"] = True
            apps.append(data)
        except Exception as e:
            print(f"[webapps] Failed to read installed {path}: {e}")
    return apps


def install(app_id: str) -> tuple[bool, str]:
    """
    Install a web app from the catalog.
    Returns (success, message).
    """
    app = get_catalog_by_id(app_id)
    if not app:
        return False, f"Web app '{app_id}' not found in catalog."

    try:
        _ensure_dirs()

        # Resolve and cache icon
        icon_path = _resolve_icon(app)
        if not icon_path:
            # Use a generic web icon as fallback
            icon_path = "web-browser"

        # Write installed JSON sidecar
        installed_data = {
            "id":          app["id"],
            "name":        app["name"],
            "url":         app["url"],
            "description": app.get("description", ""),
            "summary":     app.get("summary", ""),
            "icon_path":   icon_path,
            "categories":  app.get("categories", []),
            "keywords":    app.get("keywords", []),
            "source":      "webapp",
            "installed":   True,
        }
        (INSTALL_DIR / f"{app_id}.json").write_text(
            json.dumps(installed_data, indent=2))

        # Write .desktop file
        _write_desktop(app, icon_path)

        # Update desktop database
        subprocess.run(
            ["update-desktop-database", str(DESKTOP_DIR)],
            capture_output=True)

        return True, f"{app['name']} installed successfully."
    except Exception as e:
        return False, f"Failed to install {app_id}: {e}"


def uninstall(app_id: str) -> tuple[bool, str]:
    """
    Uninstall a web app.
    Returns (success, message).
    """
    try:
        name = app_id
        sidecar = INSTALL_DIR / f"{app_id}.json"
        if sidecar.exists():
            data = json.loads(sidecar.read_text())
            name = data.get("name", app_id)
            sidecar.unlink()

        desktop = DESKTOP_DIR / f"{DESKTOP_PREFIX}{app_id}.desktop"
        if desktop.exists():
            desktop.unlink()

        subprocess.run(
            ["update-desktop-database", str(DESKTOP_DIR)],
            capture_output=True)

        return True, f"{name} uninstalled."
    except Exception as e:
        return False, f"Failed to uninstall {app_id}: {e}"


def _write_desktop(app: dict, icon_path: str):
    """Write a .desktop launcher for the web app using cefpython3."""
    app_id = app["id"]
    name   = app["name"]
    url    = app["url"]
    desc   = app.get("summary") or app.get("description", "")
    cats   = ";".join(app.get("categories", ["Network"])) + ";"

    # Launcher command — uses cefpython3 wrapper
    exec_cmd = f"/usr/bin/rakuos-webapp-launcher '{url}' '{name}'"

    desktop_content = f"""[Desktop Entry]
Name={name}
Comment={desc}
Exec={exec_cmd}
Icon={icon_path}
Terminal=false
Type=Application
Categories={cats}
StartupNotify=true
StartupWMClass=rakuos-webapp-{app_id}
X-RakuOS-WebApp=true
X-RakuOS-WebApp-ID={app_id}
X-RakuOS-WebApp-URL={url}
"""
    desktop_path = DESKTOP_DIR / f"{DESKTOP_PREFIX}{app_id}.desktop"
    desktop_path.write_text(desktop_content)
    desktop_path.chmod(0o755)
