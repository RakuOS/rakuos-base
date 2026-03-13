"""
appimages.py — AppImage management for RakuOS Software Center.

Install dir:  ~/.local/share/rakuos/appimages/
Icons:        ~/.local/share/rakuos/appimages/icons/
Sidecars:     ~/.local/share/rakuos/appimages/{name}.json
Desktop:      ~/.local/share/applications/rakuos-appimage-{name}.desktop

Sidecar JSON schema:
{
  "id":             "obsidian",
  "name":           "Obsidian",
  "version":        "1.5.3",
  "summary":        "A powerful note-taking app",
  "description":    "...",
  "installed_path": "~/.local/share/rakuos/appimages/Obsidian-1.5.3.AppImage",
  "desktop_path":   "~/.local/share/applications/rakuos-appimage-obsidian.desktop",
  "icon_path":      "~/.local/share/rakuos/appimages/icons/obsidian.png",
  "categories":     ["Office"],
  "update_source":  "github",        # github | gitlab | url | none
  "update_url":     "https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest",
  "update_pattern": "Obsidian-*.AppImage",
  "installed_at":   "2026-03-13T00:00:00Z",
  "last_checked":   "2026-03-13T00:00:00Z"
}
"""

import os
import json
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import urllib.error
import re
from datetime import datetime, timezone
from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

INSTALL_DIR    = Path.home() / ".local/share/rakuos/appimages"
ICON_DIR       = Path.home() / ".local/share/rakuos/appimages/icons"
DESKTOP_DIR    = Path.home() / ".local/share/applications"
DESKTOP_PREFIX = "rakuos-appimage-"
EXTRACT_TMP    = Path(tempfile.gettempdir()) / "rakuos-appimage-extract"

GITHUB_API  = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITLAB_API  = "https://gitlab.com/api/v4/projects/{project}/releases"


def _ensure_dirs():
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_appimage_info(path: str) -> dict:
    """
    Extract metadata from an AppImage file.
    Uses --appimage-extract to dump squashfs, then reads .desktop + icon.
    Returns dict with name, version, summary, description, icon_data, categories,
    update_source, update_url, update_pattern.
    """
    path = Path(path)
    if not path.exists():
        return {}

    extract_dir = EXTRACT_TMP / path.stem
    try:
        # Clean previous extraction
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Make executable and extract
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        result = subprocess.run(
            [str(path), "--appimage-extract"],
            capture_output=True, text=True, timeout=60,
            cwd=str(extract_dir)
        )

        squashfs = extract_dir / "squashfs-root"
        if not squashfs.exists():
            # Some AppImages extract directly
            squashfs = extract_dir

        info = _parse_extracted(squashfs, path.name)
        return info

    except subprocess.TimeoutExpired:
        print(f"[appimages] Extraction timed out for {path}")
        return {"name": path.stem, "version": "", "summary": ""}
    except Exception as e:
        print(f"[appimages] Extraction error for {path}: {e}")
        return {"name": path.stem, "version": "", "summary": ""}
    finally:
        # Clean up extract dir
        try:
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
        except Exception:
            pass


def _parse_extracted(squashfs: Path, filename: str) -> dict:
    """Parse desktop file and icon from extracted squashfs root."""
    info = {
        "name":           "",
        "version":        "",
        "summary":        "",
        "description":    "",
        "icon_data":      None,   # raw bytes
        "icon_ext":       "png",
        "categories":     [],
        "update_source":  "none",
        "update_url":     "",
        "update_pattern": "",
    }

    # ── Find .desktop file ────────────────────────────────────────────────────
    desktop_files = list(squashfs.glob("*.desktop"))
    if not desktop_files:
        desktop_files = list(squashfs.glob("**/*.desktop"))

    desktop_data = {}
    if desktop_files:
        desktop_data = _parse_desktop_file(desktop_files[0])

    info["name"]        = desktop_data.get("Name", Path(filename).stem)
    info["summary"]     = desktop_data.get("Comment", "")
    info["description"] = desktop_data.get("Comment", "")
    info["version"]     = desktop_data.get("X-AppImage-Version", "")
    cats_str            = desktop_data.get("Categories", "")
    info["categories"]  = [c for c in cats_str.split(";") if c.strip()]

    # ── Parse update info from X-AppImage-UpdateInformation ──────────────────
    update_info = desktop_data.get("X-AppImage-UpdateInformation", "")
    if update_info:
        parsed = _parse_update_info(update_info)
        info.update(parsed)

    # ── Find icon ─────────────────────────────────────────────────────────────
    icon_name = desktop_data.get("Icon", "")
    icon_data, icon_ext = _find_icon(squashfs, icon_name)
    info["icon_data"] = icon_data
    info["icon_ext"]  = icon_ext

    return info


