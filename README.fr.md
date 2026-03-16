# Removarr

**Removarr** est une interface web auto-hébergée pour nettoyer votre bibliothèque média — supprimer films et séries de Radarr/Sonarr, retirer tous les torrents associés de qBittorrent (cross-seeds inclus), et libérer l'espace disque. Le tout en un clic.

---

## Fonctionnalités

### Cœur
- **Suppression en cascade** : un clic supprime le média de Radarr/Sonarr, retire tous les torrents associés de qBittorrent (cross-seeds inclus), et efface les fichiers du disque
- Détection des cross-seeds par matching de titres normalisé Unicode (gère les accents : Yoroï ↔ Yoroi)
- Panneau torrent par média : inspecter, retirer individuellement, ou supprimer entièrement
- Sélection multiple avec barre d'action groupée
- Vue grille (taille ajustable) + Vue liste

### Intégrations
- **Radarr** / **Sonarr** — gestion de la bibliothèque + suppression des fichiers
- **qBittorrent** — suppression des torrents + fichiers
- **TMDB** — posters HD + matching des titres alternatifs
- **Seerr / Overseerr** — nettoyage automatique des demandes à la suppression
- **Tautulli** — badges d'historique de lecture (jamais vu, dernier visionnage, nombre de lectures)

### Performance
- Scan complet de 700 items en **~9 secondes** (index inversé par mots, cache multi-niveaux)
- Métadonnées TMDB en cache sur disque, données qBittorrent en cache mémoire
- Enrichissement en arrière-plan avec widget de progression en temps réel

### Interface
- Assistant de configuration au premier lancement (aucun fichier de config nécessaire)
- Recherche, filtres (Films / Séries / Masquer sans torrent / Jamais vu), tri multi-critères
- Multilingue (FR / EN + extensible), détection automatique du navigateur
- Responsive mobile
- Indicateurs de statut des services avec vérification de connectivité

### Sécurité
- **Assistant de configuration** crée le compte admin au premier lancement
- Identifiant + mot de passe configurables depuis les Réglages (stocké en hash SHA-256)
- Toutes les clés API **chiffrées au repos** (Fernet/AES-128-CBC) dans `settings.json`
- Whitelist IP (support CIDR)
- Tous les champs sensibles masqués avec bouton œil dans l'interface

---

## Démarrage rapide

```bash
# 1. Cloner
git clone https://github.com/Matt17000/removarr.git
cd removarr

# 2. Lancer
docker compose up -d

# 3. Ouvrir
# → http://<votre-ip>:5999
# L'assistant de configuration vous guide
```

C'est tout. Aucune variable d'environnement nécessaire — l'assistant s'occupe de tout.

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
      - removarr-data:/data    # settings, cache TMDB, posters
    environment:
      - SECRET_KEY=votre_chaine_aleatoire   # optionnel mais recommandé — openssl rand -hex 32

volumes:
  removarr-data:
```

> **Note** : `SECRET_KEY` sert à chiffrer les clés API au repos et signer les sessions. Sans cette variable, une clé aléatoire est générée à chaque redémarrage (ce qui invalide les sessions et les clés chiffrées). Définissez-la une fois.

### Premier lancement

1. Ouvrir `http://<votre-ip>:5999`
2. L'assistant de configuration apparaît en 3 étapes :
   - **Étape 1** — Créer le compte admin (identifiant + mot de passe)
   - **Étape 2** — Configurer Radarr, Sonarr, qBittorrent (avec test de connexion)
   - **Étape 3** — Services optionnels : TMDB (posters), Seerr (demandes), Tautulli (historique)
3. Terminé — vous êtes connecté et la bibliothèque se charge

### Avancé : variables d'environnement

Tous les réglages peuvent aussi être passés en variables d'environnement (utile pour l'automatisation). L'assistant / la page Réglages prend la priorité.

