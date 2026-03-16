# Removarr

**Removarr** is a self-hosted web UI to clean up your media library — delete movies and series from Radarr/Sonarr, remove all associated torrents from qBittorrent (including cross-seeds), and free up disk space. All from a single click.

> **⚠️ Important — please read before using:**
>
> - This project was built primarily using **AI-assisted development** (vibe-coded with Claude)
> - **No security audit** has been performed
> - **Do NOT expose this to the internet** — local network use only
> - Provided **as-is**, no warranty — use at your own risk
> - This is a personal project, not a product — **no support, no feature requests**
>
> I built this for my own homelab. If it's useful to you, feel free to use it, but you're responsible for how you run it. There are probably bugs. I do my best.

---

## Features

### Core
- **Cascade delete**: one click removes the media from Radarr/Sonarr, deletes all matching torrents in qBittorrent (cross-seeds included), and removes files from disk
- Cross-seed detection via Unicode-normalized title matching (handles accents: Yoroï ↔ Yoroi)
- Torrent panel per media: inspect, remove individual torrents, or full delete
- Multi-select with bulk action bar
- Grid view (adjustable card size) + List view

### Integrations
- **Radarr** / **Sonarr** — library management + file deletion
- **qBittorrent** — torrent + file deletion
- **TMDB** — HD posters + alternate title matching
- **Seerr / Overseerr** — automatic request cleanup on delete
- **Tautulli** — watch history badges (never watched, last watched, play count)

### Performance
- Full library scan of 700 items in **~9 seconds** (inverted word index, multi-level caching)
- TMDB metadata cached on disk, qBittorrent data cached in memory
- Background enrichment with real-time progress widget

### UI/UX
- Setup wizard on first launch (no config files needed)
- Search, filters (Movies / Series / Hide no torrent / Never watched), multi-criteria sort
- Multilingual (FR / EN + extensible), auto-detects browser language
- Mobile responsive
- Service status indicators with live connectivity checks

### Security
- **Setup wizard** creates admin account on first launch
- Username + password configurable from Settings (stored as SHA-256 hash)
- All API keys **encrypted at rest** (Fernet/AES-128-CBC) in `settings.json`
- IP whitelist (CIDR support)
- All sensitive fields masked with eye toggle in the UI

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/Matt17000/removarr.git
cd removarr

# 2. Start
docker compose up -d

# 3. Open
# → http://<your-ip>:5999
# The setup wizard will guide you through configuration
```

That's it. No environment variables needed — the setup wizard handles everything.

---

## Installation

### Docker Compose

```yaml
services:
  removarr:
    build: .
    container_name: removarr
    restart: unless-stopped
    ports:
      - "5999:5000"
    volumes:
      - removarr-data:/data    # settings, TMDB cache, posters
    environment:
      - SECRET_KEY=your_random_string   # optional but recommended — openssl rand -hex 32

volumes:
  removarr-data:
```

> **Note**: `SECRET_KEY` is used to encrypt API keys at rest and sign sessions. If not set, a random one is generated on each restart (which invalidates sessions and encrypted keys). Set it once and keep it.

### First launch

1. Open `http://<your-ip>:5999`
2. The setup wizard appears with 3 steps:
   - **Step 1** — Create admin account (username + password)
   - **Step 2** — Configure Radarr, Sonarr, qBittorrent (with live connection test)
   - **Step 3** — Optional services: TMDB (posters), Seerr (requests), Tautulli (watch history)
3. Done — you're logged in and the library loads

### Advanced: environment variables

All settings can also be passed as env vars (useful for automation). The setup wizard / Settings page takes priority over env vars.

| Variable | Description |
|---|---|
| `RADARR_URL` / `RADARR_API_KEY` | Radarr connection |
| `SONARR_URL` / `SONARR_API_KEY` | Sonarr connection |
| `QBIT_URL` / `QBIT_USERNAME` / `QBIT_PASSWORD` | qBittorrent connection |
| `TMDB_API_KEY` | TMDB API key or Bearer v4 token |
| `SEERR_URL` / `SEERR_API_KEY` | Seerr/Overseerr connection |
| `TAUTULLI_URL` / `TAUTULLI_API_KEY` | Tautulli connection |
| `REMOVARR_PASSWORD` | Login password (fallback if not set via UI) |
| `REMOVARR_ALLOWED_IPS` | IP whitelist, e.g. `192.168.0.0/24,10.0.0.1` |
| `SECRET_KEY` | Encryption + session key |
| `CACHE_FILE` | TMDB cache path (default: `/data/tmdb_cache.json`) |