def _parse_desktop_file(path: Path) -> dict:
    """Parse a .desktop file into a dict."""
    result = {}
    in_entry = False
    try:
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if line == "[Desktop Entry]":
                in_entry = True
                continue
            if line.startswith("[") and in_entry:
                break
            if in_entry and "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip()
    except Exception:
        pass
    return result


def _find_icon(squashfs: Path, icon_name: str) -> tuple[bytes | None, str]:
    """Find and return icon bytes + extension from squashfs."""
    candidates = []

    # .DirIcon is the standard AppImage icon
    diricon = squashfs / ".DirIcon"
    if diricon.exists():
        candidates.append(diricon)

    # Named icon in root
    if icon_name:
        for ext in ("png", "svg", "xpm"):
            p = squashfs / f"{icon_name}.{ext}"
            if p.exists():
                candidates.append(p)

    # Search usr/share/icons
    if icon_name:
        for p in squashfs.glob(f"usr/share/icons/**/{icon_name}.*"):
            candidates.append(p)
        for p in squashfs.glob(f"usr/share/pixmaps/{icon_name}.*"):
            candidates.append(p)

    # Fallback: any png in root
    if not candidates:
        candidates = list(squashfs.glob("*.png"))[:1]

    for candidate in candidates:
        try:
            ext = candidate.suffix.lstrip(".") or "png"
            return candidate.read_bytes(), ext
        except Exception:
            continue

    return None, "png"


def _parse_update_info(update_info: str) -> dict:
    """
    Parse X-AppImage-UpdateInformation field.
    Formats:
      gh-releases-zsync|owner|repo|latest|*.AppImage.zsync
      gl-releases-zsync|namespace/repo|latest|*.AppImage.zsync
      zsync|https://example.com/latest/*.AppImage.zsync
    """
    result = {
        "update_source":  "none",
        "update_url":     "",
        "update_pattern": "",
    }
    if not update_info or update_info.lower() == "none":
        return result

    parts = update_info.split("|")

    if parts[0].startswith("gh-releases"):
        # gh-releases-zsync|owner|repo|tag|pattern
        if len(parts) >= 4:
            owner   = parts[1]
            repo    = parts[2]
            pattern = parts[4].replace(".zsync", "") if len(parts) > 4 else "*.AppImage"
            result["update_source"]  = "github"
            result["update_url"]     = GITHUB_API.format(owner=owner, repo=repo)
            result["update_pattern"] = pattern

    elif parts[0].startswith("gl-releases"):
        # gl-releases-zsync|namespace/repo|tag|pattern
        if len(parts) >= 3:
            project = urllib.parse.quote(parts[1], safe="")
            pattern = parts[3].replace(".zsync", "") if len(parts) > 3 else "*.AppImage"
            result["update_source"]  = "gitlab"
            result["update_url"]     = GITLAB_API.format(project=project)
            result["update_pattern"] = pattern

    elif parts[0] == "zsync" and len(parts) >= 2:
        url = parts[1]
        result["update_source"]  = "url"
        result["update_url"]     = url.replace(".zsync", "")
        result["update_pattern"] = Path(url).name.replace(".zsync", "")

    return result


# ── Install / Uninstall ───────────────────────────────────────────────────────

