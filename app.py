from flask import Flask, jsonify, request, render_template, session, redirect, url_for, abort
from flask_cors import CORS
from cryptography.fernet import Fernet
import requests
import re
import os
import logging
import threading
import json
import ipaddress
import hashlib
import secrets
import time
import unicodedata
import base64

APP_VERSION = "1.5.3"

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"Removarr v{APP_VERSION} starting")


# ─── Encryption for sensitive fields ─────────────────────────────────────────

# Derive a stable Fernet key from SECRET_KEY (Fernet needs 32 url-safe base64 bytes)
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(app.config["SECRET_KEY"].encode()).digest())
_fernet = Fernet(_fernet_key)

# Fields that are encrypted at rest in settings.json
ENCRYPTED_FIELDS = {
    "radarr_api_key", "sonarr_api_key", "qbit_password",
    "tmdb_api_key", "seerr_api_key", "tautulli_api_key",
}

def _encrypt(value):
    """Encrypt a string value. Returns prefixed encrypted string."""
    if not value or value.startswith("ENC:"):
        return value
    return "ENC:" + _fernet.encrypt(value.encode()).decode()

def _decrypt(value):
    """Decrypt a value. Returns plain text. Handles unencrypted legacy values."""
    if not value:
        return value
    if not value.startswith("ENC:"):
        return value  # Legacy unencrypted value — return as-is
    try:
        return _fernet.decrypt(value[4:].encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt a field — SECRET_KEY may have changed")
        return ""


@app.after_request
def set_cache_headers(response):
    """Prevent browser from caching HTML pages (forces fresh load after deploy)."""
    if response.content_type and "text/html" in response.content_type:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ─── Auth & IP whitelist ──────────────────────────────────────────────────────

def _get_auth_username():
    """Return configured username, or 'admin' as default."""
    # Settings file > env var > default
    u = _runtime_settings.get("removarr_username") or os.environ.get("REMOVARR_USERNAME", "").strip()
    return u if u else "admin"

def _get_password():
    """Return configured password (plain or hash), or None if auth disabled."""
    # Settings file takes priority (stored as hash)
    pw_hash = _runtime_settings.get("removarr_password_hash", "").strip()
    if pw_hash:
        return pw_hash
    # Fallback to env var (plain text)
    pw = os.environ.get("REMOVARR_PASSWORD", "").strip()
    return pw if pw else None

def _get_allowed_ips():
    """Return list of allowed IP networks, or None if whitelist disabled."""
    raw = (_runtime_settings.get("removarr_allowed_ips") or os.environ.get("REMOVARR_ALLOWED_IPS", "")).strip()
    if not raw:
        return None
    networks = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.warning(f"Invalid IP/CIDR in REMOVARR_ALLOWED_IPS: {part}")
    return networks if networks else None

def _get_client_ip():
    """Get real client IP, respecting X-Forwarded-For if behind proxy."""
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")
    if forwarded and forwarded[0].strip():
        return forwarded[0].strip()
    return request.remote_addr or "127.0.0.1"

def _ip_allowed():
    """Check if client IP is in the whitelist (always True if no whitelist configured)."""
    networks = _get_allowed_ips()
    if networks is None:
        return True
    try:
        client = ipaddress.ip_address(_get_client_ip())
        return any(client in net for net in networks)
    except ValueError:
        return False

def _hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def _auth_required():
    """Return True if auth is enabled."""
    return _get_password() is not None

def _is_authenticated():
    """Check if current session is authenticated."""
    if not _auth_required():
        return True
    return session.get("authenticated") is True

def _check_access():
    """Combined IP + auth check. Returns error response or None if OK."""
    if not _ip_allowed():
        logger.warning(f"Blocked request from {_get_client_ip()} (not in whitelist)")
        abort(403)
    if not _is_authenticated():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized", "login_required": True}), 401
        return redirect(url_for("login_page"))
    return None


# ─── Settings (override env vars at runtime) ──────────────────────────────────

SETTINGS_FILE = "/data/settings.json"
_settings_lock = threading.Lock()

def load_settings():
    """Load settings from disk, fallback to env vars."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load settings: {e}")
    return {}

def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with _settings_lock:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.warning(f"Could not save settings: {e}")
        return False

def _cfg(key, env_key, default=""):
    """Get config value: settings file > env var > default. Auto-decrypts encrypted fields."""
    val = _runtime_settings.get(key) or os.environ.get(env_key, default)
    if key in ENCRYPTED_FIELDS and val:
        return _decrypt(val)
    return val

# Load settings once at startup, store in memory
_runtime_settings = load_settings()

def get_radarr_url():     return _cfg("radarr_url",     "RADARR_URL",     "http://localhost:7878")
def get_radarr_key():     return _cfg("radarr_api_key", "RADARR_API_KEY", "")
def get_sonarr_url():     return _cfg("sonarr_url",     "SONARR_URL",     "http://localhost:8989")
def get_sonarr_key():     return _cfg("sonarr_api_key", "SONARR_API_KEY", "")
def get_qbit_url():       return _cfg("qbit_url",       "QBIT_URL",       "http://localhost:8080")
def get_qbit_username():  return _cfg("qbit_username",  "QBIT_USERNAME",  "admin")
def get_qbit_password():  return _cfg("qbit_password",  "QBIT_PASSWORD",  "adminadmin")
def get_tmdb_key():       return _cfg("tmdb_api_key",   "TMDB_API_KEY",   "")
def get_seerr_url():      return _cfg("seerr_url",      "SEERR_URL",      "")
def get_seerr_key():      return _cfg("seerr_api_key",  "SEERR_API_KEY",  "")

# ─── TMDB ─────────────────────────────────────────────────────────────────────

CACHE_FILE   = os.environ.get("CACHE_FILE", "/data/tmdb_cache.json")
POSTERS_DIR  = os.path.join(os.path.dirname(os.environ.get("CACHE_FILE", "/data/tmdb_cache.json")), "posters")
_tmdb_cache = {}
_tmdb_lock  = threading.Lock()

def _load_cache():
    global _tmdb_cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                raw = json.load(f)
            # Discard stale entries that have no titles key at all (built before alt_titles support)
            _tmdb_cache = {k: v for k, v in raw.items() if "titles" in v}
            discarded = len(raw) - len(_tmdb_cache)
            logger.info(f"TMDB cache loaded: {len(_tmdb_cache)} entries ({discarded} stale discarded)")
    except Exception as e:
        logger.warning(f"Could not load TMDB cache: {e}")

_load_cache()  # Load cache at startup

def _save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with _tmdb_lock:
            with open(CACHE_FILE, "w") as f:
                json.dump(_tmdb_cache, f)
    except Exception as e:
        logger.warning(f"Could not save TMDB cache: {e}")

def _tmdb_get(url):
    key = get_tmdb_key().strip('"').strip("'")
    if len(key) > 40:
        clean = re.sub(r'[?&]api_key=[^&]*', '', url).rstrip('?').rstrip('&')
        return requests.get(clean, headers={"Authorization": f"Bearer {key}"}, timeout=8)
    return requests.get(url, timeout=8)

def fetch_tmdb_data(media_id, media_type):
    if not get_tmdb_key() or not media_id:
        return {"poster": None, "titles": []}
    cache_key = f"{media_type}-{media_id}"
    with _tmdb_lock:
        if cache_key in _tmdb_cache:
            return _tmdb_cache[cache_key]
    result = {"poster": None, "titles": []}
    key = get_tmdb_key().strip('"').strip("'")
    try:
        if media_type == "movie":
            r = _tmdb_get(f"https://api.themoviedb.org/3/movie/{media_id}?api_key={key}&append_to_response=alternative_titles&language=fr-FR")
            data = r.json()
            result["poster"] = f"https://image.tmdb.org/t/p/w300{data['poster_path']}" if data.get("poster_path") else None
            titles = set()
            titles.add(data.get("title", "").lower())
            titles.add(data.get("original_title", "").lower())
            for t in data.get("alternative_titles", {}).get("titles", []):
                titles.add(t.get("title", "").lower())
            result["titles"] = [t for t in titles if t]
        else:
            r = _tmdb_get(f"https://api.themoviedb.org/3/find/{media_id}?api_key={key}&external_source=tvdb_id")
            tv_list = r.json().get("tv_results", [])
            if tv_list:
                tv = tv_list[0]
                tmdb_tv_id = tv["id"]
                result["poster"] = f"https://image.tmdb.org/t/p/w300{tv['poster_path']}" if tv.get("poster_path") else None
                r2 = _tmdb_get(f"https://api.themoviedb.org/3/tv/{tmdb_tv_id}/alternative_titles?api_key={key}")
                titles = set()
                titles.add(tv.get("name", "").lower())
                titles.add(tv.get("original_name", "").lower())
                for t in r2.json().get("results", []):
                    titles.add(t.get("title", "").lower())
                result["titles"] = [t for t in titles if t]
    except Exception as e:
        logger.warning(f"TMDB fetch failed for {cache_key}: {e}")
    with _tmdb_lock:
        _tmdb_cache[cache_key] = result
    _save_cache()
    return result

# ─── Poster cache (serve posters as local files) ──────────────────────────────

def get_poster_path(media_type, media_id):
    return os.path.join(POSTERS_DIR, f"{media_type}_{media_id}.jpg")

def poster_cached(media_type, media_id):
    return os.path.exists(get_poster_path(media_type, media_id))

def save_poster(media_type, media_id, url):
    try:
        os.makedirs(POSTERS_DIR, exist_ok=True)
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.headers.get("content-type","").startswith("image"):
            with open(get_poster_path(media_type, media_id), "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        logger.warning(f"Failed to save poster {media_type}_{media_id}: {e}")
    return False

# ─── Matching ─────────────────────────────────────────────────────────────────

def _slugify(s):
    if not s:
        return ""
    s = str(s).lower()
    # Normalize unicode: strip diacritics (é→e, ï→i, ü→u, etc.)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _prepare_torrents(all_torrents):
    """Pre-compute slugs and word-sets for all torrents. Call once per request."""
    result = []
    for t in all_torrents:
        name = t.get("name") or ""
        slug = _slugify(name)
        result.append({
            **t,
            "_slug": slug,
            "_words": frozenset(slug.split()),
        })
    return result

def _build_word_index(prepared_torrents):
    """Build inverted index: word → set of torrent indices for fast candidate lookup."""
    idx = {}
    for i, t in enumerate(prepared_torrents):
        for w in t["_words"]:
            if w not in idx:
                idx[w] = set()
            idx[w].add(i)
    return idx

def find_matching_torrents(title, year=None, all_torrents=None, alt_titles=None, _word_index=None):
    if all_torrents is None:
        all_torrents = get_qbit_torrents()

    # Support both raw and pre-prepared torrent lists
    if all_torrents and "_slug" not in all_torrents[0]:
        all_torrents = _prepare_torrents(all_torrents)

    # Build word index if not provided
    if _word_index is None:
        _word_index = _build_word_index(all_torrents)

    # Pre-slugify all search titles
    search_slugs = [_slugify(title)]
    if alt_titles:
        search_slugs.extend(_slugify(t) for t in alt_titles if t)
    search_slugs = [s for s in search_slugs if s and len(s) >= 3]

    year_str = str(year) if year else None
    seen_hashes = set()
    matches = []

    for search_slug in search_slugs:
        title_words = search_slug.split()

        # Strategy 1: word-based lookup via inverted index (fast)
        if len(title_words) >= 2:
            # Intersect candidate sets for each word
            candidate_sets = [_word_index.get(w) for w in title_words]
            if all(s is not None for s in candidate_sets):
                candidates = candidate_sets[0]
                for s in candidate_sets[1:]:
                    candidates = candidates & s
                for i in candidates:
                    t = all_torrents[i]
                    h = t.get("hash", "")
                    if h in seen_hashes:
                        continue
                    if year_str and year_str not in t.get("name", ""):
                        continue
                    matches.append(t)
                    seen_hashes.add(h)

        # Strategy 2: substring search (fallback, slower but catches partial matches)
        for i, t in enumerate(all_torrents):
            h = t.get("hash", "")
            if h in seen_hashes:
                continue
            if search_slug in t["_slug"]:
                if year_str and year_str not in t.get("name", ""):
                    continue
                matches.append(t)
                seen_hashes.add(h)

    return matches

# ─── qBittorrent ──────────────────────────────────────────────────────────────

qbit_session = requests.Session()

def qbit_login():
    try:
        r = qbit_session.post(f"{get_qbit_url()}/api/v2/auth/login",
                              data={"username": get_qbit_username(), "password": get_qbit_password()},
                              timeout=5)
        return r.text == "Ok."
    except Exception as e:
        logger.error(f"qBittorrent login failed: {e}")
        return False

def get_qbit_torrents():
    try:
        r = qbit_session.get(f"{get_qbit_url()}/api/v2/torrents/info", timeout=10)
        if r.status_code == 403:
            qbit_login()
            r = qbit_session.get(f"{get_qbit_url()}/api/v2/torrents/info", timeout=10)
        return r.json()
    except Exception as e:
        logger.error(f"Failed to get torrents: {e}")
        return []

# Short-lived cache for enrichment batches (avoid re-fetching qbit torrents 14 times)
_qbit_cache = {"data": None, "prepared": None, "word_index": None, "ts": 0}
QBIT_CACHE_TTL = 30  # seconds

def get_qbit_torrents_cached():
    """Get qbit torrents with 30s cache — used by enrich batches."""
    now = time.time()
    if _qbit_cache["data"] is not None and now - _qbit_cache["ts"] < QBIT_CACHE_TTL:
        return _qbit_cache["data"]
    data = get_qbit_torrents()
    prepared = _prepare_torrents(data)
    _qbit_cache["data"] = data
    _qbit_cache["prepared"] = prepared
    _qbit_cache["word_index"] = _build_word_index(prepared)
    _qbit_cache["ts"] = now
    return data

def get_prepared_torrents_cached():
    """Get pre-processed torrents with 30s cache."""
    now = time.time()
    if _qbit_cache["prepared"] is not None and now - _qbit_cache["ts"] < QBIT_CACHE_TTL:
        return _qbit_cache["prepared"]
    get_qbit_torrents_cached()  # populates all caches
    return _qbit_cache["prepared"] or []

def get_word_index_cached():
    """Get word index with 30s cache."""
    now = time.time()
    if _qbit_cache["word_index"] is not None and now - _qbit_cache["ts"] < QBIT_CACHE_TTL:
        return _qbit_cache["word_index"]
    get_qbit_torrents_cached()
    return _qbit_cache["word_index"] or {}

def delete_torrents(hashes, delete_files=False):
    if not hashes:
        return True
    try:
        r = qbit_session.post(f"{get_qbit_url()}/api/v2/torrents/delete",
                              data={"hashes": "|".join(hashes), "deleteFiles": str(delete_files).lower()},
                              timeout=10)
        if r.status_code == 403:
            qbit_login()
            r = qbit_session.post(f"{get_qbit_url()}/api/v2/torrents/delete",
                                  data={"hashes": "|".join(hashes), "deleteFiles": str(delete_files).lower()},
                                  timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Failed to delete torrents: {e}")
        return False

# ─── Radarr ───────────────────────────────────────────────────────────────────

def get_radarr_movies():
    if not get_radarr_url() or not get_radarr_key():
        return []
    try:
        r = requests.get(f"{get_radarr_url()}/api/v3/movie",
                         headers={"X-Api-Key": get_radarr_key()}, timeout=10)
        return r.json()
    except Exception as e:
        logger.error(f"Radarr error: {e}")
        return []

def delete_radarr_movie(movie_id, delete_files=True):
    try:
        r = requests.delete(f"{get_radarr_url()}/api/v3/movie/{movie_id}",
                            params={"deleteFiles": delete_files, "addImportExclusion": False},
                            headers={"X-Api-Key": get_radarr_key()}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Failed to delete movie {movie_id}: {e}")
        return False

# ─── Sonarr ───────────────────────────────────────────────────────────────────

def get_sonarr_series():
    if not get_sonarr_url() or not get_sonarr_key():
        return []
    try:
        r = requests.get(f"{get_sonarr_url()}/api/v3/series",
                         headers={"X-Api-Key": get_sonarr_key()}, timeout=10)
        return r.json()
    except Exception as e:
        logger.error(f"Sonarr error: {e}")
        return []

def delete_sonarr_series(series_id, delete_files=True):
    try:
        r = requests.delete(f"{get_sonarr_url()}/api/v3/series/{series_id}",
                            params={"deleteFiles": delete_files},
                            headers={"X-Api-Key": get_sonarr_key()}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Failed to delete series {series_id}: {e}")
        return False

# ─── Seerr ────────────────────────────────────────────────────────────────────

def seerr_get_requests(tmdb_id, media_type):
    """Find all requests in Seerr for a given tmdbId."""
    if not get_seerr_url() or not get_seerr_key():
        return []
    headers = {"X-Api-Key": get_seerr_key()}
    status_map = {1: "pending", 2: "approved", 3: "declined", 4: "processing", 5: "available"}

    def parse_req(req):
        return {
            "id":           req.get("id"),
            "status":       status_map.get(req.get("status"), "unknown"),
            "status_code":  req.get("status"),
            "created_at":   req.get("createdAt", ""),
            "requested_by": req.get("requestedBy", {}).get("displayName", "?"),
            "seasons":      [s.get("seasonNumber") for s in req.get("seasons", [])],
        }

    results = []
    seen_ids = set()
    tmdb_id_int = int(tmdb_id) if tmdb_id else None

    try:
        # Strategy: scan /api/v1/request?filter=all and match by tmdbId
        # This works for ALL statuses including "available"
        skip = 0
        take = 100
        while True:
            r = requests.get(
                f"{get_seerr_url()}/api/v1/request",
                params={"filter": "all", "take": take, "skip": skip},
                headers=headers, timeout=10
            )
            if r.status_code != 200:
                break
            data = r.json()
            page_results = data.get("results", [])
            if not page_results:
                break
            for req in page_results:
                req_media = req.get("media", {})
                # Match by tmdbId (stored as tmdbId or id depending on Seerr version)
                req_tmdb = req_media.get("tmdbId") or req_media.get("externalServiceId")
                req_type = req.get("type", "")  # "movie" or "tv"
                expected_type = "movie" if media_type == "movie" else "tv"
                if (req_tmdb == tmdb_id_int or str(req_tmdb) == str(tmdb_id))                         and req_type == expected_type                         and req.get("id") not in seen_ids:
                    results.append(parse_req(req))
                    seen_ids.add(req.get("id"))
            # Check pagination
            total = data.get("pageInfo", {}).get("results", len(page_results))
            skip += take
            if skip >= total or len(page_results) < take:
                break
    except Exception as e:
        logger.warning(f"Seerr lookup failed for tmdb:{tmdb_id}: {e}")

    # Fallback: also check mediaInfo.requests directly
    if not results:
        try:
            media_endpoint = "movie" if media_type == "movie" else "tv"
            r = requests.get(
                f"{get_seerr_url()}/api/v1/{media_endpoint}/{tmdb_id}",
                headers=headers, timeout=8
            )
            if r.status_code == 200:
                media_info = r.json().get("mediaInfo") or {}
                for req in media_info.get("requests", []):
                    if req.get("id") not in seen_ids:
                        results.append(parse_req(req))
                        seen_ids.add(req.get("id"))
        except Exception as e:
            logger.warning(f"Seerr mediaInfo fallback failed: {e}")

    logger.info(f"Seerr: found {len(results)} requests for tmdb:{tmdb_id}")
    return results


def seerr_delete_request(request_id):
    """Delete a specific request from Seerr."""
    if not get_seerr_url() or not get_seerr_key():
        return False
    try:
        r = requests.delete(
            f"{get_seerr_url()}/api/v1/request/{request_id}",
            headers={"X-Api-Key": get_seerr_key()}, timeout=8
        )
        return r.status_code in (200, 204)
    except Exception as e:
        logger.warning(f"Seerr delete request {request_id} failed: {e}")
        return False


def _setup_completed():
    """Check if initial setup has been completed."""
    # Setup is done if settings.json exists with at least one arr service configured
    if not _runtime_settings:
        # No settings file — check env vars
        return bool((get_radarr_url() and get_radarr_key()) or (get_sonarr_url() and get_sonarr_key()))
    return _runtime_settings.get("setup_completed", False)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not _setup_completed():
        return redirect(url_for("setup_page"))
    response = app.make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/setup")
def setup_page():
    if _setup_completed():
        return redirect(url_for("index"))
    return render_template("setup.html")

# ─── Auth routes ─────────────────────────────────────────────────────────────

@app.before_request
def enforce_access():
    """Enforce IP whitelist and auth on every request except login/setup endpoints."""
    # Always allow login, logout
    if request.path in ("/login", "/logout"):
        return None
    # Setup pages: only accessible before setup is completed
    if request.path == "/setup" or request.path.startswith("/api/setup"):
        if _setup_completed():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Setup already completed"}), 403
            return redirect(url_for("index"))
        return None
    # Public read-only endpoints (no sensitive data)
    if request.path == "/api/config-status":
        return None
    if request.path == "/api/version":
        return None
    # Always allow static files
    if request.path.startswith("/static/"):
        return None
    err = _check_access()
    if err is not None:
        return err

@app.route("/login", methods=["GET"])
def login_page():
    if not _auth_required():
        return redirect(url_for("index"))
    if _is_authenticated():
        return redirect(url_for("index"))
    error = request.args.get("error", "")
    return render_template("login.html", error=error)

@app.route("/login", methods=["POST"])
def login_post():
    if not _ip_allowed():
        abort(403)
    pw = _get_password()
    if pw is None:
        return redirect(url_for("index"))
    submitted_user = request.form.get("username", "").strip()
    submitted_pw = request.form.get("password", "")
    # Check username
    expected_user = _get_auth_username()
    if submitted_user and submitted_user != expected_user:
        return redirect(url_for("login_page") + "?error=1")
    # Check password: if stored as hash (from settings), compare hashes; if from env, hash both
    submitted_hash = _hash_password(submitted_pw)
    if _runtime_settings.get("removarr_password_hash"):
        # Settings file: password is already stored as hash
        if submitted_hash == pw:
            session["authenticated"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("index"))
    else:
        # Env var: plain text password
        if submitted_hash == _hash_password(pw):
            session["authenticated"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("index"))
    return redirect(url_for("login_page") + "?error=1")

@app.route("/logout")
def logout():
    session.clear()
    if _auth_required():
        return redirect(url_for("login_page"))
    return redirect(url_for("index"))



# ─── Tautulli ─────────────────────────────────────────────────────────────────

def get_tautulli_url():
    return _cfg("tautulli_url", "TAUTULLI_URL", "").rstrip("/")

def get_tautulli_key():
    return _cfg("tautulli_api_key", "TAUTULLI_API_KEY", "")

def tautulli_configured():
    return bool(get_tautulli_url() and get_tautulli_key())

def fetch_tautulli_history():
    """Fetch full watch history from Tautulli. Returns dict keyed by (title_lower, year) -> {last_watched, play_count}."""
    if not tautulli_configured():
        return {}
    try:
        url = get_tautulli_url() + "/api/v2"
        # Fetch up to 10000 records to cover full library
        params = {
            "apikey": get_tautulli_key(),
            "cmd": "get_history",
            "length": 10000,
            "media_type": "movie,episode",
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        records = data.get("response", {}).get("data", {}).get("data", [])

        history = {}
        for rec in records:
            title = (rec.get("title") or "").lower().strip()
            # For episodes, use grandparent_title (show name)
            if rec.get("media_type") == "episode":
                title = (rec.get("grandparent_title") or rec.get("title") or "").lower().strip()
            year = rec.get("year") or rec.get("grandparent_year")
            watched_at = rec.get("date") or rec.get("started")  # unix timestamp

            key = title
            if key not in history:
                history[key] = {"last_watched": watched_at, "play_count": 0}
            history[key]["play_count"] += 1
            if watched_at and watched_at > history[key].get("last_watched", 0):
                history[key]["last_watched"] = watched_at

        logger.info(f"Tautulli: loaded history for {len(history)} titles")
        return history
    except Exception as e:
        logger.warning(f"Tautulli history fetch failed: {e}")
        return {}

# Module-level cache for Tautulli history (refreshed with media enrichment)
_tautulli_cache = {}
_tautulli_cache_ts = 0
TAUTULLI_CACHE_TTL = 300  # 5 minutes

def get_tautulli_history_cached():
    global _tautulli_cache, _tautulli_cache_ts
    if not tautulli_configured():
        return {}
    now = time.time()
    if now - _tautulli_cache_ts > TAUTULLI_CACHE_TTL:
        _tautulli_cache = fetch_tautulli_history()
        _tautulli_cache_ts = now
    return _tautulli_cache

def lookup_tautulli(title, history):
    """Look up a media title in the Tautulli history dict."""
    key = title.lower().strip()
    if key in history:
        return history[key]
    # Fuzzy: try without articles
    for k in history:
        if k.startswith(key) or key.startswith(k):
            return history[k]
    return None

@app.route("/api/status")
def status():
    results = {}
    try:
        r = requests.get(f"{get_radarr_url()}/api/v3/system/status",
                         headers={"X-Api-Key": get_radarr_key()}, timeout=5)
        results["radarr"] = {"ok": r.status_code == 200, "version": r.json().get("version", "?")}
    except:
        results["radarr"] = {"ok": False}
    try:
        r = requests.get(f"{get_sonarr_url()}/api/v3/system/status",
                         headers={"X-Api-Key": get_sonarr_key()}, timeout=5)
        results["sonarr"] = {"ok": r.status_code == 200, "version": r.json().get("version", "?")}
    except:
        results["sonarr"] = {"ok": False}
    results["qbittorrent"] = {"ok": qbit_login()}
    # Tautulli (optional)
    if tautulli_configured():
        try:
            r = requests.get(get_tautulli_url() + "/api/v2",
                           params={"apikey": get_tautulli_key(), "cmd": "get_server_info"},
                           timeout=5)
            results["tautulli"] = {"ok": r.status_code == 200, "configured": True}
        except Exception:
            results["tautulli"] = {"ok": False, "configured": True}
    else:
        results["tautulli"] = {"ok": False, "configured": False}
    return jsonify(results)


@app.route("/api/config-status")
def config_status():
    """Returns whether any configuration exists (env vars or settings file)."""
    has_radarr  = bool(get_radarr_url() and get_radarr_key())
    has_sonarr  = bool(get_sonarr_url() and get_sonarr_key())
    has_qbit    = bool(get_qbit_url())
    configured  = has_radarr or has_sonarr
    return jsonify({
        "configured": configured,
        "setup_required": not _setup_completed(),
        "has_radarr": has_radarr,
        "has_sonarr": has_sonarr,
        "has_qbit":   has_qbit,
    })


@app.route("/api/setup", methods=["POST"])
def run_setup():
    """Initial setup: save all config at once and mark setup as completed."""
    global _runtime_settings
    if _setup_completed():
        return jsonify({"success": False, "error": "Setup already completed"}), 400

    data = request.json or {}
    merged = {}

    # Auth
    username = data.get("removarr_username", "admin").strip()
    password = data.get("removarr_password", "").strip()
    if username:
        merged["removarr_username"] = username
    if password:
        merged["removarr_password_hash"] = _hash_password(password)

    # Services — encrypt sensitive fields
    for key in ["radarr_url", "radarr_api_key", "sonarr_url", "sonarr_api_key",
                "qbit_url", "qbit_username", "qbit_password",
                "tmdb_api_key", "seerr_url", "seerr_api_key",
                "tautulli_url", "tautulli_api_key"]:
        val = data.get(key, "").strip()
        if val:
            if key in ENCRYPTED_FIELDS:
                merged[key] = _encrypt(val)
            else:
                merged[key] = val

    merged["setup_completed"] = True

    if save_settings(merged):
        _runtime_settings = merged
        logger.info(f"Setup completed: {len(merged)} settings saved")
        try:
            qbit_login()
        except:
            pass
        # Auto-login the user who just set up
        session["authenticated"] = True
        session.permanent = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Could not save settings"}), 500


@app.route("/api/setup/test", methods=["POST"])
def setup_test_service():
    """Test a service during setup (before settings are saved)."""
    data = request.json or {}
    service = data.get("service", "")
    try:
        if service == "radarr":
            url = data.get("url", "").rstrip("/")
            key = data.get("api_key", "")
            r = requests.get(f"{url}/api/v3/system/status", headers={"X-Api-Key": key}, timeout=5)
            return jsonify({"ok": r.status_code == 200})
        elif service == "sonarr":
            url = data.get("url", "").rstrip("/")
            key = data.get("api_key", "")
            r = requests.get(f"{url}/api/v3/system/status", headers={"X-Api-Key": key}, timeout=5)
            return jsonify({"ok": r.status_code == 200})
        elif service == "qbit":
            url = data.get("url", "").rstrip("/")
            s = requests.Session()
            r = s.post(f"{url}/api/v2/auth/login",
                       data={"username": data.get("username", "admin"), "password": data.get("password", "")}, timeout=5)
            return jsonify({"ok": r.text.strip() == "Ok."})
        elif service == "tmdb":
            key = data.get("api_key", "").strip('"').strip("'")
            r = requests.get(
                "https://api.themoviedb.org/3/configuration",
                headers={"Authorization": f"Bearer {key}"} if len(key) > 40 else {},
                params={} if len(key) > 40 else {"api_key": key},
                timeout=5
            )
            return jsonify({"ok": r.status_code == 200})
        elif service == "seerr":
            url = data.get("url", "").rstrip("/")
            key = data.get("api_key", "")
            r = requests.get(f"{url}/api/v1/settings/public", headers={"X-Api-Key": key}, timeout=5)
            return jsonify({"ok": r.status_code == 200})
        elif service == "tautulli":
            url = data.get("url", "").rstrip("/")
            key = data.get("api_key", "")
            r = requests.get(f"{url}/api/v2",
                             params={"apikey": key, "cmd": "get_server_info"}, timeout=5)
            return jsonify({"ok": r.status_code == 200})
        else:
            return jsonify({"ok": False, "error": "Unknown service"})
    except requests.exceptions.ConnectionError:
        return jsonify({"ok": False, "error": "Connexion refusée"})
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "Timeout"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/version")
def get_version():
    return jsonify({"version": APP_VERSION})


@app.route("/api/locales")
def list_locales():
    """List available locale files."""
    import glob
    locales_dir = os.path.join(os.path.dirname(__file__), "locales")
    result = []
    for path in sorted(glob.glob(os.path.join(locales_dir, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("_meta", {})
            result.append({
                "lang":  meta.get("lang", os.path.basename(path).replace(".json", "")),
                "label": meta.get("label", os.path.basename(path).replace(".json", "")),
            })
        except Exception as e:
            logger.warning(f"Could not read locale {path}: {e}")
    return jsonify(result)

@app.route("/api/locales/<lang>")
def get_locale(lang):
    """Return a specific locale JSON file."""
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', lang):
        return jsonify({"error": "invalid lang"}), 400
    locales_dir = os.path.join(os.path.dirname(__file__), "locales")
    path = os.path.join(locales_dir, f"{lang}.json")
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        return app.response_class(f.read(), mimetype="application/json")


@app.route("/api/media")
def get_media():
    movies = get_radarr_movies()
    series = get_sonarr_series()
    logger.info(f"Loaded {len(movies)} movies, {len(series)} series")
    media_list = []

    for m in movies:
        if not m.get("hasFile"):
            continue
        native_titles = [t["title"] for t in m.get("alternateTitles", []) if t.get("title")]
        mid = m["id"]
        media_list.append({
            "id": mid, "type": "movie",
            "title": m["title"], "year": m.get("year"),
            "size": m.get("sizeOnDisk", 0),
            "added": m.get("added", ""),
            "poster": f"/api/poster/movie/{mid}" if poster_cached("movie", mid) else None,
            "genres": m.get("genres", []),
            "tmdb_id": m.get("tmdbId"),
            "native_titles": native_titles,
            "torrent_count": 0,
            "torrent_hashes": [],
        })

    for s in series:
        if not s.get("statistics", {}).get("episodeFileCount", 0):
            continue
        native_titles = [t["title"] for t in s.get("alternateTitles", []) if t.get("title")]
        sid = s["id"]
        media_list.append({
            "id": sid, "type": "series",
            "title": s["title"], "year": s.get("year"),
            "size": s.get("statistics", {}).get("sizeOnDisk", 0),
            "added": s.get("added", ""),
            "poster": f"/api/poster/series/{sid}" if poster_cached("series", sid) else None,
            "genres": s.get("genres", []),
            "tvdb_id": s.get("tvdbId"),
            "native_titles": native_titles,
            "seasons": s.get("statistics", {}).get("seasonCount", 0),
            "torrent_count": 0,
            "torrent_hashes": [],
        })

    media_list.sort(key=lambda x: x["title"].lower())
    return jsonify(media_list)

@app.route("/api/poster/<media_type>/<int:media_id>")
def serve_poster(media_type, media_id):
    """Serve cached poster JPG from disk."""
    from flask import send_file
    path = get_poster_path(media_type, media_id)
    if os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    return "", 404


@app.route("/api/media/enrich", methods=["POST"])
def enrich_media():
    t0 = time.time()
    items = request.json
    all_torrents = get_prepared_torrents_cached()
    word_index = get_word_index_cached()
    t_qbit = time.time() - t0

    t_tmdb_total = 0
    t_poster_total = 0
    t_match_total = 0
    tmdb_hits = 0
    tmdb_misses = 0
    poster_downloads = 0

    results = []
    for item in items:
        media_type = item.get("type")
        media_id   = item["id"]
        tmdb_id    = item.get("tmdb_id") or item.get("tvdb_id")

        t1 = time.time()
        cache_key = f"{media_type}-{tmdb_id}"
        was_cached = cache_key in _tmdb_cache
        tmdb_data  = fetch_tmdb_data(tmdb_id, media_type)
        t_tmdb = time.time() - t1
        t_tmdb_total += t_tmdb
        if was_cached:
            tmdb_hits += 1
        else:
            tmdb_misses += 1

        # Save poster to disk if we have a URL and it's not cached yet
        poster_url = None
        if tmdb_data.get("poster"):
            if not poster_cached(media_type, media_id):
                t2 = time.time()
                save_poster(media_type, media_id, tmdb_data["poster"])
                t_poster_total += time.time() - t2
                poster_downloads += 1
            if poster_cached(media_type, media_id):
                poster_url = f"/api/poster/{media_type}/{media_id}"

        # Merge native titles from Radarr/Sonarr + TMDB alt titles
        native_titles = item.get("native_titles") or []
        all_alt_titles = list(dict.fromkeys(native_titles + (tmdb_data["titles"] or [])))
        t3 = time.time()
        torrents = find_matching_torrents(
            item["title"],
            item.get("year") if media_type == "movie" else None,
            all_torrents,
            all_alt_titles,
            _word_index=word_index
        )
        t_match_total += time.time() - t3

        # Tautulli watch history
        tautulli_history = get_tautulli_history_cached()
        watch_info = lookup_tautulli(item["title"], tautulli_history)

        results.append({
            "id":             media_id,
            "type":           media_type,
            "poster":         poster_url,
            "torrent_count":  len(torrents),
            "torrent_hashes": [t["hash"] for t in torrents],
            "last_watched":   watch_info["last_watched"] if watch_info else None,
            "play_count":     watch_info["play_count"] if watch_info else 0,
        })

    total = time.time() - t0
    logger.info(f"Enrich {len(items)} items in {total:.1f}s — "
                f"qbit:{t_qbit:.2f}s tmdb:{t_tmdb_total:.2f}s({tmdb_hits}hit/{tmdb_misses}miss) "
                f"match:{t_match_total:.2f}s posters:{t_poster_total:.2f}s({poster_downloads}dl)")
    return jsonify(results)

def get_torrent_trackers(torrent_hash):
    """Fetch trackers for a single torrent from qBittorrent."""
    try:
        r = qbit_session.get(f"{get_qbit_url()}/api/v2/torrents/trackers",
                             params={"hash": torrent_hash}, timeout=5)
        if r.status_code == 403:
            qbit_login()
            r = qbit_session.get(f"{get_qbit_url()}/api/v2/torrents/trackers",
                                 params={"hash": torrent_hash}, timeout=5)
        trackers = r.json()
        # Filter real trackers (skip DHT/PeX/LSD)
        real = [t["url"] for t in trackers
                if t.get("url", "").startswith("http") and t.get("status") != 0]
        # Extract clean domain from tracker URL
        domains = []
        for url in real:
            m = re.search(r'https?://([^/:]+)', url)
            if m:
                domain = m.group(1)
                # Strip common subdomains
                parts = domain.split('.')
                if len(parts) >= 2:
                    domain = '.'.join(parts[-2:])
                if domain not in domains:
                    domains.append(domain)
        return domains
    except Exception as e:
        logger.warning(f"Failed to get trackers for {torrent_hash}: {e}")
        return []


@app.route("/api/torrents/preview", methods=["POST"])
def preview_torrents():
    try:
        data = request.json or {}
        title      = data.get("title")
        year       = data.get("year")
        media_type = data.get("type")
        tmdb_id    = data.get("tmdb_id")
        hashes     = set(data.get("torrent_hashes") or [])
        raw_torrents = get_qbit_torrents()
        prepared     = _prepare_torrents(raw_torrents)

        # Merge native titles (from Radarr/Sonarr) + TMDB alt titles
        tmdb_data     = fetch_tmdb_data(tmdb_id, media_type) if tmdb_id else {"poster": None, "titles": []}
        native_titles = data.get("native_titles") or []
        all_alt_titles = list(dict.fromkeys(native_titles + (tmdb_data["titles"] or [])))

        matched = find_matching_torrents(
            title,
            year if media_type == "movie" else None,
            prepared,
            all_alt_titles
        )
        matched_hashes = {t["hash"] for t in matched}

        # Union: matched + previously known hashes
        all_hashes = matched_hashes | hashes

        # Filter from raw (no _slug/_words pollution in JSON)
        torrents = [t for t in raw_torrents if t.get("hash") in all_hashes]

        result = []
        for t in torrents:
            trackers = get_torrent_trackers(t["hash"])
            result.append({
                "hash":     t["hash"],
                "name":     t["name"],
                "size":     t["size"],
                "state":    t["state"],
                "trackers": trackers,
            })
        return jsonify(result)
    except Exception as e:
        logger.exception(f"preview_torrents error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/torrents/delete-one", methods=["POST"])
def delete_one_torrent():
    data = request.json
    torrent_hash  = data.get("hash")
    delete_files  = data.get("delete_files", False)
    if not torrent_hash:
        return jsonify({"success": False, "error": "Missing hash"}), 400
    ok = delete_torrents([torrent_hash], delete_files=delete_files)
    return jsonify({"success": ok})

@app.route("/api/delete", methods=["POST"])
def delete_media():
    data = request.json
    media_id       = data.get("id")
    media_type     = data.get("type")
    torrent_hashes = data.get("torrent_hashes", [])
    delete_files   = data.get("delete_torrent_files", False)
    logger.info(f"DELETE request: {media_type} id={media_id} torrents={len(torrent_hashes)} delete_files={delete_files}")
    results = {"arr_deleted": False, "torrents_deleted": False, "errors": []}
    if media_type == "movie":
        results["arr_deleted"] = delete_radarr_movie(media_id, delete_files=True)
    elif media_type == "series":
        results["arr_deleted"] = delete_sonarr_series(media_id, delete_files=True)
    if not results["arr_deleted"]:
        results["errors"].append("Échec suppression dans Radarr/Sonarr")
    if torrent_hashes:
        results["torrents_deleted"] = delete_torrents(torrent_hashes, delete_files=delete_files)
        if not results["torrents_deleted"]:
            results["errors"].append("Échec suppression torrents qBittorrent")
    else:
        results["torrents_deleted"] = True
    results["success"] = results["arr_deleted"]
    # Clean up poster cache on delete
    if results["success"]:
        try:
            path = get_poster_path(media_type, media_id)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning(f"Could not remove poster cache: {e}")
    return jsonify(results)

@app.route("/api/stats")
def get_stats():
    movies   = [m for m in get_radarr_movies() if m.get("hasFile")]
    series   = [s for s in get_sonarr_series() if s.get("statistics", {}).get("episodeFileCount", 0)]
    torrents = get_qbit_torrents()
    total_size  = sum(m.get("sizeOnDisk", 0) for m in movies)
    total_size += sum(s.get("statistics", {}).get("sizeOnDisk", 0) for s in series)
    return jsonify({
        "movie_count": len(movies), "series_count": len(series),
        "torrent_count": len(torrents), "total_size": total_size,
    })

@app.route("/api/seerr/requests", methods=["POST"])
def get_seerr_requests():
    """Get Seerr requests for a media item."""
    data = request.json
    tmdb_id    = data.get("tmdb_id")
    media_type = data.get("type")
    if not tmdb_id:
        return jsonify([])
    reqs = seerr_get_requests(tmdb_id, media_type)
    return jsonify(reqs)


@app.route("/api/seerr/request/<int:request_id>/delete", methods=["POST"])
def delete_seerr_request(request_id):
    ok = seerr_delete_request(request_id)
    return jsonify({"success": ok})


@app.route("/api/seerr/status")
def seerr_status():
    """Check if Seerr is configured and reachable."""
    if not get_seerr_url() or not get_seerr_key():
        return jsonify({"configured": False, "ok": False})
    try:
        r = requests.get(f"{get_seerr_url()}/api/v1/settings/public",
                         headers={"X-Api-Key": get_seerr_key()}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return jsonify({
                "configured": True, "ok": True,
                "app_name": data.get("applicationTitle", "Seerr")
            })
        return jsonify({"configured": True, "ok": False})
    except:
        return jsonify({"configured": True, "ok": False})


@app.route("/api/seerr/debug/<int:tmdb_id>")
def seerr_debug(tmdb_id):
    """Debug endpoint: dump raw Seerr data for a tmdbId."""
    if not get_seerr_url() or not get_seerr_key():
        return jsonify({"error": "Seerr not configured"})
    headers = {"X-Api-Key": get_seerr_key()}
    out = {}
    try:
        # Raw /api/v1/request?filter=all first page
        r = requests.get(f"{get_seerr_url()}/api/v1/request",
                         params={"filter": "all", "take": 10, "skip": 0},
                         headers=headers, timeout=10)
        data = r.json()
        out["request_status"] = r.status_code
        out["pageInfo"] = data.get("pageInfo")
        # Show first 3 requests raw structure
        out["sample_requests"] = []
        for req in data.get("results", [])[:3]:
            out["sample_requests"].append({
                "id": req.get("id"),
                "type": req.get("type"),
                "status": req.get("status"),
                "media_keys": list((req.get("media") or {}).keys()),
                "media": req.get("media"),
            })
    except Exception as e:
        out["request_error"] = str(e)
    try:
        # Raw movie endpoint
        r2 = requests.get(f"{get_seerr_url()}/api/v1/movie/{tmdb_id}",
                          headers=headers, timeout=8)
        out["movie_status"] = r2.status_code
        if r2.status_code == 200:
            d = r2.json()
            mi = d.get("mediaInfo") or {}
            out["mediaInfo_keys"] = list(mi.keys())
            out["mediaInfo_id"] = mi.get("id")
            out["mediaInfo_tmdbId"] = mi.get("tmdbId")
            out["mediaInfo_requests_count"] = len(mi.get("requests", []))
            out["mediaInfo_requests"] = mi.get("requests", [])
    except Exception as e:
        out["movie_error"] = str(e)
    return jsonify(out)



@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Return current settings, always masking sensitive fields."""
    MASKED = "••••••••"  # Never expose actual key values
    def has_val(key, env_key):
        return bool(_cfg(key, env_key, ""))
    return jsonify({
        "radarr_url":     _cfg("radarr_url",     "RADARR_URL",     "http://localhost:7878"),
        "radarr_api_key": MASKED if has_val("radarr_api_key", "RADARR_API_KEY") else "",
        "sonarr_url":     _cfg("sonarr_url",     "SONARR_URL",     "http://localhost:8989"),
        "sonarr_api_key": MASKED if has_val("sonarr_api_key", "SONARR_API_KEY") else "",
        "qbit_url":       _cfg("qbit_url",       "QBIT_URL",       "http://localhost:8080"),
        "qbit_username":  _cfg("qbit_username",  "QBIT_USERNAME",  "admin"),
        "qbit_password":  MASKED if has_val("qbit_password",  "QBIT_PASSWORD")  else "",
        "tmdb_api_key":   MASKED if has_val("tmdb_api_key",   "TMDB_API_KEY")   else "",
        "seerr_url":      _cfg("seerr_url",      "SEERR_URL",      ""),
        "seerr_api_key":  MASKED if has_val("seerr_api_key",  "SEERR_API_KEY")  else "",
        "tautulli_url":     _cfg("tautulli_url",     "TAUTULLI_URL",     ""),
        "tautulli_api_key": MASKED if has_val("tautulli_api_key", "TAUTULLI_API_KEY") else "",
        "removarr_username": _get_auth_username(),
        "removarr_password": MASKED if _get_password() else "",
        "removarr_allowed_ips": _runtime_settings.get("removarr_allowed_ips") or os.environ.get("REMOVARR_ALLOWED_IPS", ""),
        "source": "file" if _runtime_settings else "env",
        "auth_enabled": _auth_required(),
    })


@app.route("/api/settings", methods=["POST"])
def update_settings():
    """Save settings to disk and reload runtime config."""
    global _runtime_settings
    data = request.json or {}

    SENSITIVE = ENCRYPTED_FIELDS | {"removarr_password"}
    # Merge: keep existing values for masked fields (never overwrite with placeholder)
    merged = dict(_runtime_settings)
    for key, val in data.items():
        val_str = str(val) if val is not None else ""
        if "••••" in val_str:
            continue  # Skip masked placeholder — keep existing value
        if key in SENSITIVE and not val_str:
            continue  # Skip empty sensitive fields — keep existing value
        # Encrypt API keys and passwords at rest
        if key in ENCRYPTED_FIELDS and val_str and "ENC:" not in val_str:
            merged[key] = _encrypt(val_str)
        else:
            merged[key] = val

    # Hash the password if it was changed (not masked, not empty)
    if "removarr_password" in data:
        pw_val = str(data["removarr_password"]) if data["removarr_password"] else ""
        if pw_val and "••••" not in pw_val:
            merged["removarr_password_hash"] = _hash_password(pw_val)
            merged.pop("removarr_password", None)  # Don't store plain text
        elif not pw_val:
            # Empty password = disable auth
            merged.pop("removarr_password_hash", None)
            merged.pop("removarr_password", None)

    if save_settings(merged):
        _runtime_settings = merged
        # Re-login to qBit with new credentials
        try:
            qbit_login()
        except:
            pass
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Could not save settings"}), 500


@app.route("/api/settings/test/<service>", methods=["POST"])
def test_service(service):
    """Test connectivity to a service with provided or current credentials."""
    data = request.json or {}

    def val(key, env_key, default=""):
        v = data.get(key, "")
        if v and "••••" not in v:
            return v
        return _cfg(key, env_key, default)

    try:
        if service == "radarr":
            url = val("radarr_url", "RADARR_URL", "http://localhost:7878").rstrip("/")
            key = val("radarr_api_key", "RADARR_API_KEY")
            r = requests.get(f"{url}/api/v3/system/status", headers={"X-Api-Key": key}, timeout=5)
            ok = r.status_code == 200
            name = r.json().get("appName", "Radarr") if ok else None
            return jsonify({"ok": ok, "name": name, "status": r.status_code})

        elif service == "sonarr":
            url = val("sonarr_url", "SONARR_URL", "http://localhost:8989").rstrip("/")
            key = val("sonarr_api_key", "SONARR_API_KEY")
            r = requests.get(f"{url}/api/v3/system/status", headers={"X-Api-Key": key}, timeout=5)
            ok = r.status_code == 200
            name = r.json().get("appName", "Sonarr") if ok else None
            return jsonify({"ok": ok, "name": name, "status": r.status_code})

        elif service == "qbit":
            url = val("qbit_url", "QBIT_URL", "http://localhost:8080").rstrip("/")
            user = val("qbit_username", "QBIT_USERNAME", "admin")
            pwd  = val("qbit_password", "QBIT_PASSWORD", "")
            s = requests.Session()
            r = s.post(f"{url}/api/v2/auth/login", data={"username": user, "password": pwd}, timeout=5)
            ok = r.text.strip() == "Ok."
            return jsonify({"ok": ok, "status": r.status_code})

        elif service == "tmdb":
            key = val("tmdb_api_key", "TMDB_API_KEY").strip('"').strip("'")
            r = requests.get(
                "https://api.themoviedb.org/3/configuration",
                headers={"Authorization": f"Bearer {key}"} if len(key) > 40 else {},
                params={} if len(key) > 40 else {"api_key": key},
                timeout=5
            )
            ok = r.status_code == 200
            return jsonify({"ok": ok, "status": r.status_code})

        elif service == "seerr":
            url = val("seerr_url", "SEERR_URL", "").rstrip("/")
            key = val("seerr_api_key", "SEERR_API_KEY")
            if not url:
                return jsonify({"ok": False, "error": "URL non configurée"})
            r = requests.get(f"{url}/api/v1/settings/main", headers={"X-Api-Key": key}, timeout=5)
            ok = r.status_code == 200
            name = r.json().get("applicationTitle", "Overseerr") if ok else None
            return jsonify({"ok": ok, "name": name, "status": r.status_code})

        elif service == "tautulli":
            url = val("tautulli_url", "TAUTULLI_URL", "").rstrip("/")
            key = val("tautulli_api_key", "TAUTULLI_API_KEY")
            if not url:
                return jsonify({"ok": False, "error": "URL non configurée"})
            r = requests.get(f"{url}/api/v2",
                             params={"apikey": key, "cmd": "get_server_info"},
                             timeout=5)
            ok = r.status_code == 200
            server_name = None
            if ok:
                try:
                    server_name = r.json().get("response", {}).get("data", {}).get("pms_name")
                except Exception:
                    pass
            return jsonify({"ok": ok, "name": server_name, "status": r.status_code})

        else:
            return jsonify({"ok": False, "error": "Service inconnu"}), 400

    except requests.exceptions.ConnectionError:
        return jsonify({"ok": False, "error": "Connexion refusée"})
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "Timeout"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/settings")
def settings_page():
    from flask import render_template
    return render_template("settings.html")


@app.route("/api/settings/reset", methods=["POST"])
def reset_settings():
    """Delete settings.json and revert to env vars."""
    global _runtime_settings
    try:
        if os.path.exists(SETTINGS_FILE):
            os.remove(SETTINGS_FILE)
        _runtime_settings = {}
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/cache/clear", methods=["POST"])
def clear_tmdb_cache():
    """Clear TMDB cache to force re-fetch of all posters and titles."""
    global _tmdb_cache
    with _tmdb_lock:
        _tmdb_cache = {}
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except:
        pass
    # Also clear poster files
    import shutil
    try:
        if os.path.exists(POSTERS_DIR):
            shutil.rmtree(POSTERS_DIR)
    except:
        pass
    return jsonify({"success": True, "message": "Cache TMDB et posters effacés"})


if __name__ == "__main__":
    qbit_login()
    app.run(host="0.0.0.0", port=5000, debug=False)
