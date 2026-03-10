"""
packages.py — Native package management via rakuos install/remove and AppStream metadata
"""

import logging
import os
import re
import gzip
import locale
import subprocess
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

def _get_system_lang() -> str:
    """Get system language code e.g. 'en', 'de', 'fr'"""
    try:
        lang = locale.getlocale()[0] or "en"
        return lang.split("_")[0].lower()
    except Exception:
        return "en"

SYSTEM_LANG = _get_system_lang()
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

def _get_localized(comp, tag: str) -> str:
    """Get localized text matching system locale with English fallback."""
    els = comp.findall(tag)
    by_lang = {}
    default = ""
    for el in els:
        lang = el.get(XML_LANG, "")
        if lang == "":
            default = el.text or ""
        else:
            by_lang[lang.split("-")[0].lower()] = el.text or ""
    return (
        by_lang.get(SYSTEM_LANG)
        or by_lang.get("en")
        or default
        or ""
    )

def _get_localized_description(comp) -> str:
    """Get localized description, handling nested p/ul/li tags."""
    by_lang = {}
    default = ""
    for desc_el in comp.findall("description"):
        lang = desc_el.get(XML_LANG, "")
        text = " ".join(desc_el.itertext()).strip()
        if lang == "":
            default = text
        else:
            by_lang[lang.split("-")[0].lower()] = text
    return (
        by_lang.get(SYSTEM_LANG)
        or by_lang.get("en")
        or default
        or ""
    )

# ── Package manager detection ─────────────────────────────────────────────────

def is_rakuos() -> bool:
    """True if running on RakuOS — packages.list and rakuos CLI present."""
    import shutil
    return PACKAGES_LIST.exists() or shutil.which("rakuos") is not None


def _get_pkg_manager() -> list[str]:
    """
    Return the best available package manager command as a list.
    Priority: rakuos CLI → dnf5 → dnf
    This allows the software center to work on any DNF-based distro.
    """
    import shutil
    if shutil.which("rakuos"):
        return ["rakuos"]
    if shutil.which("dnf5"):
        return ["dnf5"]
    if shutil.which("dnf"):
        return ["dnf"]
    return ["dnf"]


def _get_dnf() -> list[str]:
    """
    Return dnf5 or dnf directly — never rakuos.
    Used for read-only queries (repoquery, info) that rakuos doesn't support.
    """
    import shutil
    if shutil.which("dnf5"):
        return ["dnf5"]
    if shutil.which("dnf"):
        return ["dnf"]
    return ["dnf"]


def _get_pkexec_install_cmd(pkg_name: str) -> list[str]:
    """Return the full privileged install command for pkg_name."""
    import shutil
    if shutil.which("rakuos"):
        return ["pkexec", "/usr/libexec/rakuos/rakuos-install", pkg_name]
    mgr = _get_pkg_manager()
    return ["pkexec"] + mgr + ["install", "-y", pkg_name]


def _get_pkexec_remove_cmd(pkg_name: str) -> list[str]:
    """Return the full privileged remove command for pkg_name."""
    import shutil
    if shutil.which("rakuos"):
        return ["pkexec", "/usr/libexec/rakuos/rakuos-remove", pkg_name]
    mgr = _get_pkg_manager()
    return ["pkexec"] + mgr + ["remove", "-y", pkg_name]


PACKAGES_LIST = Path("/var/lib/rakuos/packages.list")

APPSTREAM_DIRS = [
    ("/usr/share/swcatalog/xml", "native"),
    ("/usr/share/app-info/xmls", "native"),
    ("/var/cache/app-info/xmls", "native"),
    ("/var/lib/flatpak/appstream/flathub/x86_64/active", "flatpak"),
]

ICON_DIRS = [
    "/usr/share/swcatalog/icons/fedora/64x64",
    "/usr/share/swcatalog/icons/fedora/128x128",
    "/usr/share/swcatalog/icons/rpmfusion-free-43/64x64",
    "/usr/share/swcatalog/icons/rpmfusion-nonfree-43/64x64",
    "/var/lib/flatpak/appstream/flathub/x86_64/active/icons/64x64",
    "/var/lib/flatpak/appstream/flathub/x86_64/active/icons/128x128",
]

