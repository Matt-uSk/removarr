# Removarr

**Removarr** est une interface web auto-hébergée pour supprimer des médias depuis Radarr/Sonarr et retirer automatiquement tous les torrents associés dans qBittorrent (cross-seeds inclus) — avec suppression des fichiers sur le disque.

---

## Fonctionnalités

- Bibliothèque complète (films Radarr + séries Sonarr) avec posters, taille, année, compteur de torrents
- **Suppression en cascade** : Radarr/Sonarr (fichiers inclus) → qBittorrent (tous torrents + cross-seeds + fichiers disque)
- Détection des cross-seeds par matching de torrents avec normalisation Unicode des titres alternatifs (TMDB + Radarr/Sonarr natifs)
- Panneau torrent par média : voir, retirer individuellement, ou supprimer entièrement avec fichiers
- Intégration Seerr/Overseerr : suppression automatique des demandes associées
- Intégration Tautulli : badges d'historique de lecture ("Jamais vu", date du dernier visionnage, nombre de lectures)
- Sélection multiple avec barre d'action pour suppression groupée
- Recherche, filtres (Films / Séries), tri multi-critères (titre, taille, année, torrents, date de visionnage)
- Vue grille avec taille de cartes ajustable + vue liste
- Widget de progression du scan en temps réel
- Cache posters local (`/data/posters/`) + cache TMDB (`/data/tmdb_cache.json`)
- Enrichissement haute performance : index inversé par mots pour le matching torrents, cache multi-niveaux
- Interface multilingue (FR / EN + extensible), détection automatique du navigateur
- Page de réglages avec test de connexion par service (Radarr, Sonarr, qBittorrent, TMDB, Seerr, Tautulli)
- Indicateurs de statut en temps réel (pill services avec dropdown)
- Authentification par mot de passe + whitelist IP (optionnel)
- Design responsive mobile
- Numéro de version affiché dans les réglages et en tooltip sur le logo

---

## Prérequis

- Docker + Docker Compose
- Au moins **Radarr** ou **Sonarr** configuré
- **qBittorrent** avec l'API Web activée
- *(Optionnel)* Compte TMDB pour les posters HD et le matching des titres alternatifs
- *(Optionnel)* Seerr / Overseerr pour la gestion des demandes
- *(Optionnel)* Tautulli pour l'historique de lecture

---

## Installation

### 1. Structure des fichiers

```
removarr/
├── app.py
├── Dockerfile
├── docker-compose.yml
├── docker-compose.example.yml
├── requirements.txt
├── template.json          ← modèle vide pour les traductions
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

### 2. Configurer le `docker-compose.yml`

```yaml
environment:
  - CACHE_FILE=/data/tmdb_cache.json
  - RADARR_URL=http://192.168.1.10:7878
  - RADARR_API_KEY=votre_cle_radarr
  - SONARR_URL=http://192.168.1.10:8989
  - SONARR_API_KEY=votre_cle_sonarr
  - QBIT_URL=http://192.168.1.10:8080
  - QBIT_USERNAME=admin
  - QBIT_PASSWORD=votre_mot_de_passe_qbit
  - TMDB_API_KEY=votre_cle_tmdb
  - SEERR_URL=http://192.168.1.10:5055
  - SEERR_API_KEY=votre_cle_seerr
  - TAUTULLI_URL=http://192.168.1.10:8181
  - TAUTULLI_API_KEY=votre_cle_tautulli
```

### 3. Lancer

```bash
docker compose up -d
```

Accéder à l'interface : `http://<votre-ip>:5999`

---

## Configuration

La configuration peut se faire de deux manières :

1. **Variables d'environnement** dans `docker-compose.yml` (recommandé au départ)
2. **Page Réglages** (`/settings`) — les valeurs sont sauvegardées dans `/data/settings.json` et prennent le dessus

### Variables d'environnement disponibles

