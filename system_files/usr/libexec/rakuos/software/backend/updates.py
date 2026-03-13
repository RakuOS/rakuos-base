"""
updates.py — System update management via bootc
"""

import json
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path


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


def _get_ghcr_token(repo_path: str) -> str:
    """Get anonymous GHCR pull token for a repo path."""
    url = f"https://ghcr.io/token?scope=repository:{repo_path}:pull&service=ghcr.io"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    return data["token"]


def _get_latest_version_annotation(repo_path: str, token: str) -> str:
    """Get org.opencontainers.image.version annotation from latest tag."""
    url = f"https://ghcr.io/v2/{repo_path}/manifests/latest"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.oci.image.manifest.v1+json",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        manifest = json.loads(resp.read())

    # Try manifest-level annotations first
    version = manifest.get("annotations", {}).get("org.opencontainers.image.version", "")

    # Fallback: check config blob labels
    if not version:
        config_digest = manifest.get("config", {}).get("digest", "")
        if config_digest:
            blob_url = f"https://ghcr.io/v2/{repo_path}/blobs/{config_digest}"
            blob_req = urllib.request.Request(blob_url, headers={
                "Authorization": f"Bearer {token}",
            })
            with urllib.request.urlopen(blob_req, timeout=10) as resp:
                blob = json.loads(resp.read())
            version = blob.get("config", {}).get("Labels", {}).get(
                "org.opencontainers.image.version", "")

    return version


def check_for_update() -> dict:
    """Check GHCR for a newer image using version annotation logic."""
    try:
        data = _get_bootc_status()
        booted = data.get("status", {}).get("booted", {})
        booted_image = booted.get("image", {})
        image_ref = booted_image.get("image", {})

        image_full = image_ref.get("image", "")  # e.g. ghcr.io/rakuos/rakuos-kde:latest
        booted_version = booted_image.get("version", "")  # e.g. latest.20260308
        booted_digest = booted_image.get("imageDigest", "")

        if not image_full:
            return {"update_available": False, "error": "Could not detect booted image"}

        # Parse repo URL and current date tag
        repo_url = image_full.rsplit(":", 1)[0]  # strip :latest
        repo_path = repo_url.replace("ghcr.io/", "", 1)

        current_tag = re.sub(r"^latest\.", "", booted_version).strip()

        # Get GHCR token and fetch latest version annotation
        token = _get_ghcr_token(repo_path)
        version_annotation = _get_latest_version_annotation(repo_path, token)

        newest_tag = re.sub(r"^latest\.", "", version_annotation).strip()
        newest_tag_match = re.match(r"^(\d{8})$", newest_tag)
        newest_tag = newest_tag_match.group(1) if newest_tag_match else ""

        if not newest_tag:
            return {
                "update_available": False,
                "error": f"Could not parse version annotation: {version_annotation}",
                "current_version": booted_version,
            }

        # Compare date tags
        update_available = False
        if re.match(r"^\d{8}$", current_tag):
            update_available = int(newest_tag) > int(current_tag)
        else:
            # Non-date tag — treat as needing update
            update_available = True

        return {
            "update_available": update_available,
            "current_version": booted_version,
            "current_digest": booted_digest,
            "new_version": f"latest.{newest_tag}",
            "new_tag": newest_tag,
            "repo_url": repo_url,
        }

    except Exception as e:
        return {"update_available": False, "error": str(e)}


def apply_update_stream():
    """Generator that yields output from bootc upgrade."""
    yield from upgrade_image_stream()


def upgrade_packages_stream():
    """Generator that yields output from rakuos-update upgrade."""
    try:
        proc = subprocess.Popen(
            ["sudo", "/usr/libexec/rakuos/rakuos-update", "upgrade"],
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


def upgrade_image_stream(update_type: str = "switch", repo_url: str = "", new_tag: str = ""):
    """Generator that yields output from bootc upgrade or switch.
    update_type: 'switch' = new tag available, 'upgrade' = hotfix on same tag.
    """
    try:
        if update_type == "upgrade":
            cmd = ["sudo", "bootc", "upgrade"]
        else:
            # switch to new tag
            target = f"{repo_url}:{new_tag}" if repo_url and new_tag else None
            cmd = ["sudo", "bootc", "switch", target] if target else ["sudo", "bootc", "upgrade"]

        proc = subprocess.Popen(
            cmd,
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
            ["sudo", "bootc", "rollback"],
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
        subprocess.run(["systemctl", "reboot"], check=True)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_overlay_status() -> dict:
    """Get overlay package count and state."""
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