---

## Security

### How credentials are stored

| Data | Method | Reversible |
|---|---|---|
| Removarr password | SHA-256 hash | No (compare only) |
| API keys & service passwords | Fernet encryption (AES-128-CBC) | Yes (decrypted at runtime) |

All sensitive data in `/data/settings.json` is either hashed or encrypted. Nothing is stored in plain text.

The encryption key is derived from `SECRET_KEY`. If you change or lose it, re-enter your API keys in Settings.

### Authentication

Configured during setup or in Settings → 🔒 Security:
- **Username** (default: `admin`)
- **Password** (leave empty to disable auth)
- **IP whitelist** (CIDR ranges, comma-separated)

### All sensitive fields in the UI

Every API key and password field uses `type="password"` with an eye toggle to show/hide. The Settings page never returns actual values — only `••••••••` placeholders.

---

## Adding a language

1. Copy `template.json` → `locales/de.json`
2. Set `_meta.lang` and `_meta.label` (e.g. `"de"` and `"Deutsch"`)
3. Translate all values (keys must stay identical)
4. Copy into the container: `docker cp locales/de.json removarr:/app/locales/de.json`
5. The language appears automatically in Settings → Language

---

## Persistent data

Mount a volume on `/data`:

| Path | Content |
|---|---|
| `/data/settings.json` | All configuration (encrypted API keys, auth, service URLs) |
| `/data/tmdb_cache.json` | TMDB metadata cache (titles, poster URLs) |
| `/data/posters/` | Downloaded poster images (JPG) |

---

## Tech stack

- **Backend**: Python 3.12 / Flask / Gunicorn (1 worker + 4 threads)
- **Frontend**: Vanilla HTML/CSS/JS — zero external JS dependencies
- **Encryption**: cryptography (Fernet)
- **Fonts**: Inter + JetBrains Mono (Google Fonts)
- **Port**: 5000 internal (mapped to 5999 by default)

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/version` | GET | `{"version": "x.y.z"}` |
| `/api/status` | GET | Service connectivity |
| `/api/config-status` | GET | Setup state |
| `/api/media` | GET | Full library from Radarr/Sonarr |
| `/api/media/enrich` | POST | Batch enrichment (posters, torrents, Tautulli) |
| `/api/delete` | POST | Cascade delete (media + torrents + files) |
| `/api/settings` | GET/POST | Read/write configuration |
| `/api/setup` | POST | Initial setup (first launch only) |
| `/api/setup/test` | POST | Test service connectivity during setup |
| `/api/seerr/requests` | POST | Seerr requests for a media |

---

## Changelog

### v1.5.1 (2026-03-16)
- Setup wizard: favicon on all pages, test buttons on all services (TMDB/Seerr/Tautulli), TMDB warning banner

### v1.5.0 (2026-03-16)
- API keys encrypted at rest (Fernet/AES-128-CBC)
- Backward compatible with legacy plain-text settings

### v1.4.0 (2026-03-15)
- Setup wizard on first launch (3-step guided configuration)
- Username/password configurable from Settings UI
- Eye toggle on all sensitive fields
- Login page with username + password
- "Hide no torrent" filter
- Sticky header/toolbar restored

### v1.3.1 (2026-03-15)
- TMDB cache loaded at startup (was never called — 688 HTTP calls saved)
- Inverted word index for torrent matching (~2.5 min → ~9s for 688 items)
- Unicode normalization for accented title matching (Yoroï ↔ Yoroi)
- Files now actually deleted from disk on cascade delete
- Complete mobile responsive rewrite
- All hardcoded French strings replaced with i18n
- Scan progress widget with real-time updates
- Session cache fixes (no more ghost entries after delete)

---

## License

MIT
