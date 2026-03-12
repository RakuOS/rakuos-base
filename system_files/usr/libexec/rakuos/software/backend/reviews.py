"""
backend/reviews.py — ODRS (Open Desktop Ratings Service) client.
Used by GNOME Software, KDE Discover, elementary AppCenter, etc.
API: https://odrs.gnome.org/1.0/reviews/api/
"""

import json
import hashlib
import os
import urllib.request
import urllib.error
from typing import Optional

ODRS_BASE = "https://odrs.gnome.org/1.0/reviews/api"
_reviews_cache: dict[str, list] = {}
USER_AGENT = "RakuOS-Software/1.0"
TIMEOUT = 10


def _user_hash() -> str:
    """
    Generate a one-way hash of machine-id + username.
    ODRS uses this to prevent duplicate reviews — it never sees your username.
    Same approach as gnome-software.
    """
    machine_id = ""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            machine_id = open(path).read().strip()
            break
        except OSError:
            pass
    username = os.environ.get("USER", os.environ.get("LOGNAME", "user"))
    raw = f"{machine_id}{username}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _post(endpoint: str, payload: dict) -> Optional[list | dict]:
    url = f"{ODRS_BASE}/{endpoint}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _get(endpoint: str) -> Optional[list | dict]:
    url = f"{ODRS_BASE}/{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def get_reviews(app_id: str, locale: str = "en_GB") -> list[dict]:
    """
    Fetch reviews for an app_id using GET /app/{id}.
    Tries multiple ID variants to maximise hit rate:
      1. As-is (e.g. org.mozilla.Firefox or firefox.desktop)
      2. .desktop suffix (for RPM apps)
      3. Title-cased last component (org.mozilla.firefox → org.mozilla.Firefox)
    Returns list of review dicts with keys:
        summary, description, rating (0-100), user_display, date_created,
        version, distro, karma_up, karma_down, review_id
    """
    import urllib.parse

    if app_id in _reviews_cache:
        return _reviews_cache[app_id]

    def _try(aid: str) -> list[dict]:
        result = _get(f"app/{urllib.parse.quote(aid, safe='')}")
        if result and isinstance(result, list) and len(result) > 0:
            return result
        return []

    # Build list of IDs to try in order
    ids_to_try = [app_id]

    # .desktop variant for RPM apps
    if not app_id.endswith(".desktop"):
        ids_to_try.append(f"{app_id}.desktop")

    # Title-case the last component: org.mozilla.firefox → org.mozilla.Firefox
    parts = app_id.split(".")
    if len(parts) >= 2:
        titled = ".".join(parts[:-1]) + "." + parts[-1].capitalize()
        if titled not in ids_to_try:
            ids_to_try.append(titled)

    for aid in ids_to_try:
        result = _try(aid)
        if result:
            _reviews_cache[app_id] = result
            return result

    _reviews_cache[app_id] = []
    return []


def get_ratings(app_id: str) -> Optional[dict]:
    """
    Derive aggregate star ratings from the reviews list.
    The /app/ endpoint returns reviews, not a ratings summary,
    so we compute counts ourselves from the review data.
    Returns dict with keys: star1..star5
    """
    reviews = get_reviews(app_id)
    if not reviews:
        return None
    counts = {f"star{i}": 0 for i in range(1, 6)}
    for r in reviews:
        rating = r.get("rating", 0)
        star = max(1, min(5, round(rating / 20)))
        counts[f"star{star}"] += 1
    return counts


def submit_review(
    app_id: str,
    summary: str,
    description: str,
    rating: int,          # 0-100
    version: str = "",
    locale: str = "en_GB",
) -> tuple[bool, str]:
    """
    Submit a review to ODRS.
    Returns (success, message).
    """
    if not summary.strip() or not description.strip():
        return False, "Summary and review text are required."
    if not (0 <= rating <= 100):
        return False, "Rating must be 0–100."

    result = _post("submit", {
        "user_hash": _user_hash(),
        "app_id": app_id,
        "locale": locale,
        "summary": summary.strip(),
        "description": description.strip(),
        "rating": rating,
        "version": version,
        "distro": "RakuOS Linux",
        "user_display": None,  # anonymous
    })

    if result is None:
        return False, "Could not reach the review server. Check your connection."
    if isinstance(result, dict) and result.get("msg"):
        msg = result["msg"]
        if "already reviewed" in msg.lower():
            return False, "You have already reviewed this app."
        return False, msg

    return True, "Review submitted — thank you!"


def vote_review(review_id: int, upvote: bool) -> bool:
    """Upvote or downvote a review by its ID."""
    result = _post("vote", {
        "user_hash": _user_hash(),
        "review_id": review_id,
        "vote_id": 1 if upvote else -1,
    })
    return result is not None


def stars_from_rating(rating: int) -> str:
    """Convert 0-100 rating to a 1-5 star display string."""
    stars = round(rating / 20)
    return "★" * stars + "☆" * (5 - stars)


def avg_rating_from_counts(ratings: dict) -> tuple[float, int]:
    """
    Given a ratings dict with star1..star5 counts,
    return (average_0_to_100, total_count).
    """
    total = sum(ratings.get(f"star{i}", 0) for i in range(1, 6))
    if total == 0:
        return 0.0, 0
    weighted = sum(i * ratings.get(f"star{i}", 0) for i in range(1, 6))
    avg_stars = weighted / total          # 1.0 – 5.0
    return round((avg_stars / 5) * 100), total
