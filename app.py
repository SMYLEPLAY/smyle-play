"""
SMYLE PLAY — Application Flask principale
─────────────────────────────────────────
• Sert les fichiers statiques (index.html, style.css, script.js)
• Sert les fichiers audio en mode local (dev)
• Expose l'API JSON : GET /api/tracks, GET /api/playlists
• Expose l'API auth : POST /api/auth/register, /api/auth/login, /api/auth/logout
• Expose l'API feedback : POST /api/feedback
• Expose l'API play counts : POST /api/plays/<track_id>

Usage local :
    python3 app.py

Usage production (Railway / Render) :
    gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
"""

import os
import logging
from flask import Flask, jsonify, send_from_directory, request, session

from config import get_config
from scanner import scan_playlists

# ── App Factory ───────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s : %(message)s',
)
logger = logging.getLogger(__name__)


def create_app(config_class=None):
    app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
    app.config.from_object(config_class or get_config())

    # ── Base de données ────────────────────────────────────────────────────
    db_enabled = bool(app.config.get('DATABASE_URL'))
    if db_enabled:
        from models import db
        db.init_app(app)
        with app.app_context():
            db.create_all()
            logger.info('PostgreSQL connecté — tables créées si absentes')
    else:
        logger.info('Mode sans base de données (localStorage côté client)')

    # ── Client R2 (optionnel) ──────────────────────────────────────────────
    r2_client = None
    if (app.config.get('R2_ACCOUNT_ID')
            and app.config.get('R2_ACCESS_KEY')
            and app.config.get('R2_SECRET_KEY')):
        try:
            import boto3
            r2_client = boto3.client(
                's3',
                endpoint_url=f"https://{app.config['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                aws_access_key_id=app.config['R2_ACCESS_KEY'],
                aws_secret_access_key=app.config['R2_SECRET_KEY'],
                region_name='auto',
            )
            logger.info('Cloudflare R2 connecté')
        except ImportError:
            logger.warning('boto3 non installé — R2 désactivé')

    app.r2_client = r2_client

    # ── Routes statiques ──────────────────────────────────────────────────

    @app.route('/')
    def index():
        return send_from_directory(BASE_DIR, 'index.html')

    # ── API Playlists / Tracks ────────────────────────────────────────────

    @app.route('/api/tracks')
    @app.route('/api/playlists')
    def get_tracks():
        data = scan_playlists(
            base_dir         = BASE_DIR,
            cloud_base_url   = app.config.get('CLOUD_AUDIO_BASE_URL', ''),
            playlists_config = app.config.get('PLAYLISTS'),
            audio_extensions = app.config.get('AUDIO_EXTENSIONS'),
            r2_client        = app.r2_client,
            r2_bucket        = app.config.get('R2_BUCKET', ''),
        )
        resp = jsonify(data)
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp

    # ── API Auth (DB uniquement) ──────────────────────────────────────────

    @app.route('/api/auth/register', methods=['POST'])
    def register():
        if not db_enabled:
            return jsonify({'error': 'Auth DB non configurée'}), 503
        from models import db, User
        data = request.get_json() or {}
        name, email, password = data.get('name','').strip(), data.get('email','').strip(), data.get('password','')
        if not all([name, email, password]):
            return jsonify({'error': 'Champs manquants'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Mot de passe trop court (min 6)'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email déjà utilisé'}), 409
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        return jsonify({'ok': True, 'user': user.to_dict()}), 201

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        if not db_enabled:
            return jsonify({'error': 'Auth DB non configurée'}), 503
        from models import User
        data = request.get_json() or {}
        email, password = data.get('email','').strip(), data.get('password','')
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({'error': 'Email ou mot de passe incorrect'}), 401
        session['user_id'] = user.id
        return jsonify({'ok': True, 'user': user.to_dict()})

    @app.route('/api/auth/logout', methods=['POST'])
    def logout():
        session.pop('user_id', None)
        return jsonify({'ok': True})

    @app.route('/api/auth/me')
    def me():
        if not db_enabled or 'user_id' not in session:
            return jsonify({'user': None})
        from models import User
        user = User.query.get(session['user_id'])
        return jsonify({'user': user.to_dict() if user else None})

    # ── API Play counts ───────────────────────────────────────────────────

    @app.route('/api/plays/<track_id>', methods=['POST'])
    def increment_play(track_id):
        if not db_enabled:
            return jsonify({'ok': True, 'count': 1})   # localStorage côté client
        from models import db, PlayCount
        user_id = session.get('user_id')
        pc = PlayCount.query.filter_by(track_id=track_id, user_id=user_id).first()
        if pc:
            pc.count += 1
        else:
            pc = PlayCount(track_id=track_id, user_id=user_id, count=1)
            db.session.add(pc)
        db.session.commit()
        return jsonify({'ok': True, 'count': pc.count})

    # ── API Feedback / Contact ────────────────────────────────────────────

    @app.route('/api/feedback', methods=['POST'])
    def submit_feedback():
        data = request.get_json() or {}
        name    = data.get('name', '').strip()
        email   = data.get('email', '').strip()
        ftype   = data.get('type', 'Autre')
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Message vide'}), 400

        if db_enabled:
            from models import db, Feedback
            fb = Feedback(
                user_id = session.get('user_id'),
                name    = name,
                email   = email,
                type    = ftype,
                message = message,
            )
            db.session.add(fb)
            db.session.commit()
            logger.info(f'Feedback #{fb.id} reçu ({ftype})')

        return jsonify({'ok': True})

    # ── Healthcheck ────────────────────────────────────────────────────────

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'db': db_enabled, 'r2': r2_client is not None})

    # ── Fichiers statiques / audio (catch-all) ─────────────────────────────

    @app.errorhandler(404)
    def not_found(e):
        # Retourne index.html pour les routes SPA (single page app)
        return send_from_directory(BASE_DIR, 'index.html')

    return app


# ── Point d'entrée ────────────────────────────────────────────────────────────

app = create_app()

if __name__ == '__main__':
    port  = app.config['PORT']
    debug = app.config['DEBUG']
    print(f'\n  ╔══════════════════════════════════════╗')
    print(f'  ║  SMYLE PLAY → http://localhost:{port}  ║')
    print(f'  ╚══════════════════════════════════════╝\n')
    app.run(host='0.0.0.0', port=port, debug=debug)
