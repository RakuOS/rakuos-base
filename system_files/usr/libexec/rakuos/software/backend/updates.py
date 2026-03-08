"""
updates.py — System update management via bootc
"""

import json
import subprocess
from datetime import datetime


def _get_bootc_status() -> dict:
    """Run bootc status --json and return parsed data."""
    result = subprocess.run(
        ["sudo", "bootc", "status", "--json"],
        capture_output=True, text=True, timeout=15
    )
    return json.loads(result.stdout)


def get_system_status() -> dict:
    """Get current bootc image status."""
    try:
        data = _get_bootc_status()
        booted = data.get("status", {}).get("booted", {})
        image = booted.get("image", {})
        image_ref = image.get("image", {})
        return {
            "image": image_ref.get("image", ""),
            "version": image.get("version", ""),
            "digest": image.get("imageDigest", ""),
            "timestamp": image.get("timestamp", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def check_for_update() -> dict:
    """Check if a system update is available."""
    try:
        data = _get_bootc_status()
        status = data.get("status", {})

        booted = status.get("booted", {})
        staged = status.get("staged")

        booted_image = booted.get("image", {})
        booted_digest = booted_image.get("imageDigest", "")
        booted_version = booted_image.get("version", "")

        if staged:
            staged_image = staged.get("image", {})
            staged_digest = staged_image.get("imageDigest", "")
            staged_version = staged_image.get("version", "")
            update_available = staged_digest != booted_digest
        else:
            update_available = False
            staged_version = ""
            staged_digest = ""

        return {
            "update_available": update_available,
            "current_version": booted_version,
            "current_digest": booted_digest,
            "new_version": staged_version,
            "new_digest": staged_digest,
        }
    except Exception as e:
        return {"update_available": False, "error": str(e)}


def apply_update_stream():
    """Generator that yields output from bootc upgrade."""
    try:
        proc = subprocess.Popen(
            ["pkexec", "bootc", "upgrade"],
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


def rollback_stream():
    """Generator that yields output from bootc rollback."""
    try:
        proc = subprocess.Popen(
            ["pkexec", "bootc", "rollback"],
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


def schedule_reboot():
    """Schedule system reboot."""
    try:
        subprocess.run(["pkexec", "systemctl", "reboot"], check=True)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_overlay_status() -> dict:
    """Get overlay package count and state."""
    from pathlib import Path
    packages_list = Path("/var/lib/rakuos/packages.list")
    state_file = Path("/var/lib/rakuos/overlay.state")
    dirty_file = Path("/var/lib/rakuos/overlay.dirty")

    packages = []
    if packages_list.exists():
        packages = [p.strip() for p in packages_list.read_text().splitlines() if p.strip()]

    return {
        "package_count": len(packages),
        "packages": packages,
        "has_digest": state_file.exists(),
        "is_dirty": dirty_file.exists(),
    }
