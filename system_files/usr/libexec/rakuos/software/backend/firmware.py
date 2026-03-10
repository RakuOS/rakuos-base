"""
firmware.py — Firmware update management via fwupd/fwupdmgr.
Covers LVFS remotes, vendor directories, and metadata refresh.
"""

import subprocess
import json
import os
from typing import Optional


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out."
    except Exception as e:
        return -1, "", str(e)


def fwupd_available() -> bool:
    code, _, _ = _run(["fwupdmgr", "--version"])
    return code == 0


def get_remotes() -> list[dict]:
    """
    Return all fwupd remotes.
    Each dict: id, title, url, enabled, kind, metadata_uri,
               last_updated, agreement_required, priority
    """
    code, out, err = _run(["fwupdmgr", "get-remotes", "--json"])
    if code != 0 or not out.strip():
        # Fallback: try without --json (older fwupd)
        return _parse_remotes_text()

    try:
        data = json.loads(out)
        remotes = []
        for r in data.get("Remotes", []):
            remotes.append({
                "id":                 r.get("Id", ""),
                "title":              r.get("Title", r.get("Id", "")),
                "url":                r.get("Uri", r.get("Url", "")),
                "enabled":            r.get("Enabled", False),
                "kind":               r.get("Kind", "unknown"),
                "metadata_uri":       r.get("MetadataUri", ""),
                "last_updated":       r.get("Timestamp", ""),
                "agreement_required": r.get("AgreementRequired", False),
                "priority":           r.get("Priority", 0),
                "filename":           r.get("FilenameCache", ""),
            })
        return remotes
    except (json.JSONDecodeError, KeyError):
        return _parse_remotes_text()


def _parse_remotes_text() -> list[dict]:
    """Fallback text parser for fwupdmgr get-remotes."""
    code, out, _ = _run(["fwupdmgr", "get-remotes"])
    if code != 0:
        return []
    remotes = []
    current: dict = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            if current.get("id"):
                remotes.append(current)
            current = {}
            continue
        if line.startswith("Remote ID"):
            current["id"] = line.split(":", 1)[-1].strip()
            current["title"] = current["id"]
        elif line.startswith("Enabled"):
            current["enabled"] = "true" in line.lower()
        elif line.startswith("URL"):
            current["url"] = line.split(":", 1)[-1].strip()
        elif line.startswith("Type") or line.startswith("Kind"):
            current["kind"] = line.split(":", 1)[-1].strip().lower()
        elif line.startswith("Last"):
            current["last_updated"] = line.split(":", 1)[-1].strip()
    if current.get("id"):
        remotes.append(current)
    # Fill missing keys
    for r in remotes:
        r.setdefault("url", "")
        r.setdefault("enabled", False)
        r.setdefault("kind", "unknown")
        r.setdefault("metadata_uri", "")
        r.setdefault("last_updated", "")
        r.setdefault("agreement_required", False)
        r.setdefault("priority", 0)
        r.setdefault("filename", "")
        r.setdefault("title", r["id"])
    return remotes


def set_remote_enabled(remote_id: str, enabled: bool) -> tuple[bool, str]:
    action = "enable-remote" if enabled else "disable-remote"
    code, _, err = _run(["fwupdmgr", action, remote_id])
    if code == 0:
        return True, f"Remote '{remote_id}' {'enabled' if enabled else 'disabled'}."
    return False, err.strip() or f"Failed to {action} '{remote_id}'."


def refresh_metadata_stream():
    """Generator yielding output lines from fwupdmgr refresh."""
    try:
        proc = subprocess.Popen(
            ["fwupdmgr", "refresh", "--force"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait()
        yield f"__done__{proc.returncode}"
    except FileNotFoundError:
        yield "Error: fwupdmgr not found."
        yield "__done__1"
    except Exception as e:
        yield f"Error: {e}"
        yield "__done__1"


def get_vendor_dirs() -> list[dict]:
    """
    Return vendor-supplied remote directories fwupd scans.
    Typically under /usr/share/fwupd/remotes.d/ and /etc/fwupd/remotes.d/
    """
    dirs = [
        "/usr/share/fwupd/remotes.d",
        "/etc/fwupd/remotes.d",
        "/usr/lib/fwupd/remotes.d",
    ]
    found = []
    for d in dirs:
        if os.path.isdir(d):
            for fname in sorted(os.listdir(d)):
                if fname.endswith(".conf"):
                    fpath = os.path.join(d, fname)
                    info = _parse_remote_conf(fpath)
                    if info:
                        info["source_dir"] = d
                        info["filename"] = fname
                        found.append(info)
    return found


def _parse_remote_conf(path: str) -> Optional[dict]:
    """Parse a fwupd .conf remote file."""
    try:
        info: dict = {"path": path, "enabled": False, "title": "", "url": ""}
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("Enabled"):
                    info["enabled"] = line.split("=", 1)[-1].strip().lower() == "true"
                elif line.startswith("Title"):
                    info["title"] = line.split("=", 1)[-1].strip()
                elif line.startswith("MetadataURI") or line.startswith("Uri"):
                    info["url"] = line.split("=", 1)[-1].strip()
                elif line.startswith("Id"):
                    info["id"] = line.split("=", 1)[-1].strip()
        info.setdefault("id", os.path.basename(path).replace(".conf", ""))
        if not info["title"]:
            info["title"] = info["id"]
        return info
    except Exception:
        return None
