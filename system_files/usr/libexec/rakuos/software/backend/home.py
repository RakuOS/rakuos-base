"""
backend/home.py — Home page data fetching.
Provides popular apps (stats-sorted), editor's picks, recently updated, and new apps.
All results cached to disk with TTL so the home page loads instantly.
"""

import json
import logging
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "rakuos")
os.makedirs(_CACHE_DIR, exist_ok=True)

_POPULAR_CACHE   = os.path.join(_CACHE_DIR, "popular.json")
_PICKS_CACHE     = os.path.join(_CACHE_DIR, "picks.json")
_UPDATED_CACHE   = os.path.join(_CACHE_DIR, "recently_updated.json")
_NEW_CACHE       = os.path.join(_CACHE_DIR, "new_apps.json")

_CACHE_TTL       = 6 * 3600   # 6 hours — refreshed by tray daemon
_PICKS_URL       = "https://rakuos.org/api/picks.json"
_UPDATED_FEED    = "https://flathub.org/api/v2/feed/recently-updated"
_NEW_FEED        = "https://flathub.org/api/v2/feed/new"
_STATS_URL       = "https://flathub.org/api/v2/stats/{app_id}"

# Seed list — sorted by live stats on first fetch, then cached
_POPULAR_SEED = [
    "com.valvesoftware.Steam",
    "org.mozilla.firefox",
    "com.spotify.Client",
    "com.discordapp.Discord",
    "org.videolan.vlc",
    "com.obsproject.Studio",
    "org.gimp.GIMP",
    "org.inkscape.Inkscape",
    "org.libreoffice.LibreOffice",
    "org.kde.kdenlive",
    "org.blender.Blender",
    "com.google.Chrome",
    "org.signal.Signal",
    "net.lutris.Lutris",
    "com.heroicgameslauncher.hgl",
    "org.freedesktop.Piper",
    "org.gnome.Boxes",
    "io.github.celluloid_player.Celluloid",
    "com.github.tchx84.Flatseal",
    "org.kde.okular",
]

# Fallback picks if rakuos.org isn't set up yet
_FALLBACK_PICKS = [
    "com.valvesoftware.Steam",
    "com.obsproject.Studio",
    "org.kde.kdenlive",
    "org.gimp.GIMP",
    "net.lutris.Lutris",
    "com.heroicgameslauncher.hgl",
    "org.mozilla.firefox",
    "com.discordapp.Discord",
    "org.blender.Blender",
    "com.github.tchx84.Flatseal",
    "org.inkscape.Inkscape",
    "org.libreoffice.LibreOffice",
]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_valid(path: str, ttl: int = _CACHE_TTL) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) < ttl
    except OSError:
        return False


def _read_cache(path: str) -> Optional[list]:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(path: str, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.debug("home cache write error %s: %s", path, e)


def _fetch_url(url: str, timeout: int = 8) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RakuOS-Software/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        logging.debug("home fetch error %s: %s", url, e)
        return None


# ── RSS feed parser ───────────────────────────────────────────────────────────

def _parse_feed(data: bytes, limit: int = 20) -> list[str]:
    """Extract Flathub app IDs from an RSS feed."""
    app_ids = []
    try:
        root = ET.fromstring(data)
        for item in root.findall(".//item"):
            link = item.findtext("link") or ""
            # URL format: https://flathub.org/apps/org.kde.okular
            if "/apps/" in link:
                app_id = link.rstrip("/").split("/apps/")[-1]
                if app_id and "." in app_id:
                    app_ids.append(app_id)
            if len(app_ids) >= limit:
                break
    except Exception as e:
        logging.debug("feed parse error: %s", e)
    return app_ids


# ── Stats fetcher ─────────────────────────────────────────────────────────────

def _fetch_app_stats(app_id: str) -> int:
    """Return total install count for an app from Flathub stats API."""
    data = _fetch_url(_STATS_URL.format(app_id=app_id), timeout=5)
    if not data:
        return 0
    try:
        j = json.loads(data)
        return j.get("installs_total", j.get("downloads_total", 0))
    except Exception:
        return 0


# ── Public API ────────────────────────────────────────────────────────────────

def get_popular(force: bool = False) -> list[str]:
    """
    Return list of popular app IDs sorted by total installs.
    Uses disk cache — call force=True to refresh (done by tray daemon).
    """
    if not force and _cache_valid(_POPULAR_CACHE):
        cached = _read_cache(_POPULAR_CACHE)
        if cached:
            return cached

    logging.debug("home: fetching popular app stats")
    scored = []
    for app_id in _POPULAR_SEED:
        count = _fetch_app_stats(app_id)
        scored.append((count, app_id))
        logging.debug("  %s: %d installs", app_id, count)

    # Sort by installs descending, fall back to seed order on ties
    scored.sort(key=lambda x: -x[0])
    result = [app_id for _, app_id in scored]

    _write_cache(_POPULAR_CACHE, result)
    return result


def get_picks(force: bool = False) -> list[str]:
    """
    Return editor's picks app IDs.
    Tries rakuos.org first, falls back to hardcoded list.
    """
    if not force and _cache_valid(_PICKS_CACHE):
        cached = _read_cache(_PICKS_CACHE)
        if cached:
            return cached

    logging.debug("home: fetching editor's picks from rakuos.org")
    data = _fetch_url(_PICKS_URL, timeout=5)
    if data:
        try:
            j = json.loads(data)
            # Support both {"picks": [...]} and flat list formats
            picks = j.get("picks", j) if isinstance(j, dict) else j
            # Each entry can be {"id": "..."} or just a string
            result = [
                (p["id"] if isinstance(p, dict) else p)
                for p in picks
            ]
            if result:
                _write_cache(_PICKS_CACHE, result)
                return result
        except Exception as e:
            logging.debug("picks parse error: %s", e)

    logging.debug("home: picks fallback to hardcoded list")
    _write_cache(_PICKS_CACHE, _FALLBACK_PICKS)
    return _FALLBACK_PICKS


def get_recently_updated(force: bool = False, limit: int = 20) -> list[str]:
    """Return recently updated app IDs from Flathub RSS feed."""
    if not force and _cache_valid(_UPDATED_CACHE):
        cached = _read_cache(_UPDATED_CACHE)
        if cached:
            return cached

    logging.debug("home: fetching recently updated feed")
    data = _fetch_url(_UPDATED_FEED)
    if data:
        result = _parse_feed(data, limit)
        if result:
            _write_cache(_UPDATED_CACHE, result)
            return result

    return _read_cache(_UPDATED_CACHE) or []


def get_new_apps(force: bool = False, limit: int = 20) -> list[str]:
    """Return newly added app IDs from Flathub RSS feed."""
    if not force and _cache_valid(_NEW_CACHE):
        cached = _read_cache(_NEW_CACHE)
        if cached:
            return cached

    logging.debug("home: fetching new apps feed")
    data = _fetch_url(_NEW_FEED)
    if data:
        result = _parse_feed(data, limit)
        if result:
            _write_cache(_NEW_CACHE, result)
            return result

    return _read_cache(_NEW_CACHE) or []


def refresh_all():
    """Refresh all caches — called by tray daemon on schedule."""
    logging.debug("home: refreshing all caches")
    get_picks(force=True)
    get_recently_updated(force=True)
    get_new_apps(force=True)
    get_popular(force=True)  # last — slowest (fetches stats per app)
    logging.debug("home: cache refresh complete")
