# Removarr

**Removarr** is a self-hosted web UI to delete media from Radarr/Sonarr and automatically remove all associated qBittorrent torrents (including cross-seeds) — with files deleted from disk.

---

## Features

- Full library view (Radarr movies + Sonarr series) with posters, size, year, torrent count
- **Cascade delete**: Radarr/Sonarr (with files) → qBittorrent (all torrents + cross-seeds + files on disk)
- Cross-seed detection via torrent matching with Unicode-normalized alternate titles (TMDB + Radarr/Sonarr native)
- Torrent panel per media: view, remove individually, or full delete with files
- Seerr/Overseerr integration: automatic deletion of associated requests
- Tautulli integration: watch history badges ("Never watched", last watched date, play count)
- Multi-select with action bar for bulk deletion
- Search, filters (Movies / Series), multi-criteria sort (title, size, year, torrents, watch date)
- Grid view with adjustable card size + List view
- Real-time scan progress widget with per-batch timing
- Local poster cache (`/data/posters/`) + TMDB metadata cache (`/data/tmdb_cache.json`)
- High-performance enrichment: inverted word index for torrent matching, multi-level caching
- Multilingual UI (FR / EN + extensible), automatic browser language detection
- Settings page with per-service connection test (Radarr, Sonarr, qBittorrent, TMDB, Seerr, Tautulli)
- Real-time status indicators (services pill with dropdown)
- Optional password auth + IP whitelist
- Mobile responsive design
- Version display in settings page and logo tooltip

---

## Requirements

- Docker + Docker Compose
- At least **Radarr** or **Sonarr** configured
- **qBittorrent** with Web API enabled (for torrent deletion)
- *(Optional)* TMDB account for high-quality posters and alternate title matching
- *(Optional)* Seerr / Overseerr for request management
- *(Optional)* Tautulli for watch history integration

---

## Installation

### 1. File structure

```
removarr/
├── app.py
├── Dockerfile
├── docker-compose.yml
├── docker-compose.example.yml
├── requirements.txt
├── template.json          ← blank locale template for translations
├── README.md
├── README.fr.md
├── locales/
│   ├── fr.json
│   └── en.json
└── templates/
    ├── index.html
    ├── settings.html
    └── login.html
```

### 2. Configure `docker-compose.yml`

```yaml
environment:
  - CACHE_FILE=/data/tmdb_cache.json
  - RADARR_URL=http://192.168.1.10:7878
  - RADARR_API_KEY=your_radarr_api_key
  - SONARR_URL=http://192.168.1.10:8989
  - SONARR_API_KEY=your_sonarr_api_key
  - QBIT_URL=http://192.168.1.10:8080
  - QBIT_USERNAME=admin
  - QBIT_PASSWORD=your_qbit_password
  - TMDB_API_KEY=your_tmdb_key
  - SEERR_URL=http://192.168.1.10:5055
  - SEERR_API_KEY=your_seerr_api_key
  - TAUTULLI_URL=http://192.168.1.10:8181
  - TAUTULLI_API_KEY=your_tautulli_api_key
```

### 3. Start

```bash
docker compose up -d
```

Access the UI at: `http://<your-ip>:5999`

---

## Configuration

Settings can be managed two ways:

1. **Environment variables** in `docker-compose.yml` (recommended for initial setup)
2. **Settings page** (`/settings`) — values are saved to `/data/settings.json` and take priority over env vars

### Available environment variables

| Variable | Description | Required |
|---|---|---|
| `RADARR_URL` | Radarr URL (e.g. `http://192.168.1.10:7878`) | No* |
| `RADARR_API_KEY` | Radarr API key | No* |
| `SONARR_URL` | Sonarr URL (e.g. `http://192.168.1.10:8989`) | No* |
| `SONARR_API_KEY` | Sonarr API key | No* |
| `QBIT_URL` | qBittorrent WebUI URL | No |
| `QBIT_USERNAME` | qBittorrent username | No |
| `QBIT_PASSWORD` | qBittorrent password | No |
| `TMDB_API_KEY` | TMDB API key or Bearer v4 JWT token | No |
| `SEERR_URL` | Seerr/Overseerr URL | No |
| `SEERR_API_KEY` | Seerr/Overseerr API key | No |
| `TAUTULLI_URL` | Tautulli URL | No |
| `TAUTULLI_API_KEY` | Tautulli API key | No |
| `CACHE_FILE` | TMDB cache path (default: `/data/tmdb_cache.json`) | No |

\*At least Radarr or Sonarr is required.

---

## Security

Removarr stores API keys for your entire *arr stack. It is strongly recommended to enable authentication if your instance is accessible on a shared network.

### Password authentication

Set `REMOVARR_PASSWORD` to enable a login page.

```yaml
environment:
  - REMOVARR_PASSWORD=your_secure_password
  - SECRET_KEY=a_long_random_string   # generate with: openssl rand -hex 32
```

### IP whitelist

```yaml
environment:
  - REMOVARR_ALLOWED_IPS=192.168.0.0/24,10.0.0.1
```

