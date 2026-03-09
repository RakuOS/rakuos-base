"""
api.py — Flask API routes for RakuOS Software
"""

import json
from flask import Flask, jsonify, request, Response, stream_with_context
from . import packages, flatpak, updates

app = Flask(__name__)


# ── Search ─────────────────────────────────────────────────────────────────

@app.route("/api/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    source = request.args.get("source", "all")  # all, native, flatpak

    results = []
    if source in ("all", "native"):
        results += packages.search_packages(query)
    if source in ("all", "flatpak"):
        results += flatpak.search_flatpaks(query)

    return jsonify(results)


# ── App Detail ─────────────────────────────────────────────────────────────

@app.route("/api/app/<path:app_id>")
def app_detail(app_id):
    """Return full app details including both native and flatpak options."""
    appstream = packages._load_appstream()

    # Find by id or pkg_name
    native_app = appstream.get(app_id)
    if not native_app:
        for a in appstream.values():
            if a["pkg_name"] == app_id and a["source"] == "native":
                native_app = a
                break

    flatpak_app = appstream.get(app_id)
    if not flatpak_app or flatpak_app.get("source") != "flatpak":
        flatpak_app = None
        for a in appstream.values():
            if a["source"] == "flatpak" and (
                a["id"] == app_id or
                a["pkg_name"] == app_id or
                a["name"].lower() == (native_app or {}).get("name", "").lower()
            ):
                flatpak_app = a
                break

    if not native_app and not flatpak_app:
        return jsonify({"error": "App not found"}), 404

    base = native_app or flatpak_app

    # Enrich URLs from AppStream
    import xml.etree.ElementTree as ET
    import gzip, os
    extra_urls = {"homepage": "", "donation": "", "bugtracker": "", "help": ""}
    # Already parsed into base app — re-parse for extra url types
    for appstream_dir, source in packages.APPSTREAM_DIRS:
        if not os.path.isdir(appstream_dir):
            continue
        for fname in os.listdir(appstream_dir):
            fpath = os.path.join(appstream_dir, fname)
            try:
                if fname.endswith(".gz"):
                    fh = gzip.open(fpath, "rt", encoding="utf-8", errors="ignore")
                else:
                    fh = open(fpath, "rt", encoding="utf-8", errors="ignore")
                tree = ET.parse(fh)
                fh.close()
                root = tree.getroot()
                comps = [root] if root.tag == "component" else root.findall("component")
                for comp in comps:
                    cid = (comp.findtext("id") or "").strip()
                    if cid == base["id"]:
                        for url_el in comp.findall("url"):
                            utype = url_el.get("type", "")
                            if utype in extra_urls and url_el.text:
                                extra_urls[utype] = url_el.text.strip()
                        break
                else:
                    continue
                break
            except Exception:
                continue
        else:
            continue
        break

    return jsonify({
        "base": base,
        "native": packages._enrich_installed(native_app) if native_app else None,
        "flatpak": packages._enrich_installed(flatpak_app) if flatpak_app else None,
        "urls": extra_urls,
    })


# ── Categories ─────────────────────────────────────────────────────────────

@app.route("/api/category/<category>")
def by_category(category):
    source = request.args.get("source", "all")
    limit = int(request.args.get("limit", 40))
    offset = int(request.args.get("offset", 0))
    results = packages.get_by_category(category, limit=limit, offset=offset, source=source)
    return jsonify(results)

# ── Icons ─────────────────────────────────────────────────────────────
@app.route("/icons/<path:filename>")
def serve_icon(filename):
    from backend.packages import find_icon
    fpath = find_icon(filename)
    if fpath:
        return send_from_directory(os.path.dirname(fpath), os.path.basename(fpath))
    return "", 404

# ── Installed ──────────────────────────────────────────────────────────────

@app.route("/api/installed")
def installed():
    native = packages.get_installed_with_metadata()
    fps = flatpak.get_installed_flatpaks()
    return jsonify({"native": native, "flatpak": fps})


# ── Install / Remove (streaming) ───────────────────────────────────────────

@app.route("/api/install/native/<pkg_name>")
def install_native(pkg_name):
    def generate():
        for line in packages.install_package_stream(pkg_name):
            yield f"data: {json.dumps({'line': line})}\n\n"
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")


@app.route("/api/remove/native/<pkg_name>")
def remove_native(pkg_name):
    def generate():
        for line in packages.remove_package_stream(pkg_name):
            yield f"data: {json.dumps({'line': line})}\n\n"
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")


@app.route("/api/install/flatpak/<path:app_id>")
def install_flatpak(app_id):
    def generate():
        for line in flatpak.install_flatpak_stream(app_id):
            yield f"data: {json.dumps({'line': line})}\n\n"
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")


@app.route("/api/remove/flatpak/<path:app_id>")
def remove_flatpak(app_id):
    def generate():
        for line in flatpak.remove_flatpak_stream(app_id):
            yield f"data: {json.dumps({'line': line})}\n\n"
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")


# ── Updates ────────────────────────────────────────────────────────────────

@app.route("/api/updates/status")
def update_status():
    system = updates.check_for_update()
    flatpak_updates = flatpak.get_flatpak_updates()
    overlay = updates.get_overlay_status()
    return jsonify({
        "system": system,
        "flatpak_updates": flatpak_updates,
        "overlay": overlay,
    })


@app.route("/api/updates/system")
def apply_system_update():
    status = updates.check_for_update()
    new_tag = status.get("new_tag", "")
    repo_url = status.get("repo_url", "")
    def generate():
        for line in updates.apply_update_stream(new_tag=new_tag, repo_url=repo_url):
            yield f"data: {json.dumps({'line': line})}\n\n"
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")


@app.route("/api/updates/flatpak")
def apply_flatpak_updates():
    def generate():
        for line in flatpak.update_all_flatpaks_stream():
            yield f"data: {json.dumps({'line': line})}\n\n"
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")


@app.route("/api/updates/rollback")
def rollback():
    def generate():
        for line in updates.rollback_stream():
            yield f"data: {json.dumps({'line': line})}\n\n"
    return Response(stream_with_context(generate()),
                    content_type="text/event-stream")


@app.route("/api/updates/reboot", methods=["POST"])
def reboot():
    result = updates.schedule_reboot()
    return jsonify(result)


# ── System info ────────────────────────────────────────────────────────────

@app.route("/api/system")
def system_info():
    return jsonify({
        "status": updates.get_system_status(),
        "overlay": updates.get_overlay_status(),
    })


# ── UI serving ─────────────────────────────────────────────────────────────

import os
from flask import send_from_directory

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")

@app.route("/")
def index():
    return send_from_directory(UI_DIR, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(UI_DIR, filename)