| Variable | Description | Requis |
|---|---|---|
| `RADARR_URL` | URL de Radarr | Non* |
| `RADARR_API_KEY` | Clé API Radarr | Non* |
| `SONARR_URL` | URL de Sonarr | Non* |
| `SONARR_API_KEY` | Clé API Sonarr | Non* |
| `QBIT_URL` | URL de la WebUI qBittorrent | Non |
| `QBIT_USERNAME` | Utilisateur qBittorrent | Non |
| `QBIT_PASSWORD` | Mot de passe qBittorrent | Non |
| `TMDB_API_KEY` | Clé API TMDB ou Bearer Token v4 | Non |
| `SEERR_URL` | URL de Seerr/Overseerr | Non |
| `SEERR_API_KEY` | Clé API Seerr/Overseerr | Non |
| `TAUTULLI_URL` | URL de Tautulli | Non |
| `TAUTULLI_API_KEY` | Clé API Tautulli | Non |
| `CACHE_FILE` | Chemin du cache TMDB (défaut : `/data/tmdb_cache.json`) | Non |

\*Au moins Radarr ou Sonarr est requis.

---

## Sécurité

Removarr stocke les clés API de toute votre stack *arr. Activez l'authentification si l'instance est accessible sur un réseau partagé.

### Authentification par mot de passe

```yaml
environment:
  - REMOVARR_PASSWORD=votre_mot_de_passe
  - SECRET_KEY=une_longue_chaine_aleatoire   # openssl rand -hex 32
```

### Whitelist IP

```yaml
environment:
  - REMOVARR_ALLOWED_IPS=192.168.0.0/24,10.0.0.1
```

### Variables de sécurité

| Variable | Description | Défaut |
|---|---|---|
| `REMOVARR_PASSWORD` | Mot de passe. Auth désactivée si vide. | *(désactivé)* |
| `REMOVARR_ALLOWED_IPS` | IPs/CIDRs séparés par virgule. Toutes si vide. | *(toutes)* |
| `SECRET_KEY` | Clé de signature des sessions. Auto-générée si non définie. | *(auto)* |

---

## Ajouter une langue

1. Copier `template.json` → `locales/de.json`
2. Renseigner `_meta.lang` et `_meta.label`
3. Traduire toutes les valeurs (les clés doivent rester identiques)
4. Copier dans le container : `docker cp locales/de.json removarr:/app/locales/de.json`
5. La langue apparaît automatiquement dans Réglages → Langue

---

## Données persistantes

| Chemin | Contenu |
|---|---|
| `/data/settings.json` | Configuration sauvegardée depuis l'interface |
| `/data/tmdb_cache.json` | Cache des métadonnées TMDB |
| `/data/posters/` | Cache des posters (fichiers JPG) |

---

## Stack technique

- **Backend** : Python 3.12 / Flask / Gunicorn (1 worker + 4 threads, timeout 180s)
- **Frontend** : HTML/CSS/JS vanilla — aucune dépendance JS externe
- **Polices** : Inter + JetBrains Mono (Google Fonts)
- **Port interne** : 5000 (mappé sur 5999 par défaut)

---

## API

| Endpoint | Méthode | Description |
|---|---|---|
| `/api/version` | GET | Retourne `{"version": "x.y.z"}` |
| `/api/status` | GET | Statut de connectivité des services |
| `/api/media` | GET | Liste complète des médias Radarr/Sonarr |
| `/api/media/enrich` | POST | Enrichissement par batch (posters, torrents, Tautulli) |
| `/api/delete` | POST | Suppression média + torrents + fichiers |
| `/api/settings` | GET/POST | Lecture/écriture des réglages |
| `/api/seerr/requests` | POST | Récupérer les demandes Seerr pour un média |

---

## Changelog

### v1.5.0 (2025-03-16)

