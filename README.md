# Convertisseur MP3 MoD

Bibliothèque audio locale avec conversion automatique des trackers (.mod/.xm/.it/.s3m) en MP3 et site statique de lecture.

## Architecture

- `convert.py` — scan + conversion + index (Python stdlib + ffmpeg)
- `index.html` / `style.css` / `app.js` — site statique
- `musiques/` — sources audio (arborescence libre)
- `images/` — images bandeau défilant
- `audio/` — MP3 convertis (généré)
- `thumbs/` — miniatures waveform (généré)
- `data/audio_index.json` + `audio_index.js` — index (généré)

## Prérequis

**ffmpeg** + **ffprobe** dans le PATH, idéalement build avec `libopenmpt` pour les trackers.

- Windows : `winget install ffmpeg` ou build officiel sur https://ffmpeg.org
- Vérifier support tracker : `ffmpeg -formats | findstr -i openmpt`

## Utilisation

### 1. Remplir les dossiers
- Déposer `.mod` / `.xm` / `.it` / `.s3m` / `.mp3` dans `musiques/` (sous-dossiers OK)
- Déposer images bandeau dans `images/`

### 2. Lancer l'analyse
```
python convert.py
```
Options :
- `--force` : reconstruit tout, ignore le cache

### 3. Ouvrir le site
Double-cliquer sur `index.html`. Aucun serveur requis.

## Fonctionnalités

- Scan récursif `musiques/`
- Conversion `.mod` → `.wav` → `.mp3` (44.1 kHz stéréo 192 kbps) via ffmpeg+libopenmpt
- Miniatures waveform générées par `showwavespic`
- Cache incrémental (hash + mtime + size) — seuls les fichiers changés sont retraités
- Nettoyage auto des sorties orphelines
- Navigation tiroirs/sous-tiroirs + fil d'Ariane
- Lecteur : play/pause, seek, volume, précédent/suivant, playlist auto (siblings)
- Préchargement piste suivante
- Recherche, tri nom/durée/taille
- Thème sombre/clair (persisté)
- Bandeau images défilement infini

## Incrémental

`data/hash_cache.json` stocke hash + mtime + size par fichier source. Run ultérieurs :
- Fichier inchangé → skip
- Fichier modifié → re-conversion
- Fichier supprimé → MP3 + waveform orphelins effacés