| Variable | Description |
|---|---|
| `RADARR_URL` / `RADARR_API_KEY` | Connexion Radarr |
| `SONARR_URL` / `SONARR_API_KEY` | Connexion Sonarr |
| `QBIT_URL` / `QBIT_USERNAME` / `QBIT_PASSWORD` | Connexion qBittorrent |
| `TMDB_API_KEY` | Clé API TMDB ou Bearer Token v4 |
| `SEERR_URL` / `SEERR_API_KEY` | Connexion Seerr/Overseerr |
| `TAUTULLI_URL` / `TAUTULLI_API_KEY` | Connexion Tautulli |
| `REMOVARR_PASSWORD` | Mot de passe (fallback si non configuré via l'UI) |
| `REMOVARR_ALLOWED_IPS` | Whitelist IP, ex : `192.168.0.0/24,10.0.0.1` |
| `SECRET_KEY` | Clé de chiffrement + sessions |
| `CACHE_FILE` | Chemin du cache TMDB (défaut : `/data/tmdb_cache.json`) |

---

## Sécurité

### Comment les identifiants sont stockés

| Donnée | Méthode | Réversible |
|---|---|---|
| Mot de passe Removarr | Hash SHA-256 | Non (comparaison uniquement) |
| Clés API et mots de passe services | Chiffrement Fernet (AES-128-CBC) | Oui (déchiffré à l'exécution) |

Toutes les données sensibles dans `/data/settings.json` sont hashées ou chiffrées. Rien n'est stocké en clair.

La clé de chiffrement est dérivée de `SECRET_KEY`. Si vous la changez ou la perdez, re-saisissez vos clés API dans les Réglages.

### Authentification

Configurée pendant le setup ou dans Réglages → 🔒 Sécurité :
- **Identifiant** (défaut : `admin`)
- **Mot de passe** (laisser vide pour désactiver l'auth)
- **Whitelist IP** (plages CIDR, séparées par virgule)

---

## Ajouter une langue

1. Copier `template.json` → `locales/de.json`
2. Renseigner `_meta.lang` et `_meta.label`
3. Traduire toutes les valeurs (les clés doivent rester identiques)
4. Copier dans le container : `docker cp locales/de.json removarr:/app/locales/de.json`
5. La langue apparaît automatiquement dans Réglages → Langue

---

## Données persistantes

Monter un volume sur `/data` :

| Chemin | Contenu |
|---|---|
| `/data/settings.json` | Configuration complète (clés API chiffrées, auth, URLs) |
| `/data/tmdb_cache.json` | Cache des métadonnées TMDB (titres, URLs posters) |
| `/data/posters/` | Images des posters téléchargées (JPG) |

---

## Stack technique

- **Backend** : Python 3.12 / Flask / Gunicorn (1 worker + 4 threads)
- **Frontend** : HTML/CSS/JS vanilla — zéro dépendance JS externe
- **Chiffrement** : cryptography (Fernet)
- **Polices** : Inter + JetBrains Mono (Google Fonts)
- **Port** : 5000 interne (mappé sur 5999 par défaut)

---

## API

| Endpoint | Méthode | Description |
|---|---|---|
| `/api/version` | GET | `{"version": "x.y.z"}` |
| `/api/status` | GET | Connectivité des services |
| `/api/config-status` | GET | État du setup |
| `/api/media` | GET | Bibliothèque complète Radarr/Sonarr |
| `/api/media/enrich` | POST | Enrichissement par batch (posters, torrents, Tautulli) |
| `/api/delete` | POST | Suppression en cascade (média + torrents + fichiers) |
| `/api/settings` | GET/POST | Lecture/écriture de la configuration |
| `/api/setup` | POST | Configuration initiale (premier lancement uniquement) |
| `/api/setup/test` | POST | Test de connectivité pendant le setup |
| `/api/seerr/requests` | POST | Demandes Seerr pour un média |

---

## Changelog

### v1.5.1 (2026-03-16)
- Assistant de configuration : favicon sur toutes les pages, boutons test sur tous les services, avertissement TMDB

### v1.5.0 (2026-03-16)
- Clés API chiffrées au repos (Fernet/AES-128-CBC)
- Rétrocompatible avec les anciens settings en clair

### v1.4.0 (2026-03-15)
- Assistant de configuration au premier lancement (3 étapes)
- Identifiant/mot de passe configurables depuis l'interface
- Bouton œil sur tous les champs sensibles
- Page de connexion avec identifiant + mot de passe
- Filtre "Masquer sans torrent"
- Header/toolbar sticky restaurés

### v1.3.1 (2026-03-15)
- Cache TMDB chargé au démarrage (688 appels HTTP économisés)
- Index inversé pour le matching torrents (~2.5 min → ~9s pour 688 items)
- Normalisation Unicode pour le matching des titres accentués (Yoroï ↔ Yoroi)
- Les fichiers sont maintenant réellement supprimés du disque
- Réécriture complète du responsive mobile
- Toutes les chaînes françaises codées en dur remplacées par l'i18n
- Widget de progression du scan en temps réel
- Corrections du cache de session

---

## Avertissement

Ce projet a été développé principalement par vibe coding assisté par IA (Claude / Anthropic). Il a été conçu pour un usage personnel sur un réseau domestique.

**⚠️ Important :**

- **Aucun audit de sécurité** n'a été réalisé. N'exposez pas cette application sur internet.
- C'est un projet personnel — fourni tel quel, sans garantie, sans support officiel, et sans engagement sur les demandes de fonctionnalités ou corrections de bugs.
- Vous êtes libre d'utiliser, forker et adapter le projet pour vos besoins, mais vous le faites **sous votre propre responsabilité**.
- Il y a probablement des bugs. Je fais de mon mieux, mais c'est un projet hobby, pas un logiciel de production.

Si ça vous est utile, tant mieux ! Gardez juste en tête ce que vous exécutez.

---

## Licence

MIT