**Sécurité**
- Toutes les clés API et mots de passe de services sont maintenant **chiffrés au repos** dans `settings.json` via chiffrement symétrique Fernet (AES-128-CBC), dérivé du `SECRET_KEY`
- Rétrocompatible : les anciennes valeurs non chiffrées sont lues normalement et chiffrées au prochain enregistrement
- Hash SHA-256 pour le mot de passe Removarr, chiffrement Fernet pour les clés API — chaque donnée utilise la méthode appropriée
- Si le `SECRET_KEY` change, les champs chiffrés deviennent illisibles (warning dans les logs) — les re-saisir dans les Réglages

### v1.4.0 (2025-03-15)

**Sécurité & Authentification**
- Nom d'utilisateur + mot de passe configurables depuis la page Réglages (plus besoin de variables d'environnement)
- Mot de passe stocké en hash SHA-256 dans `/data/settings.json` (jamais en clair)
- Whitelist IP configurable depuis les Réglages
- Rétrocompatible : les variables `REMOVARR_PASSWORD` et `REMOVARR_ALLOWED_IPS` fonctionnent toujours en fallback
- La page de connexion a maintenant un champ utilisateur + mot de passe

**Interface**
- Tous les champs sensibles (clés API, mots de passe) utilisent `type="password"` avec un bouton œil pour afficher/masquer
- Nouvelle section 🔒 Sécurité dans les Réglages avec utilisateur, mot de passe, whitelist IP
- Badge de statut auth (✅ activé / indication pour configurer) dans les réglages
- Filtre "Masquer sans torrent" dans la toolbar pour cacher les médias sans torrent associé
- Header + toolbar sticky restaurés (cassés par le fix overflow-x)
- La page Réglages se recharge après sauvegarde pour refléter l'état de l'auth

### v1.3.1 (2025-03-15)

**Performance**
- Le cache TMDB est maintenant chargé au démarrage (était défini mais jamais appelé — causait ~5s/batch d'appels HTTP inutiles)
- Index inversé par mots pour le matching torrents : recherche O(1) au lieu de scan O(n) par titre
- Liste des torrents qBittorrent cachée 30s entre les batches d'enrichissement (14 appels HTTP → 1)
- Taille des batches augmentée de 20 à 50 items
- Scan complet de la bibliothèque (688 items) : **~2.5 minutes → ~9 secondes**

**Corrections de bugs**
- Les fichiers n'étaient pas supprimés du disque (`delete_torrent_files` était codé en dur à `false`)
- Les caractères accentués empêchaient le matching de torrents (ex: Yoroï vs Yoroi) — ajout de la normalisation Unicode NFD
- Le filtre du cache TMDB jetait les entrées avec des listes de titres vides
- Le bouton Actualiser ne forçait pas le rechargement
- Shadowing de variable : `t` utilisé comme paramètre dans `.map(t =>)` masquait la fonction i18n `t()` à 4 endroits
- Le bouton Test de Tautulli retournait "service inconnu"
- 2 workers Gunicorn causaient des incohérences d'état partagé — passé à 1 worker + 4 threads
- Le cache de session causait un re-scan à chaque navigation et des entrées fantômes après suppression
- Les badges de visionnage ne se mettaient pas à jour visuellement après le scan

**Interface**
- Clic sur la carte ouvre le panneau torrent, la coche (en bas à droite) gère la sélection
- Widget de progression du scan avec barre de progression, compteur, titre en cours
- Toutes les chaînes françaises codées en dur remplacées par des clés i18n
- Messages d'erreur améliorés avec distinction timeout / erreur réseau
- Cache invalidé après chaque suppression
- Données fraîches à chaque chargement de page (cache uniquement pour la navigation réglages↔accueil)
- Numéro de version dans les réglages et en tooltip sur le logo

**Mobile**
- Réécriture complète du responsive pour écrans < 768px
- Header compact avec boutons icône uniquement
- Dropdown services en position fixe (pas de débordement)
- Handler tactile pour fermeture du dropdown

**Infrastructure**
- Headers HTTP no-cache sur les réponses HTML
- Logs de requêtes et de timing sur les endpoints d'enrichissement et de suppression
- Constante `APP_VERSION`, exposée via `/api/version`

---

## Licence

MIT
