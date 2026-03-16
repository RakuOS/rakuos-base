"""
flatpak.py — Flatpak package management
"""

import os
import subprocess
import json
from typing import Optional


def get_installed_flatpaks() -> list[dict]:
    """Return list of installed Flatpaks enriched with AppStream metadata."""
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application,name,version,description,origin"],
            capture_output=True, text=True
        )

        # Load AppStream cache for metadata enrichment
        from backend.packages import _load_appstream
        appstream = _load_appstream()
        appstream_by_id = {a["id"]: a for a in appstream.values() if a["source"] == "flatpak"}

        apps = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                app_id = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else app_id
                version = parts[2].strip() if len(parts) > 2 else ""
                summary = parts[3].strip() if len(parts) > 3 else ""
                origin = parts[4].strip() if len(parts) > 4 else "flathub"

                # Enrich from AppStream if available
                meta = appstream_by_id.get(app_id, {})
                apps.append({
                    "id": app_id,
                    "name": meta.get("name") or name,
                    "version": version,
                    "summary": meta.get("summary") or summary,
                    "description": meta.get("description", ""),
                    "origin": origin,
                    "source": "flatpak",
                    "installed": True,
                    "icon": meta.get("icon") or f"{app_id}.png",
                    "screenshots": meta.get("screenshots", []),
                    "categories": meta.get("categories", []),
                    "pkg_name": app_id,
                    "url": meta.get("url", ""),
                })
        return apps
    except Exception as e:
        print(f"get_installed_flatpaks error: {e}")
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
        if proc.returncode == 0:
            from . import packages
            packages.invalidate_flatpak_cache()
        yield f"__done__{proc.returncode}"
    except Exception as e:
        yield f"Error: {e}"
        yield "__done__1"


def remove_flatpak_stream(app_id: str, force: bool = False):
    """Generator that yields output lines from flatpak remove.
    Use force=True for runtimes/add-ons that may have dependents."""
    try:
        cmd = ["flatpak", "remove", "-y"]
        if force:
            cmd.append("--force-remove")
        cmd.append(app_id)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait()
        if proc.returncode == 0:
            from . import packages
            packages.invalidate_flatpak_cache()
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


# ── Remote / repo management ──────────────────────────────────────────────────

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"