def get_installed() -> list[dict]:
    """Return all installed AppImages from sidecar JSON files."""
    apps = []
    if not INSTALL_DIR.exists():
        return apps
    for path in sorted(INSTALL_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            data["installed"] = True
            data["source"]    = "appimage"
            apps.append(data)
        except Exception as e:
            print(f"[appimages] Failed to read sidecar {path}: {e}")
    return apps


def is_installed(app_id: str) -> bool:
    return (INSTALL_DIR / f"{app_id}.json").exists()


def install_appimage(src_path: str) -> tuple[bool, str, dict]:
    """
    Install an AppImage from src_path.
    Returns (success, message, app_info_dict).
    """
    src = Path(src_path)
    if not src.exists():
        return False, f"File not found: {src_path}", {}

    try:
        _ensure_dirs()

        # Extract metadata
        info = extract_appimage_info(src_path)
        name    = info.get("name") or src.stem
        version = info.get("version", "")

        # Sanitize id
        app_id = re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")

        # Copy AppImage to install dir
        dest_name = f"{app_id}.AppImage"
        dest_path = INSTALL_DIR / dest_name
        shutil.copy2(src, dest_path)
        dest_path.chmod(dest_path.stat().st_mode | stat.S_IEXEC)

        # Save icon
        icon_path = ""
        if info.get("icon_data"):
            ext = info.get("icon_ext", "png")
            icon_path = str(ICON_DIR / f"{app_id}.{ext}")
            Path(icon_path).write_bytes(info["icon_data"])

        # Write .desktop
        desktop_path = _write_desktop(app_id, name, str(dest_path),
                                       icon_path, info)

        # Write sidecar JSON
        sidecar = {
            "id":             app_id,
            "name":           name,
            "version":        version,
            "summary":        info.get("summary", ""),
            "description":    info.get("description", ""),
            "installed_path": str(dest_path),
            "desktop_path":   desktop_path,
            "icon_path":      icon_path,
            "categories":     info.get("categories", []),
            "update_source":  info.get("update_source", "none"),
            "update_url":     info.get("update_url", ""),
            "update_pattern": info.get("update_pattern", ""),
            "installed_at":   datetime.now(timezone.utc).isoformat(),
            "last_checked":   "",
            "source":         "appimage",
            "installed":      True,
        }
        (INSTALL_DIR / f"{app_id}.json").write_text(
            json.dumps(sidecar, indent=2))

        # Update desktop database
        subprocess.run(["update-desktop-database", str(DESKTOP_DIR)],
                       capture_output=True)

        return True, f"{name} installed successfully.", sidecar

    except Exception as e:
        return False, f"Failed to install AppImage: {e}", {}


def uninstall_appimage(app_id: str) -> tuple[bool, str]:
    """Uninstall an AppImage by id."""
    try:
        name = app_id
        sidecar_path = INSTALL_DIR / f"{app_id}.json"

        if sidecar_path.exists():
            sidecar = json.loads(sidecar_path.read_text())
            name = sidecar.get("name", app_id)

            # Remove AppImage file
            ai_path = Path(sidecar.get("installed_path", ""))
            if ai_path.exists():
                ai_path.unlink()

            # Remove icon
            icon_path = Path(sidecar.get("icon_path", ""))
            if icon_path.exists():
                icon_path.unlink()

            # Remove sidecar
            sidecar_path.unlink()

        # Remove desktop file
        desktop = DESKTOP_DIR / f"{DESKTOP_PREFIX}{app_id}.desktop"
        if desktop.exists():
            desktop.unlink()

        subprocess.run(["update-desktop-database", str(DESKTOP_DIR)],
                       capture_output=True)

        return True, f"{name} uninstalled."
    except Exception as e:
        return False, f"Failed to uninstall {app_id}: {e}"


def _write_desktop(app_id: str, name: str, exec_path: str,
                   icon_path: str, info: dict) -> str:
    """Write .desktop launcher for an AppImage."""
    cats = ";".join(info.get("categories", ["Utility"])) + ";"
    desc = info.get("summary", "")
    icon = icon_path or "application-x-executable"

    content = f"""[Desktop Entry]
Name={name}
Comment={desc}
Exec="{exec_path}" %U
Icon={icon}
Terminal=false
Type=Application
Categories={cats}
StartupNotify=true
X-RakuOS-AppImage=true
X-RakuOS-AppImage-ID={app_id}
"""
    desktop_path = DESKTOP_DIR / f"{DESKTOP_PREFIX}{app_id}.desktop"
    desktop_path.write_text(content)
    desktop_path.chmod(0o755)
    return str(desktop_path)


# ── Update checking (userspace, no sudo) ──────────────────────────────────────

def check_updates() -> list[dict]:
    """
    Check all installed AppImages for updates.
    Returns list of dicts with id, name, current_version, new_version, download_url.
    Runs entirely in userspace — no sudo needed.
    """
    updates = []
    for app in get_installed():
        try:
            result = _check_single_update(app)
            if result:
                updates.append(result)
                # Update last_checked in sidecar
                sidecar_path = INSTALL_DIR / f"{app['id']}.json"
                app["last_checked"] = datetime.now(timezone.utc).isoformat()
                sidecar_path.write_text(json.dumps(app, indent=2))
        except Exception as e:
            print(f"[appimages] Update check failed for {app.get('id')}: {e}")
    return updates


def _check_single_update(app: dict) -> dict | None:
    """Check a single AppImage for an update. Returns update dict or None."""
    source  = app.get("update_source", "none")
    url     = app.get("update_url", "")
    pattern = app.get("update_pattern", "*.AppImage")
    current = app.get("version", "")

    if source == "none" or not url:
        return None

    if source == "github":
        return _check_github(app, url, pattern, current)
    elif source == "gitlab":
        return _check_gitlab(app, url, pattern, current)
    elif source == "url":
        return _check_url(app, url, pattern, current)

    return None


def _check_github(app: dict, api_url: str, pattern: str,
                  current: str) -> dict | None:
    """Check GitHub releases API for a newer version."""
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "RakuOS-Software-Center/1.0",
                     "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        tag     = data.get("tag_name", "").lstrip("v")
        assets  = data.get("assets", [])

        # Match asset by wildcard pattern
        pat_re = re.compile(
            "^" + re.escape(pattern).replace(r"\*", ".*") + "$",
            re.IGNORECASE
        )
        matched = [a for a in assets if pat_re.match(a["name"])]
        if not matched:
            return None

        download_url = matched[0]["browser_download_url"]

        if _version_newer(tag, current):
            return {
                "id":            app["id"],
                "name":          app["name"],
                "current":       current,
                "available":     tag,
                "download_url":  download_url,
                "source":        "appimage",
            }
    except Exception as e:
        print(f"[appimages] GitHub check error for {app.get('id')}: {e}")
    return None


def _check_gitlab(app: dict, api_url: str, pattern: str,
                  current: str) -> dict | None:
    """Check GitLab releases API for a newer version."""
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "RakuOS-Software-Center/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            releases = json.loads(resp.read())

        if not releases:
            return None

        latest  = releases[0]
        tag     = latest.get("tag_name", "").lstrip("v")
        assets  = latest.get("assets", {}).get("links", [])

        pat_re = re.compile(
            "^" + re.escape(pattern).replace(r"\*", ".*") + "$",
            re.IGNORECASE
        )
        matched = [a for a in assets if pat_re.match(Path(a["url"]).name)]
        if not matched:
            return None

        download_url = matched[0]["url"]

        if _version_newer(tag, current):
            return {
                "id":           app["id"],
                "name":         app["name"],
                "current":      current,
                "available":    tag,
                "download_url": download_url,
                "source":       "appimage",
            }
    except Exception as e:
        print(f"[appimages] GitLab check error for {app.get('id')}: {e}")
    return None


def _check_url(app: dict, url: str, pattern: str,
               current: str) -> dict | None:
    """
    Check a generic URL for updates using wildcard pattern matching.
    Tries to HEAD the URL and compare ETag/Last-Modified.
    """
    try:
        req = urllib.request.Request(
            url, method="HEAD",
            headers={"User-Agent": "RakuOS-Software-Center/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            etag    = resp.headers.get("ETag", "")
            last_mod = resp.headers.get("Last-Modified", "")

        # Compare against stored etag/last-modified in sidecar
        stored_etag = app.get("_url_etag", "")
        stored_mod  = app.get("_url_last_modified", "")

        if etag and etag != stored_etag:
            # Update sidecar with new etag
            sidecar_path = INSTALL_DIR / f"{app['id']}.json"
            app["_url_etag"] = etag
            sidecar_path.write_text(json.dumps(app, indent=2))
            return {
                "id":           app["id"],
                "name":         app["name"],
                "current":      current,
                "available":    "new version",
                "download_url": url,
                "source":       "appimage",
            }
        elif last_mod and last_mod != stored_mod:
            sidecar_path = INSTALL_DIR / f"{app['id']}.json"
            app["_url_last_modified"] = last_mod
            sidecar_path.write_text(json.dumps(app, indent=2))
            return {
                "id":           app["id"],
                "name":         app["name"],
                "current":      current,
                "available":    "new version",
                "download_url": url,
                "source":       "appimage",
            }
    except Exception as e:
        print(f"[appimages] URL check error for {app.get('id')}: {e}")
    return None


def _version_newer(new: str, current: str) -> bool:
    """Compare version strings. Returns True if new > current."""
    if not current:
        return True
    if new == current:
        return False
    try:
        # Try numeric tuple comparison
        def _parse(v):
            return tuple(int(x) for x in re.findall(r"\d+", v))
        return _parse(new) > _parse(current)
    except Exception:
        return new != current


# ── Update install stream ─────────────────────────────────────────────────────

def update_appimage_stream(app_id: str, download_url: str):
    """
    Generator that downloads and installs an AppImage update.
    Yields status lines. Used by StreamWorker in the UI.
    """
    try:
        sidecar_path = INSTALL_DIR / f"{app_id}.json"
        if not sidecar_path.exists():
            yield f"Error: {app_id} not installed."
            yield "__done__1"
            return

        sidecar = json.loads(sidecar_path.read_text())
        old_path = Path(sidecar.get("installed_path", ""))
        name     = sidecar.get("name", app_id)

        yield f"Downloading update for {name}..."

        # Download to temp file
        tmp_path = INSTALL_DIR / f"{app_id}.AppImage.tmp"
        def _progress(block_num, block_size, total_size):
            if total_size > 0:
                pct = min(100, block_num * block_size * 100 // total_size)
                print(f"\rDownloading... {pct}%", end="", flush=True)

        urllib.request.urlretrieve(download_url, tmp_path, _progress)
        yield f"Download complete."

        # Replace old AppImage
        if old_path.exists():
            old_path.unlink()
        new_path = INSTALL_DIR / f"{app_id}.AppImage"
        tmp_path.rename(new_path)
        new_path.chmod(new_path.stat().st_mode | stat.S_IEXEC)

        # Re-extract metadata for new version
        yield "Extracting updated metadata..."
        info = extract_appimage_info(str(new_path))
        new_version = info.get("version", sidecar.get("version", ""))

        # Update sidecar
        sidecar["version"]        = new_version
        sidecar["installed_path"] = str(new_path)
        sidecar["last_checked"]   = datetime.now(timezone.utc).isoformat()
        sidecar_path.write_text(json.dumps(sidecar, indent=2))

        # Update icon if changed
        if info.get("icon_data"):
            ext = info.get("icon_ext", "png")
            icon_path = ICON_DIR / f"{app_id}.{ext}"
            icon_path.write_bytes(info["icon_data"])

        yield f"✓ {name} updated to {new_version}."
        yield "__done__0"

    except Exception as e:
        yield f"Error updating {app_id}: {e}"
        yield "__done__1"


# ── File association helper ───────────────────────────────────────────────────

def get_appimage_info_for_display(path: str) -> dict:
    """
    Called when user double-clicks an AppImage.
    Returns enriched info dict for the detail page.
    """
    info = extract_appimage_info(path)
    src  = Path(path)
    return {
        "id":           re.sub(r"[^a-z0-9\-]", "-",
                               info.get("name", src.stem).lower()).strip("-"),
        "name":         info.get("name") or src.stem,
        "version":      info.get("version", ""),
        "summary":      info.get("summary", ""),
        "description":  info.get("description", ""),
        "icon_data":    info.get("icon_data"),
        "icon_ext":     info.get("icon_ext", "png"),
        "categories":   info.get("categories", []),
        "update_source": info.get("update_source", "none"),
        "update_url":   info.get("update_url", ""),
        "update_pattern": info.get("update_pattern", ""),
        "source":       "appimage",
        "installed":    False,
        "src_path":     str(src),
    }