_appstream_cache: dict = {}
_cache_lock = threading.Lock()
_cache_ready = threading.Event()


def get_installed_packages() -> list[str]:
    """
    Return list of user-installed packages.
    On RakuOS: reads /var/lib/rakuos/packages.list (overlay).
    On other distros: queries DNF for explicitly installed packages.
    """
    if PACKAGES_LIST.exists():
        return [
            p.strip() for p in PACKAGES_LIST.read_text().splitlines()
            if p.strip() and not p.strip().startswith("#")
        ]

    # Non-RakuOS fallback — ask DNF for explicitly installed packages
    # (userinstalled excludes base OS packages, giving a manageable list)
    mgr = _get_pkg_manager()
    for args in [
        _get_dnf() + ["repoquery", "--userinstalled", "--queryformat", "%{name}"],
        mgr + ["history", "userinstalled"],          # dnf4 fallback
    ]:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                return [p.strip() for p in r.stdout.splitlines() if p.strip()]
        except Exception:
            continue
    return []


def is_installed_native(pkg_name: str) -> bool:
    if PACKAGES_LIST.exists():
        return pkg_name in get_installed_packages()
    # Non-RakuOS: ask rpm directly — much faster than scanning full DNF list
    try:
        r = subprocess.run(
            ["rpm", "-q", "--quiet", pkg_name],
            capture_output=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return pkg_name in get_installed_packages()


def is_installed_flatpak(app_id: str) -> bool:
    try:
        result = subprocess.run(
            ["flatpak", "info", app_id],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def install_package_stream(pkg_name: str):
    """Generator that yields output lines from install command.
    Uses rakuos CLI if available, falls back to dnf5/dnf."""
    try:
        proc = subprocess.Popen(
            _get_pkexec_install_cmd(pkg_name),
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


def remove_package_stream(pkg_name: str):
    """Generator that yields output lines from remove command.
    Uses rakuos CLI if available, falls back to dnf5/dnf."""
    try:
        proc = subprocess.Popen(
            _get_pkexec_remove_cmd(pkg_name),
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


# ── AppStream ──────────────────────────────────────────────────────────────

def preload_appstream():
    """Call this in a background thread at startup to preload the cache."""
    threading.Thread(target=_load_appstream, daemon=True).start()


def _load_appstream() -> dict:
    """Load and cache AppStream component data from system XML files."""
    global _appstream_cache
    with _cache_lock:
        if _appstream_cache:
            return _appstream_cache

        apps = {}

        for appstream_dir, source in APPSTREAM_DIRS:
            if not os.path.isdir(appstream_dir):
                continue
            for fname in os.listdir(appstream_dir):
                fpath = os.path.join(appstream_dir, fname)
                tree = None
                try:
                    if fname.endswith(".gz"):
                        with gzip.open(fpath, "rt", encoding="utf-8", errors="ignore") as fh:
                            tree = ET.parse(fh)
                    elif fname.endswith(".xml"):
                        with open(fpath, "rt", encoding="utf-8", errors="ignore") as fh:
                            tree = ET.parse(fh)
                    else:
                        continue
                except Exception as e:
                    print(f"AppStream parse error {fname}: {e}")
                    continue

                try:
                    root = tree.getroot()
                    if root.tag == "component":
                        components = [root]
                    else:
                        components = root.findall("component")
                    for comp in components:
                        app = _parse_component(comp, source=source)
                        if app:
                            apps[app["id"]] = app
                except Exception as e:
                    print(f"AppStream process error {fname}: {e}")
                    continue

        print(f"AppStream loaded {len(apps)} apps")
        _appstream_cache = apps
        _cache_ready.set()
        return apps


def _parse_component(comp, source: str = "native") -> Optional[dict]:
    """Parse a single AppStream component element."""
    kind = comp.get("type", "")
    is_addon = (kind == "addon")
    if kind not in ("desktop", "desktop-application", "console-application", "", "addon"):
        return None

    app_id = (comp.findtext("id") or "").strip()
    if not app_id:
        return None

    name = _get_localized(comp, "name") or app_id
    summary = _get_localized(comp, "summary")

    description = _get_localized_description(comp)

    # Categories
    categories = []
    cats_el = comp.find("categories")
    if cats_el is not None:
        categories = [c.text.strip() for c in cats_el.findall("category") if c.text]

    # Icon — prefer cached then stock
    icon = ""
    for icon_el in comp.findall("icon"):
        if icon_el.get("type") == "cached" and not icon:
            icon = icon_el.text or ""
        elif icon_el.get("type") == "stock" and not icon:
            icon = icon_el.text or ""
    # Flatpak icons are always named after the full app id
    if source == "flatpak":
        icon = f"{app_id}.png"

    # Screenshots
    screenshots = []
    for ss in comp.findall(".//screenshot"):
        img = ss.find("image")
        if img is not None and img.text:
            screenshots.append(img.text.strip())

    # Package name
    if source == "flatpak":
        pkg_name = app_id
    else:
        raw_pkg = comp.findtext("pkgname")
        if not raw_pkg:
            clean_id = app_id.replace(".desktop", "")
            raw_pkg = clean_id.split(".")[-1].lower()
        pkg_name = raw_pkg

    # Project URL
    url = ""
    for url_el in comp.findall("url"):
        if url_el.get("type") == "homepage":
            url = url_el.text or ""
            break

    extends_id = (comp.findtext("extends") or "").strip()

    result = {
        "id": app_id,
        "name": name,
        "summary": summary,
        "description": description,
        "categories": categories,
        "icon": icon,
        "screenshots": screenshots,
        "pkg_name": pkg_name,
        "url": url,
        "source": source,
        "installed": False,
        "is_addon": is_addon,
    }
    if extends_id:
        result["extends"] = extends_id
    return result


def _enrich_installed(app: dict) -> dict:
    """Add installed status to an app dict."""
    app = dict(app)
    if app["source"] == "flatpak":
        app["installed"] = is_installed_flatpak(app["pkg_name"])
    else:
        app["installed"] = is_installed_native(app["pkg_name"])
    return app


def _enrich_detail(app: dict) -> dict:
    """
    Fetch version, installed-size, and license for the detail page.
    For native packages: rpm -q (installed) or repoquery (not installed)
    For flatpak: flatpak info (installed) or flatpak remote-info (not installed)
    """
    if not app:
        return app
    app = dict(app)
    if app.get("local_rpm"):
        return app
    logging.debug("_enrich_detail called: pkg_name=%r source=%r installed=%r",
                  app.get("pkg_name"), app.get("source"), app.get("installed"))

    if app.get("source") == "flatpak":
        def _parse_flatpak_lines(text):
            for line in text.splitlines():
                if ":" not in line:
                    continue
                k, _, v = line.partition(":")
                k, v = k.strip().lower(), v.strip()
                if k == "version" and not app.get("version"):
                    app["version"] = v
                elif k in ("installed size", "download size") and not app.get("size"):
                    try:
                        parts = v.split()
                        num = float(parts[0].replace(",", "."))
                        unit = parts[1].upper() if len(parts) > 1 else "B"
                        mult = {"B": 1, "KB": 1024, "MB": 1024**2,
                                "MIB": 1024**2, "GB": 1024**3, "GIB": 1024**3}
                        app["size"] = int(num * mult.get(unit, 1))
                    except Exception:
                        pass

        if app.get("installed"):
            try:
                r = subprocess.run(
                    ["flatpak", "info", app["pkg_name"]],
                    capture_output=True, text=True, timeout=8
                )
                logging.debug("flatpak info: %r", r.stdout[:300])
                _parse_flatpak_lines(r.stdout)
            except Exception as e:
                logging.debug("flatpak info error: %s", e)
        else:
            remote = app.get("origin") or app.get("remote") or "flathub"
            try:
                r = subprocess.run(
                    ["flatpak", "remote-info", remote, app["pkg_name"]],
                    capture_output=True, text=True, timeout=10
                )
                logging.debug("flatpak remote-info: %r", r.stdout[:300])
                _parse_flatpak_lines(r.stdout)
            except Exception as e:
                logging.debug("flatpak remote-info error: %s", e)
    else:
        fmt = "%{VERSION}-%{RELEASE}\t%{SIZE}\t%{LICENSE}"

        def _parse_rpm_output(stdout):
            parts = stdout.strip().split("\t")
            if len(parts) >= 1 and parts[0] and "not installed" not in parts[0]:
                app["version"] = parts[0]
            if len(parts) >= 2:
                try:
                    app["size"] = int(parts[1])
                except Exception:
                    pass
            if len(parts) >= 3 and parts[2] not in ("", "(none)"):
                app["license"] = parts[2]

        def _try_rpm_q(name):
            """Try rpm -q with a name, return True if it worked."""
            try:
                r = subprocess.run(
                    ["rpm", "-q", "--queryformat", fmt, name],
                    capture_output=True, text=True, timeout=8
                )
                logging.debug("rpm -q %s: rc=%d out=%r", name, r.returncode, r.stdout[:200])
                if r.returncode == 0 and r.stdout.strip():
                    _parse_rpm_output(r.stdout)
                    return True
            except Exception as e:
                logging.debug("rpm -q error: %s", e)
            return False

        if app.get("installed"):
            # Try pkg_name first, then app name, then search rpm -qa for app id fragment
            if not _try_rpm_q(app["pkg_name"]):
                name_guess = app.get("name", "").lower().replace(" ", "-")
                if not _try_rpm_q(name_guess):
                    # Last resort: search installed rpms for anything matching the id fragment
                    try:
                        frag = app["pkg_name"].lower()
                        r = subprocess.run(
                            ["rpm", "-qa", "--queryformat", f"%{{NAME}}\t{fmt}\n"],
                            capture_output=True, text=True, timeout=10
                        )
                        for line in r.stdout.splitlines():
                            parts = line.split("\t")
                            if len(parts) >= 1 and frag in parts[0].lower():
                                logging.debug("rpm -qa match: %s", parts[0])
                                app["pkg_name"] = parts[0]
                                _parse_rpm_output("\t".join(parts[1:]))
                                break
                    except Exception as e:
                        logging.debug("rpm -qa error: %s", e)
        else:
            def _try_repoquery(name):
                try:
                    mgr = _get_dnf()
                    # DNF5 uses --qf, DNF4 uses --queryformat — try both
                    for qf_flag in ("--queryformat", "--qf"):
                        r = subprocess.run(
                            mgr + ["repoquery", qf_flag, fmt, name],
                            capture_output=True, text=True, timeout=20
                        )
                        logging.debug("repoquery %s %s: rc=%d out=%r err=%r",
                                      qf_flag, name, r.returncode,
                                      r.stdout[:200], r.stderr[:100])
                        if r.returncode == 0 and r.stdout.strip():
                            parts = r.stdout.strip().splitlines()[-1].split("\t")
                            if len(parts) >= 1 and parts[0]:
                                app["version"] = parts[0]
                            if len(parts) >= 2:
                                try:
                                    app["size"] = int(parts[1])
                                except Exception:
                                    pass
                            if len(parts) >= 3 and parts[2] not in ("", "(none)"):
                                app["license"] = parts[2]
                            return True
                except Exception as e:
                    logging.debug("repoquery exception: %s", e)
                return False

            if not _try_repoquery(app["pkg_name"]):
                name_guess = app.get("name", "").lower().replace(" ", "-")
                _try_repoquery(name_guess)

    logging.debug("_enrich_detail %s: version=%r size=%r license=%r",
                  app.get("pkg_name"), app.get("version"), app.get("size"), app.get("license"))
    return app


def search_dnf(query: str, limit: int = 20) -> list[dict]:
    """Search DNF metadata for packages not in AppStream."""
    try:
        # Use separate queries to avoid multiline description breaking parsing
        name_result = subprocess.run(
            _get_dnf() + ["repoquery", "--queryformat", "%{name}", f"*{query}*"],
            capture_output=True, text=True, timeout=15
        )
        names = [n.strip() for n in name_result.stdout.splitlines() if n.strip()]
        if not names:
            return []

        # Deduplicate and filter out meta/virtual packages
        # e.g. ardour6ardour7ardour8ardour9 — name+digit pattern repeated 3+ times
        seen = set()
        filtered = []
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            # Skip names that look like concatenated versioned packages
            if re.search(r'([a-zA-Z]+\d+){3,}', name):
                continue
            filtered.append(name)
        names = filtered

        apps = _load_appstream()
        existing_pkgs = {a["pkg_name"] for a in apps.values()}
        results = []

        # Build a lookup of Flatpak apps by name for matching
        flatpak_by_name = {}
        for app in apps.values():
            if app["source"] == "flatpak":
                flatpak_by_name[app["name"].lower()] = app
                # Also index by last segment of app id e.g. "Lutris" from "net.lutris.Lutris"
                last_seg = app["id"].split(".")[-1].lower()
                flatpak_by_name[last_seg] = app

        for name in names:
            if name in existing_pkgs:
                continue

            # Check if a Flatpak entry already covers this package
            flatpak_match = flatpak_by_name.get(name.lower())
            if flatpak_match:
                # Use Flatpak metadata but mark as native source so it installs via DNF
                entry = dict(flatpak_match)
                entry["pkg_name"] = name
                entry["source"] = "native"
                entry["installed"] = is_installed_native(name)
                results.append(entry)
                if len(results) >= limit:
                    break
                continue

            # No Flatpak match — fetch details from DNF
            info = subprocess.run(
                _get_dnf() + ["repoquery", "--queryformat",
                 "%{summary}||END||%{url}", name],
                capture_output=True, text=True, timeout=10
            )
            parts = info.stdout.strip().split("||END||")
            summary = parts[0].strip() if parts else ""
            url = parts[1].strip() if len(parts) > 1 else ""

            desc = subprocess.run(
                _get_dnf() + ["repoquery", "--queryformat", "%{description}", name],
                capture_output=True, text=True, timeout=10
            )
            description = desc.stdout.strip()

            results.append({
                "id": name,
                "name": name,
                "summary": summary,
                "description": description,
                "categories": [],
                "icon": "",
                "screenshots": [],
                "pkg_name": name,
                "url": url,
                "source": "native",
                "installed": is_installed_native(name),
            })
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        print(f"DNF search error: {e}")
        return []


def search_packages(query: str, limit: int = 40) -> list[dict]:
    """Search AppStream data by name/summary, supplemented by DNF metadata."""
    apps = _load_appstream()
    query_lower = query.lower()
    results = []
    for app in apps.values():
        if (query_lower in app["name"].lower() or
                query_lower in app["summary"].lower() or
                query_lower in app["pkg_name"].lower()):
            results.append(_enrich_installed(app))
        if len(results) >= limit:
            break
    # Supplement with DNF for packages not in AppStream
    results += search_dnf(query, limit=20)
    return results


def get_by_category(category: str, limit: int = 40, offset: int = 0, source: str = "all") -> dict:
    apps = _load_appstream()
    raw = []
    for app in apps.values():
        if source != "all" and app["source"] != source:
            continue
        if any(category.lower() in c.lower() for c in app["categories"]):
            raw.append(app)

    # Deduplicate by name+source — keep highest pkg_name version
    seen: dict = {}
    for app in raw:
        key = (app["name"].lower(), app["source"])
        existing = seen.get(key)
        if not existing or app["pkg_name"] > existing["pkg_name"]:
            seen[key] = app
    all_results = list(seen.values())

    total = len(all_results)
    page = [_enrich_installed(a) for a in all_results[offset:offset + limit]]
    return {"items": page, "total": total, "offset": offset, "limit": limit}


def get_installed_with_metadata() -> list[dict]:
    """Return installed overlay packages enriched with AppStream metadata where available."""
    installed = get_installed_packages()
    apps = _load_appstream()
    pkg_map = {a["pkg_name"]: a for a in apps.values()}

    # Build Flatpak lookup by name and last ID segment for fallback matching
    flatpak_by_name = {}
    for app in apps.values():
        if app["source"] == "flatpak":
            flatpak_by_name[app["name"].lower()] = app
            last_seg = app["id"].split(".")[-1].lower()
            flatpak_by_name[last_seg] = app

    results = []
    for pkg in installed:
        if pkg in pkg_map:
            app = dict(pkg_map[pkg])
            app["installed"] = True
            results.append(app)
        else:
            # Try matching against Flatpak metadata for icon/description
            flatpak_match = flatpak_by_name.get(pkg.lower())
            if flatpak_match:
                entry = dict(flatpak_match)
                entry["pkg_name"] = pkg
                entry["source"] = "native"
                entry["installed"] = True
                results.append(entry)
            else:
                results.append({
                    "id": pkg,
                    "name": pkg,
                    "summary": "Installed package",
                    "description": "",
                    "categories": [],
                    "icon": "",
                    "screenshots": [],
                    "pkg_name": pkg,
                    "url": "",
                    "source": "native",
                    "installed": True,
                })
    return results


def find_icon(filename: str) -> Optional[str]:
    """Find an icon file across all known icon directories."""
    for icon_dir in ICON_DIRS:
        fpath = os.path.join(icon_dir, filename)
        if os.path.exists(fpath):
            return fpath
    return None

def get_addons_for(app_id: str) -> list[dict]:
    """
    Return AppStream addon components that extend the given app_id.
    Add-ons have <component type="addon"> with <extends>parent_id</extends>.
    Returns list of dicts with: id, name, summary, pkg_name, source, installed.
    """
    cache = _load_appstream()
    return [item for item in cache.values() if item.get("extends") == app_id]


def get_local_rpm_info(rpm_path: str) -> dict:
    """
    Extract metadata from a local .rpm file using rpm -qip.
    Returns an app dict compatible with the detail page.
    Falls back gracefully if rpm isn't available.
    """
    fields = {
        "Name":        "%{NAME}",
        "Version":     "%{VERSION}-%{RELEASE}",
        "Summary":     "%{SUMMARY}",
        "Description": "%{DESCRIPTION}",
        "URL":         "%{URL}",
        "License":     "%{LICENSE}",
        "Size":        "%{SIZE}",
        "Arch":        "%{ARCH}",
    }
    fmt = "\n".join(f"{k}: {v}" for k, v in fields.items())
    try:
        r = subprocess.run(
            ["rpm", "--queryformat", fmt, "-qp", rpm_path],
            capture_output=True, text=True, timeout=10
        )
        data = {}
        for line in r.stdout.splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                data[k.strip()] = v.strip()
    except Exception:
        data = {}

    name    = data.get("Name", os.path.basename(rpm_path).replace(".rpm", ""))
    version = data.get("Version", "")
    summary = data.get("Summary", "")
    desc    = data.get("Description", "")
    url     = data.get("URL", "") if data.get("URL", "") != "(none)" else ""
    size    = int(data.get("Size", 0) or 0)

    # Check if already installed
    already_installed = is_installed_native(name)

    return {
        "id":           name,
        "name":         name,
        "version":      version,
        "summary":      summary,
        "description":  desc,
        "categories":   [],
        "icon":         "",
        "screenshots":  [],
        "pkg_name":     name,
        "url":          url,
        "source":       "native",
        "local_rpm":    rpm_path,       # signals detail page this is a local file
        "installed":    already_installed,
        "size":         size,
        "license":      data.get("License", ""),
        "arch":         data.get("Arch", ""),
    }


def install_local_rpm_stream(rpm_path: str):
    """
    Generator that yields output lines from installing a local .rpm file.
    Uses dnf5/dnf to install so deps are resolved automatically.
    """
    mgr = _get_pkg_manager()
    cmd = mgr + ["install", "-y", rpm_path]
    try:
        proc = subprocess.Popen(
            ["pkexec"] + cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait()
        yield f"__done__{proc.returncode}"
    except Exception as e:
        yield f"Error: {e}"
        yield "__done__1"