def get_remotes() -> list[dict]:
    """
    Return all configured Flatpak remotes (system + user).
    Each dict: name, url, title, enabled, system (bool)

    Uses plain `flatpak remotes` without --columns so it works across all
    Flatpak versions. Queries system and user independently; system query
    may need polkit on some setups so we fall back gracefully.
    """
    remotes = []
    seen = set()

    for scope, flags in [
        ("system", ["--system"]),
        ("user",   ["--user"]),
    ]:
        try:
            # Try with --columns first (Flatpak >= 1.2)
            r = subprocess.run(
                ["flatpak", "remotes"] + flags +
                ["--columns=name,title,url,options"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode != 0 or not r.stdout.strip():
                # Fall back to plain output — columns not supported or no access
                r = subprocess.run(
                    ["flatpak", "remotes"] + flags,
                    capture_output=True, text=True, timeout=10
                )
            for line in r.stdout.splitlines():
                if not line.strip() or line.startswith("Name"):
                    continue
                parts = line.split("\t")
                if not parts[0].strip():
                    continue
                name  = parts[0].strip()
                if name in seen:
                    continue
                seen.add(name)
                title   = parts[1].strip() if len(parts) > 1 else name
                url     = parts[2].strip() if len(parts) > 2 else ""
                options = parts[3].strip().lower() if len(parts) > 3 else ""
                # "disabled" appears in options column when remote is off
                enabled = "disabled" not in options
                remotes.append({
                    "name":    name,
                    "title":   title or name,
                    "url":     url,
                    "enabled": enabled,
                    "system":  scope == "system",
                })
        except Exception:
            continue

    # Last resort: no-scope query catches system remotes visible to current user
    if not remotes:
        try:
            r = subprocess.run(
                ["flatpak", "remotes", "--columns=name,title,url,options"],
                capture_output=True, text=True, timeout=10
            )
            for line in r.stdout.splitlines():
                if not line.strip() or line.startswith("Name"):
                    continue
                parts = line.split("\t")
                if not parts[0].strip():
                    continue
                name = parts[0].strip()
                if name in seen:
                    continue
                seen.add(name)
                title   = parts[1].strip() if len(parts) > 1 else name
                url     = parts[2].strip() if len(parts) > 2 else ""
                options = parts[3].strip().lower() if len(parts) > 3 else ""
                remotes.append({
                    "name":    name,
                    "title":   title or name,
                    "url":     url,
                    "enabled": "disabled" not in options,
                    "system":  True,  # assume system if we can see it without --user
                })
        except Exception:
            pass

    return remotes


def has_flathub() -> bool:
    return any(
        "flathub" in r["name"].lower() or "flathub" in r["url"].lower()
        for r in get_remotes()
    )


def add_remote(name: str, url: str, system: bool = True) -> tuple[bool, str]:
    scope = "--system" if system else "--user"
    try:
        r = subprocess.run(
            ["flatpak", "remote-add", scope, "--if-not-exists", name, url],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            return True, f"Remote '{name}' added."
        return False, r.stderr.strip() or "Failed to add remote."
    except Exception as e:
        return False, str(e)


def add_flathub(system: bool = True) -> tuple[bool, str]:
    return add_remote("flathub", FLATHUB_URL, system=system)


def remove_remote(name: str, system: bool = True) -> tuple[bool, str]:
    scope = "--system" if system else "--user"
    try:
        r = subprocess.run(
            ["flatpak", "remote-delete", scope, "--force", name],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            return True, f"Remote '{name}' removed."
        return False, r.stderr.strip() or "Failed to remove remote."
    except Exception as e:
        return False, str(e)


def set_remote_enabled(name: str, enabled: bool, system: bool = True) -> tuple[bool, str]:
    scope = "--system" if system else "--user"
    action = "enable" if enabled else "disable"
    try:
        r = subprocess.run(
            ["flatpak", f"remote-{action}", scope, name],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            return True, f"Remote '{name}' {'enabled' if enabled else 'disabled'}."
        return False, r.stderr.strip() or f"Failed to {action} remote."
    except Exception as e:
        return False, str(e)


# ── Local file install ────────────────────────────────────────────────────────

def get_local_flatpak_info(path: str) -> dict:
    """
    Extract metadata from a local .flatpak bundle using flatpak info.
    Returns an app dict compatible with the detail page.
    """
    import configparser
    try:
        r = subprocess.run(
            ["flatpak", "build-export", "--runtime", "/dev/null", path],
            capture_output=True, text=True, timeout=5
        )
    except Exception:
        pass

    # flatpak show-info on bundle
    try:
        r = subprocess.run(
            ["ostree", "show", "--repo=/dev/null", path],
            capture_output=True, text=True, timeout=5
        )
    except Exception:
        pass

    # Best approach: flatpak install --print-first-match
    # Actually use: flatpak info on the bundle file directly
    try:
        r = subprocess.run(
            ["flatpak", "info", "--bundle", path],
            capture_output=True, text=True, timeout=10
        )
        data = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                data[k.strip().lower()] = v.strip()

        app_id   = data.get("id", os.path.basename(path))
        name     = data.get("name", app_id.split(".")[-1])
        version  = data.get("version", "")
        summary  = data.get("subject", "")
        branch   = data.get("branch", "stable")

        return {
            "id":           app_id,
            "name":         name,
            "summary":      summary,
            "description":  "",
            "categories":   [],
            "icon":         "",
            "screenshots":  [],
            "pkg_name":     app_id,
            "url":          "",
            "source":       "flatpak",
            "installed":    False,
            "is_addon":     False,
            "local_flatpak": path,
            "version":      version,
            "branch":       branch,
        }
    except Exception as e:
        # Minimal fallback
        app_id = os.path.basename(path).replace(".flatpak", "")
        return {
            "id":           app_id,
            "name":         app_id,
            "summary":      f"Local Flatpak bundle",
            "description":  "",
            "categories":   [],
            "icon":         "",
            "screenshots":  [],
            "pkg_name":     app_id,
            "url":          "",
            "source":       "flatpak",
            "installed":    False,
            "is_addon":     False,
            "local_flatpak": path,
        }


def get_flatpakref_info(path: str) -> dict:
    """
    Parse a .flatpakref file and return an app dict for the detail page.
    .flatpakref is an INI file with [Flatpak Ref] section.
    """
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(path)
    section = "Flatpak Ref"
    if not cfg.has_section(section):
        # Try case-insensitive fallback
        for s in cfg.sections():
            if s.lower() == "flatpak ref":
                section = s
                break

    app_id  = cfg.get(section, "Name",  fallback=os.path.basename(path).replace(".flatpakref", ""))
    title   = cfg.get(section, "Title", fallback=app_id.split(".")[-1])
    comment = cfg.get(section, "Comment", fallback="")
    url     = cfg.get(section, "Url",   fallback="")
    branch  = cfg.get(section, "Branch", fallback="stable")

    return {
        "id":            app_id,
        "name":          title,
        "summary":       comment,
        "description":   "",
        "categories":    [],
        "icon":          "",
        "screenshots":   [],
        "pkg_name":      app_id,
        "url":           url,
        "source":        "flatpak",
        "installed":     False,
        "is_addon":      False,
        "local_flatpakref": path,
        "branch":        branch,
    }


def install_local_flatpak_stream(path: str):
    """Generator that installs a local .flatpak bundle file (system-wide via pkexec)."""
    try:
        proc = subprocess.Popen(
            ["pkexec", "flatpak", "install", "--bundle", "--noninteractive", "-y", path],
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


def install_flatpakref_stream(path: str):
    """Generator that installs from a .flatpakref file (system-wide via pkexec)."""
    try:
        proc = subprocess.Popen(
            ["sudo", "flatpak", "install", "--from", "--noninteractive", "-y", path],
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
