# SMYLE PLAY — Guide complet : GitHub + Cloudflare R2 + Railway

---

## ÉTAPE 1 — Créer ton compte GitHub

1. Va sur **https://github.com** → clique **Sign up**
2. Entre ton email, crée un mot de passe, choisis un nom d'utilisateur (ex: `tomwatt`)
3. Vérifie ton email et connecte-toi

---

## ÉTAPE 2 — Créer le repository GitHub

1. Sur GitHub, clique **"New"** (bouton vert en haut à gauche)
2. Nom du repo : `smyle-play`
3. Description : `Lecteur de playlists IA — Suno × WATT`
4. Visibilité : **Private** (pour garder le code chez toi)
5. Clique **"Create repository"**

---

## ÉTAPE 3 — Pousser le code depuis ton Mac

Ouvre **Terminal** sur ton Mac et lance ces commandes :

```bash
# Aller dans le dossier du projet
cd "IA SUNO PLAYLIST DEVELOPPEMENT "

# Initialiser Git
git init
git add .
git commit -m "SMYLE PLAY — version initiale"

# Connecter à GitHub (remplace 'tonusername' par ton vrai nom d'utilisateur)
git remote add origin https://github.com/tonusername/smyle-play.git
git branch -M main
git push -u origin main
```

> 💡 GitHub te demandera ton email + mot de passe (ou un token) la première fois.

---

## ÉTAPE 4 — Créer le compte Cloudflare R2 (audio)

1. Va sur **https://dash.cloudflare.com** → crée un compte gratuit
2. Dans le menu gauche → **R2 Object Storage** → **Create bucket**
3. Nom du bucket : `smyle-play-audio`
4. Région : automatique
5. Clique **Create bucket**

### Rendre le bucket public (pour que l'audio soit streamable)

1. Clique sur ton bucket `smyle-play-audio`
2. Onglet **Settings** → **Public access**
3. Active **"Allow Access"** → confirme
4. Note l'URL publique : `https://pub-XXXXXXXX.r2.dev` → tu en auras besoin plus tard

### Créer les credentials API

1. Dans R2 → **Manage R2 API Tokens** → **Create API Token**
2. Permissions : **Object Read & Write**
3. Scope : **Specific bucket** → `smyle-play-audio`
4. Clique **Create API Token**
5. Copie et sauvegarde (une seule fois visible !) :
   - **Access Key ID**
   - **Secret Access Key**
   - **Account ID** (visible en haut de la page R2)

---

## ÉTAPE 5 — Uploader tes fichiers audio vers R2

Sur ton Mac, depuis le dossier du projet :

```bash
# Installer boto3 (une seule fois)
pip3 install boto3

# Configurer les credentials (remplace par tes vraies valeurs)
export R2_ACCOUNT_ID="ton_account_id"
export R2_ACCESS_KEY="ton_access_key_id"
export R2_SECRET_KEY="ton_secret_access_key"
export R2_BUCKET="smyle-play-audio"

# Lancer l'upload (peut prendre 10-30min selon ta connexion)
python3 upload_to_r2.py
```

À la fin, le script affiche l'URL à utiliser, par exemple :
```
CLOUD_AUDIO_BASE_URL = https://smyle-play-audio.XXXXX.r2.dev
```

---

## ÉTAPE 6 — Déployer sur Railway

1. Va sur **https://railway.app** → **Login with GitHub**
2. Clique **"New Project"** → **"Deploy from GitHub repo"**
3. Sélectionne `smyle-play`
4. Railway détecte `Procfile` automatiquement et démarre le déploiement

### Ajouter la variable d'environnement

1. Dans ton projet Railway → onglet **Variables**
2. Clique **"New Variable"**
3. Ajoute :
   - **Key** : `CLOUD_AUDIO_BASE_URL`
   - **Value** : l'URL R2 de l'étape 5 (ex: `https://pub-xxx.r2.dev`)
4. Railway redémarre automatiquement

### Obtenir l'URL publique

1. Railway → **Settings** → **Domains** → **Generate Domain**
2. Ton app est accessible sur `https://smyle-play-xxxx.up.railway.app` 🎉

---

## Architecture finale

```
Mac local :
  IA SUNO PLAYLIST DEVELOPPEMENT /
  ├── server.py          ← Python stdlib, mode local + cloud
  ├── index.html         ← Interface SMYLE PLAY
  ├── style.css          ← Design PLUG WATT
  ├── script.js          ← Lecteur audio + My Mix
  ├── upload_to_r2.py    ← Script d'upload des fichiers audio
  ├── SUNSET LOVER/      ← WAV (local seulement, exclus de Git)
  ├──  JUNGLE OSMOSE/    ← WAV (local seulement)
  ├── NIGHT CITY/        ← WAV (local seulement)
  └── HIT MIX/           ← WAV (local seulement)

GitHub (smyle-play) :
  → Code uniquement (pas les fichiers audio)
  → Historique de toutes les versions

Cloudflare R2 (smyle-play-audio) :
  → Tous les fichiers WAV hébergés
  → Accès public sans frais de bande passante

Railway :
  → App Python déployée depuis GitHub
  → Variable CLOUD_AUDIO_BASE_URL → pointe vers R2
  → URL publique pour partager
```

---

## En local (sans Internet)

Double-clique sur **DEMARRER SMYLE PLAY.command** → l'app s'ouvre dans le navigateur.
Les fichiers WAV locaux sont utilisés directement (qualité maximale).

---

## Ajouter un nouveau morceau

1. Dépose le fichier WAV dans le bon dossier (ex: `NIGHT CITY/`)
2. **En local** : l'app le détecte au prochain clic (scan automatique)
3. **En ligne** : relance `python3 upload_to_r2.py` pour uploader le nouveau fichier

---

## Mettre à jour le code (workflow Git)

```bash
# Faire les modifications dans les fichiers...

# Sauvegarder dans Git
git add .
git commit -m "Description de ce que j'ai changé"
git push

# Railway redéploie automatiquement depuis GitHub ✓
```
