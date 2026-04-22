"""
SMYLE PLAY — Configuration centralisée
Toutes les valeurs sensibles viennent des variables d'environnement.
En local, copie .env.example → .env et remplis les valeurs.
"""

import os
from dotenv import load_dotenv

# Charge .env si présent (développement local)
load_dotenv()


class Config:
    # ── Serveur ────────────────────────────────────────────────────────────
    PORT  = int(os.environ.get('PORT', 8080))
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # ── Base de données PostgreSQL ─────────────────────────────────────────
    # Ex: postgresql://user:password@host:5432/smyle_play
    # Vide = mode sans DB (données en localStorage seulement)
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///smyle_local.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # ── Cloudflare R2 ──────────────────────────────────────────────────────
    # URL publique du bucket (ex: https://pub-xxx.r2.dev)
    # Vide = mode local (fichiers servis depuis le disque)
    CLOUD_AUDIO_BASE_URL = os.environ.get('CLOUD_AUDIO_BASE_URL', '').rstrip('/')
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID', '')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY', '')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY', '')
    R2_BUCKET     = os.environ.get('R2_BUCKET', 'smyle-play-audio')

    # ── Playlists ──────────────────────────────────────────────────────────
    # 'folder'    = nom du dossier sur le disque local (Mac dev)
    # 'r2_folder' = nom du dossier dans Cloudflare R2 (production)
    PLAYLISTS = [
        {'key': 'sunset-lover',  'label': 'SUNSET LOVER',  'folder': 'SUNSET LOVER',   'r2_folder': 'SUNSET LOVER',  'theme': 'sunset-lover'},
        {'key': 'jungle-osmose', 'label': 'JUNGLE OSMOSE', 'folder': ' JUNGLE OSMOSE', 'r2_folder': 'JUNGLE OSMOSE', 'theme': 'jungle-osmose'},
        {'key': 'night-city',    'label': 'NIGHT CITY',    'folder': 'NIGHT CITY',     'r2_folder': 'NIGHT CITY',    'theme': 'night-city'},
        {'key': 'hit-mix',       'label': 'HIT MIX',       'folder': 'HIT MIX',        'r2_folder': 'HIT MIX',       'theme': 'hit-mix'},
    ]
    AUDIO_EXTENSIONS = ('.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a')

    # ── CORS (Railway/Render autorisent les requêtes depuis le front) ──────
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')

    # ── Admin (bonus crédits, opérations internes) ─────────────────────────
    # Token secret pour les endpoints /api/credits/grant et futurs /admin/*.
    # Vide en dev = endpoint inactif. À définir en prod via Railway Variables.
    ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # SECRET_KEY résolue explicitement au boot via get_config() — si absente
    # en prod, on crashe immédiatement avec un message actionnable plutôt que
    # de laisser l'app tourner avec None puis exploser à la 1ère signature
    # de session.
    SECRET_KEY = os.environ.get('SECRET_KEY')


# Sélection auto selon l'env
def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        # Garde-fou prod : SECRET_KEY doit être définie et non triviale.
        # Sans ça, Flask signerait les sessions avec None → crash obscur à
        # la première requête. Mieux vaut refuser de démarrer.
        if not ProductionConfig.SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY is missing in production environment. "
                "Set it in Railway → Variables before deploying. "
                "Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        if ProductionConfig.SECRET_KEY == 'dev-secret-change-in-production':
            raise RuntimeError(
                "SECRET_KEY is still set to the development default value. "
                "Rotate it immediately in Railway → Variables."
            )
        return ProductionConfig
    return DevelopmentConfig
