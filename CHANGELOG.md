# Changelog

All notable changes to Removarr are documented here.

---

## v1.5.3 (2026-03-20)

**Features**
- Sort by "Recently added" / "Oldest added" — uses the date the media was added to Radarr/Sonarr
- Banner logo on GitHub README with centered trash icon

**Fixes**
- Trash icon properly centered in banner SVG

## v1.5.2 (2026-03-17)

**Security**
- `/api/setup/*` endpoints now locked after setup completion (prevented potential SSRF via test endpoint)
- Security audit against Huntarr vulnerabilities checklist — all points addressed

## v1.5.1 (2026-03-16)

**Fixes**
- Setup wizard: favicon on all pages, test buttons on all services (TMDB/Seerr/Tautulli), TMDB warning banner

## v1.5.0 (2026-03-16)

**Security**
- All API keys and service passwords encrypted at rest (Fernet/AES-128-CBC)
- Backward compatible with legacy plain-text settings

## v1.4.0 (2026-03-15)

**Features**
- Setup wizard on first launch (3-step guided configuration)
- Username/password configurable from Settings UI
- Eye toggle on all sensitive fields (API keys, passwords)
- Login page with username + password
- "Hide no torrent" filter in toolbar
- IP whitelist configurable from Settings page

**Fixes**
- Sticky header/toolbar restored (broken by overflow-x fix)

## v1.3.1 (2026-03-15)

**Performance**
- TMDB cache loaded at startup (was never called — 688 HTTP calls saved)
- Inverted word index for torrent matching (~2.5 min → ~9s for 688 items)
- qBittorrent torrent list cached 30s across enrichment batches (14 HTTP calls → 1)
- Batch size increased from 20 to 50 items

**Bug fixes**
- Files not deleted from disk on cascade delete (`delete_torrent_files` hardcoded to `false`)
- Unicode normalization for accented title matching (Yoroï ↔ Yoroi)
- TMDB cache filter discarded entries with empty title lists
- Refresh button didn't force reload
- Variable shadowing: `t` as parameter masked i18n `t()` function in 4 places
- Tautulli test button returned "unknown service"
- Gunicorn 2 workers → 1 worker + 4 threads (shared state issues)
- Session cache: ghost entries after delete, re-scan on navigation

**UI/UX**
- Card click opens torrent panel, checkbox (bottom-right) toggles selection
- Scan progress widget with real-time progress bar
- All hardcoded French strings replaced with i18n keys (~20 strings)
- Better error messages (timeout vs network error distinction)
- Fresh data on every page load (cache only for settings↔home navigation)
- Version number in settings page and logo tooltip

**Mobile**
- Complete responsive rewrite for screens < 768px
- Compact header, icon-only buttons, touch event handlers

**Infrastructure**
- No-cache HTTP headers on HTML responses
- Request and timing logs on enrichment and delete endpoints
- Version constant `APP_VERSION`, exposed via `/api/version`