### Security variables

| Variable | Description | Default |
|---|---|---|
| `REMOVARR_PASSWORD` | Login password. Auth disabled if empty. | *(disabled)* |
| `REMOVARR_ALLOWED_IPS` | Comma-separated IPs/CIDRs. All allowed if empty. | *(all)* |
| `SECRET_KEY` | Session signing key. Auto-generated if not set. | *(auto)* |

---

## Adding a language

1. Copy `template.json` → `locales/de.json`
2. Set `_meta.lang` and `_meta.label`
3. Translate all values (keys must stay identical)
4. Copy into the container: `docker cp locales/de.json removarr:/app/locales/de.json`
5. The language appears automatically in Settings → Language

---

## Persistent data

| Path | Content |
|---|---|
| `/data/settings.json` | Configuration saved from the UI |
| `/data/tmdb_cache.json` | TMDB metadata cache |
| `/data/posters/` | Poster cache (JPG files) |

---

## Tech stack

- **Backend**: Python 3.12 / Flask / Gunicorn (1 worker + 4 threads, timeout 180s)
- **Frontend**: Vanilla HTML/CSS/JS — no external JS dependencies
- **Fonts**: Inter + JetBrains Mono (Google Fonts)
- **Internal port**: 5000 (mapped to 5999 by default)

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/version` | GET | Returns `{"version": "x.y.z"}` |
| `/api/status` | GET | Service connectivity status |
| `/api/media` | GET | Full media list from Radarr/Sonarr |
| `/api/media/enrich` | POST | Batch enrichment (posters, torrents, Tautulli) |
| `/api/delete` | POST | Delete media + torrents + files |
| `/api/settings` | GET/POST | Read/write settings |
| `/api/seerr/requests` | POST | Get Seerr requests for a media |

---

## Changelog

### v1.5.0 (2025-03-16)

**Security**
- All API keys and service passwords are now **encrypted at rest** in `settings.json` using Fernet symmetric encryption (AES-128-CBC), derived from `SECRET_KEY`
- Backward compatible: legacy unencrypted values are read normally and encrypted on next save
- Password hash (SHA-256) for Removarr login, encryption (Fernet) for API keys — each uses the appropriate method
- If `SECRET_KEY` changes, encrypted fields become unreadable (logged as warning) — re-enter them in Settings

### v1.4.0 (2025-03-15)

**Security & Authentication**
- Username + password configurable from the Settings page (no more env-var-only setup)
- Password stored as SHA-256 hash in `/data/settings.json` (never in plain text)
- IP whitelist configurable from Settings page
- Backward compatible: `REMOVARR_PASSWORD` and `REMOVARR_ALLOWED_IPS` env vars still work as fallback
- Login page now has username + password fields

**UI/UX**
- All secret fields (API keys, passwords) use `type="password"` with eye toggle button to show/hide
- New 🔒 Security section in Settings with username, password, IP whitelist
- Auth status badge (✅ enabled / hint to configure) in settings
- "Hide no torrent" filter toggle in toolbar to hide media without associated torrents
- Sticky header + toolbar restored (was broken by overflow-x fix)
- Settings page reloads after save to reflect auth state changes

### v1.3.1 (2025-03-15)

**Performance**
- TMDB cache now loads at startup (was defined but never called — caused ~5s/batch of unnecessary HTTP calls)
- Inverted word index for torrent matching: O(1) candidate lookup instead of O(n) full scan per title
- qBittorrent torrent list cached for 30s across enrichment batches (14 HTTP calls → 1)
- Batch size increased from 20 to 50 items
- Full library scan (688 items): **~2.5 minutes → ~9 seconds**

**Bug fixes**
- Files not deleted from disk on deletion (`delete_torrent_files` was hardcoded to `false`)
- Accented characters caused torrent mismatch (e.g. Yoroï vs Yoroi) — added Unicode NFD normalization
- TMDB cache filter discarded entries with empty title lists
- Refresh button didn't force reload
- Variable shadowing: `t` used as parameter name masked the i18n `t()` function in 4 places
- Tautulli test button returned "unknown service"
- Gunicorn 2 workers caused shared state issues — switched to 1 worker + 4 threads
- Session cache caused re-scan on page navigation and ghost entries after delete
- Watch badges not updating after scan completion

**UI/UX**
- Card click opens torrent panel, checkbox (bottom-right) toggles selection
- Scan progress widget with real-time progress bar, batch counter, current title
- All hardcoded French strings replaced with i18n keys
- Better error messages with timeout vs network error distinction
- Cache invalidated after every delete
- Fresh data on every page load (cache only for settings↔home navigation)
- Version number in settings page and logo tooltip

**Mobile**
- Complete responsive rewrite for screens < 768px
- Compact header with icon-only buttons
- Services dropdown fixed position (no viewport overflow)
- Touch event handler for dropdown close

**Infrastructure**
- No-cache HTTP headers on HTML responses
- Request and timing logs on enrichment and delete endpoints
- Version constant `APP_VERSION`, exposed via `/api/version`

---

## License

MIT
