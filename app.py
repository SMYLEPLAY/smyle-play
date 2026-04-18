"""
SMYLE PLAY — Application Flask principale
─────────────────────────────────────────
• Sert les fichiers statiques (index.html, style.css, script.js)
• API playlists officielles : GET /api/tracks, GET /api/playlists
• API auth : POST /api/auth/register, /api/auth/login, /api/auth/logout
• API WATT artistes : GET/POST /api/watt/profile, /api/artists, /api/tracks/recent
• API WATT tracks : GET/POST /api/watt/tracks, DELETE /api/watt/tracks/<id>
• API collabs : POST /api/collabs, GET /api/collabs/inbox
• API plays : POST /api/plays/<id>, POST /api/watt/plays/<id>

Usage local :
    python3 app.py

Usage production (Railway) :
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
        from models import db, ensure_schema
        db.init_app(app)
        with app.app_context():
            db.create_all()
            logger.info('PostgreSQL connecté — tables créées si absentes')
        ensure_schema(app)   # additive migrations (credits, prompts, etc.)
    else:
        # Mode dev SQLite (fallback pratique pour travailler en local)
        from models import db, ensure_schema
        db.init_app(app)
        with app.app_context():
            db.create_all()
            logger.info('SQLite local activé — pas de DATABASE_URL')
        ensure_schema(app)
        db_enabled = True   # SQLite est utilisable

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

    @app.route('/watt')
    def watt_page():
        return send_from_directory(BASE_DIR, 'watt.html')

    @app.route('/dashboard')
    def dashboard_page():
        return send_from_directory(BASE_DIR, 'dashboard.html')

    @app.route('/artiste/<slug>')
    def artiste_page(slug):
        return send_from_directory(BASE_DIR, 'artiste.html')

    # ── API Playlists / Tracks officiels ──────────────────────────────────

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

    # ── API Auth ──────────────────────────────────────────────────────────

    @app.route('/api/auth/register', methods=['POST'])
    def register():
        from models import db, User
        data = request.get_json() or {}
        name, email, password = (data.get('name','').strip(),
                                 data.get('email','').strip(),
                                 data.get('password',''))
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
        if 'user_id' not in session:
            return jsonify({'user': None})
        from models import User
        user = User.query.get(session['user_id'])
        return jsonify({'user': user.to_dict() if user else None})

    # ── API Credits (Phase 1) ─────────────────────────────────────────────

    @app.route('/api/credits', methods=['GET'])
    def get_credits():
        """Retourne le solde de crédits de l'utilisateur connecté."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401
        from models import User
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'Utilisateur introuvable'}), 404
        return jsonify({'credits': int(user.credits or 0)})

    @app.route('/api/credits/grant', methods=['POST'])
    def grant_credits():
        """
        Crédite un utilisateur (opération admin / test).

        Protégé par le header X-Admin-Token qui doit matcher ADMIN_TOKEN
        dans la config. Si ADMIN_TOKEN n'est pas défini → endpoint désactivé.

        Body JSON :
            { "email": "user@example.com", "amount": 100 }
        """
        expected = app.config.get('ADMIN_TOKEN', '')
        if not expected:
            return jsonify({'error': 'Endpoint désactivé (ADMIN_TOKEN non configuré)'}), 503

        token = request.headers.get('X-Admin-Token', '')
        if token != expected:
            return jsonify({'error': 'Non autorisé'}), 403

        from models import db, User
        data = request.get_json() or {}
        email  = (data.get('email') or '').strip()
        try:
            amount = int(data.get('amount', 0))
        except (TypeError, ValueError):
            return jsonify({'error': "Le champ 'amount' doit être un entier"}), 400

        if not email or amount <= 0:
            return jsonify({'error': 'email et amount > 0 requis'}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'Utilisateur introuvable'}), 404

        user.credits = int(user.credits or 0) + amount
        db.session.commit()
        logger.info(f'[CREDITS] +{amount} à {email} → solde {user.credits}')
        return jsonify({'ok': True, 'credits': user.credits})

    # ── API WATT — Profil artiste (GET = mon profil, POST = sauvegarder) ──

    @app.route('/api/watt/profile', methods=['GET', 'POST'])
    def watt_profile():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import db, Artist

        if request.method == 'POST':
            data = request.get_json() or {}
            artist_name = data.get('artistName', '').strip()
            if not artist_name:
                return jsonify({'error': "Nom d'artiste requis"}), 400

            artist = Artist.query.filter_by(user_id=user_id).first()
            if not artist:
                slug = Artist.make_slug(artist_name)
                artist = Artist(user_id=user_id, slug=slug)
                db.session.add(artist)
            else:
                # Mettre à jour le slug si le nom a changé
                new_slug = Artist.make_slug(artist_name, exclude_id=artist.id)
                if new_slug != artist.slug:
                    artist.slug = new_slug

            artist.artist_name  = artist_name
            artist.genre        = data.get('genre', '')[:80]
            artist.bio          = data.get('bio', '')[:500]
            artist.city         = data.get('city', '')[:80]
            artist.avatar_color = data.get('avatarColor', '')[:20]
            artist.soundcloud   = data.get('soundcloud', '')[:200]
            artist.instagram    = data.get('instagram', '')[:200]
            artist.youtube      = data.get('youtube', '')[:200]
            db.session.commit()
            logger.info(f'[WATT] Profil sauvegardé : {artist.slug}')
            return jsonify({'ok': True, 'artist': artist.to_dict()})

        else:
            artist = Artist.query.filter_by(user_id=user_id).first()
            if not artist:
                return jsonify({'artist': None})
            return jsonify({'artist': artist.to_dict(include_tracks=True)})

    # ── API WATT — Mes sons (CRUD) ────────────────────────────────────────

    @app.route('/api/watt/tracks', methods=['GET', 'POST'])
    def watt_tracks():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import db, Artist, Track

        artist = Artist.query.filter_by(user_id=user_id).first()

        if request.method == 'POST':
            if not artist:
                return jsonify({'error': 'Profil artiste requis avant de publier'}), 400
            data = request.get_json() or {}
            track = Track(
                artist_id  = artist.id,
                name       = (data.get('name') or 'Sans titre')[:200],
                genre      = (data.get('genre') or '')[:80],
                stream_url = data.get('streamUrl') or '',
                r2_key     = data.get('r2Key') or '',
            )
            db.session.add(track)
            db.session.commit()
            logger.info(f'[WATT] Track créé : {track.name} (artiste={artist.slug})')
            return jsonify({'ok': True, 'track': track.to_dict()}), 201

        else:
            if not artist:
                return jsonify({'tracks': []})
            tracks = artist.tracks.all()
            return jsonify({'tracks': [t.to_dict() for t in tracks]})

    @app.route('/api/watt/tracks/<int:track_id>', methods=['DELETE'])
    def delete_watt_track(track_id):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import db, Artist, Track

        artist = Artist.query.filter_by(user_id=user_id).first()
        if not artist:
            return jsonify({'error': 'Artiste introuvable'}), 404

        track = Track.query.filter_by(id=track_id, artist_id=artist.id).first()
        if not track:
            return jsonify({'error': 'Son introuvable'}), 404

        # Décrémenter le compteur global
        if track.plays > 0:
            artist.plays_total = max(0, (artist.plays_total or 0) - track.plays)

        # Supprimer dans R2 si possible
        if app.r2_client and track.r2_key:
            try:
                app.r2_client.delete_object(
                    Bucket=app.config.get('R2_BUCKET', 'smyle-play-audio'),
                    Key=track.r2_key,
                )
                logger.info(f'[WATT] R2 delete : {track.r2_key}')
            except Exception as e:
                logger.warning(f'[WATT] Erreur R2 delete : {e}')

        db.session.delete(track)
        db.session.commit()
        return jsonify({'ok': True})

    # ── API WATT — Compteur d'écoutes ─────────────────────────────────────

    @app.route('/api/watt/plays/<int:track_id>', methods=['POST'])
    def watt_play(track_id):
        from models import db, Track

        track = Track.query.get(track_id)
        if track:
            track.plays += 1
            track.artist.plays_total = (track.artist.plays_total or 0) + 1
            db.session.commit()
        return jsonify({'ok': True, 'plays': track.plays if track else 0})

    # ── API WATT — Classement public (tous artistes) ──────────────────────

    @app.route('/api/artists', methods=['GET'])
    def get_artists():
        """Liste des artistes triés par écoutes. Pour le classement et la découverte."""
        from models import Artist
        artists = (Artist.query
                   .order_by(Artist.plays_total.desc(), Artist.created_at.desc())
                   .limit(50)
                   .all())
        return jsonify({'artists': [a.to_dict() for a in artists]})

    # ── API WATT — Profil public d'un artiste ─────────────────────────────

    @app.route('/api/artists/<slug>', methods=['GET'])
    def get_artist(slug):
        """Profil public complet d'un artiste (avec ses sons)."""
        from models import Artist

        artist = Artist.query.filter_by(slug=slug).first()
        if not artist:
            return jsonify({'error': 'Artiste introuvable'}), 404

        # Calcul du classement (rang de cet artiste parmi tous)
        rank = (Artist.query
                .filter(Artist.plays_total > artist.plays_total)
                .count()) + 1

        data = artist.to_dict(include_tracks=True)
        data['rank'] = rank
        return jsonify({'artist': data})

    # ── API WATT — Derniers sons (feed public) ────────────────────────────

    @app.route('/api/tracks/recent', methods=['GET'])
    def get_recent_tracks():
        """Derniers sons publiés par des artistes WATT (feed public)."""
        from models import Track, Artist
        from sqlalchemy import desc

        rows = (Track.query
                .join(Artist)
                .order_by(desc(Track.uploaded_at))
                .limit(12)
                .all())

        result = []
        for t in rows:
            d = t.to_dict()
            d['artistName'] = t.artist.artist_name
            d['artistSlug'] = t.artist.slug
            d['genre']      = t.genre or t.artist.genre
            result.append(d)

        return jsonify({'tracks': result})

    # ── API Collabs ───────────────────────────────────────────────────────

    @app.route('/api/collabs', methods=['POST'])
    def send_collab():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import db, Artist, Collab

        data          = request.get_json() or {}
        receiver_slug = data.get('to', '').strip()
        message       = data.get('message', '').strip()

        if not message:
            return jsonify({'error': 'Message requis'}), 400
        if len(message) > 600:
            return jsonify({'error': 'Message trop long (max 600 caractères)'}), 400

        sender = Artist.query.filter_by(user_id=user_id).first()
        if not sender:
            return jsonify({'error': 'Tu dois créer un profil artiste avant de contacter'}), 400

        receiver = Artist.query.filter_by(slug=receiver_slug).first()
        if not receiver:
            return jsonify({'error': 'Artiste destinataire introuvable'}), 404

        if sender.id == receiver.id:
            return jsonify({'error': 'Tu ne peux pas te contacter toi-même'}), 400

        collab = Collab(sender_id=sender.id, receiver_id=receiver.id, message=message)
        db.session.add(collab)
        db.session.commit()
        logger.info(f'[COLLAB] {sender.slug} → {receiver.slug}')
        return jsonify({'ok': True}), 201

    @app.route('/api/collabs/inbox', methods=['GET'])
    def collab_inbox():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import Artist, Collab

        artist = Artist.query.filter_by(user_id=user_id).first()
        if not artist:
            return jsonify({'collabs': []})

        collabs = (Collab.query
                   .filter_by(receiver_id=artist.id)
                   .order_by(Collab.created_at.desc())
                   .limit(30)
                   .all())

        # Marquer comme vus
        from models import db
        for c in collabs:
            if c.status == 'pending':
                c.status = 'seen'
        db.session.commit()

        return jsonify({'collabs': [c.to_dict() for c in collabs]})

    @app.route('/api/collabs/unread', methods=['GET'])
    def collab_unread():
        """Nombre de demandes non lues (pour badge dans le dashboard)."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'count': 0})

        from models import Artist, Collab

        artist = Artist.query.filter_by(user_id=user_id).first()
        if not artist:
            return jsonify({'count': 0})

        count = Collab.query.filter_by(receiver_id=artist.id, status='pending').count()
        return jsonify({'count': count})

    # ── API Play counts (playlists officielles) ───────────────────────────

    @app.route('/api/plays/<track_id>', methods=['POST'])
    def increment_play(track_id):
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
        from models import db, Feedback
        data    = request.get_json() or {}
        name    = data.get('name', '').strip()
        email   = data.get('email', '').strip()
        ftype   = data.get('type', 'Autre')
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Message vide'}), 400

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

    # ── API WATT — Upload vers R2 ─────────────────────────────────────────

    @app.route('/api/watt/upload', methods=['POST'])
    def watt_upload():
        """Upload d'un son artiste vers Cloudflare R2 (WATT/{userId}/{ts}-{filename})"""
        import time, re, mimetypes

        user_id    = request.form.get('userId', 'guest')
        track_name = request.form.get('name', '').strip()

        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier fourni'}), 400

        f = request.files['file']
        if not f.filename:
            return jsonify({'error': 'Fichier vide'}), 400

        ext  = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else 'wav'
        safe = re.sub(r'[^a-z0-9_-]', '_', track_name.lower())[:40]
        ts   = int(time.time())
        key  = f'WATT/{user_id}/{ts}-{safe}.{ext}'

        mime, _ = mimetypes.guess_type(f.filename)
        ct = mime or 'audio/wav'

        if app.r2_client:
            try:
                app.r2_client.upload_fileobj(
                    f.stream,
                    app.config.get('R2_BUCKET', 'smyle-play-audio'),
                    key,
                    ExtraArgs={'ContentType': ct},
                )
                base_url = app.config.get('CLOUD_AUDIO_BASE_URL', '').rstrip('/')
                url      = f'{base_url}/{key}' if base_url else f'/api/watt/stream/{key}'
                logger.info(f'[WATT] Upload R2 : {key}')
                return jsonify({'ok': True, 'url': url, 'key': key})
            except Exception as e:
                logger.error(f'[WATT] Erreur upload R2 : {e}')
                return jsonify({'error': str(e)}), 500
        else:
            # Mode dev sans R2 : on simule l'URL
            logger.info(f'[WATT] Mode sans R2 — clé simulée : {key}')
            return jsonify({'ok': True, 'url': None, 'key': key, 'mock': True})

    # ── API WATT Agents — Pipeline ADN ────────────────────────────────────

    @app.route('/api/agents/process-track', methods=['POST'])
    def agents_process_track():
        """
        Lance la chaîne autonome WATT sur un morceau.

        Body JSON :
            {
                "name":  str,           # titre du morceau (requis)
                "genre": str,           # genre déclaré (optionnel)
                "tags":  str | list,    # tags libres (optionnel)
                "bpm":   float,         # BPM (optionnel)
                "id":    int            # ID DB (optionnel, pour logging)
            }

        Retourne :
            {
                "ok": true,
                "result": { dna, confidence, scores, playlist_*, suno_prompt, ... }
            }
        """
        from agents.orchestrator import process_track as agent_process

        data = request.get_json(silent=True) or {}

        # Accepter 'name' ou 'title' (tolérance curl / front)
        track_name = (data.get('name') or data.get('title') or '').strip()

        if not track_name:
            return jsonify({'error': 'Le champ "name" (ou "title") est requis'}), 400

        # Normaliser : toujours passer 'name' à l'orchestrateur
        payload = {**data, 'name': track_name}

        try:
            result = agent_process(payload)
            return jsonify({'ok': True, 'result': result})
        except Exception as e:
            logger.error(f'[WATT Agent] /api/agents/process-track error: {e}')
            return jsonify({'error': str(e)}), 500

    # ── API WATT Agents — Traitement automatique au upload ────────────────

    @app.route('/api/agents/process-track/<int:track_id>', methods=['POST'])
    def agents_process_track_by_id(track_id: int):
        """
        Lance le pipeline ADN sur un track existant en base (par ID).
        Pratique pour ré-analyser un son déjà uploadé.
        """
        from agents.orchestrator import process_track as agent_process

        if not db_enabled:
            return jsonify({'error': 'Base de données non disponible'}), 503

        track = Track.query.get(track_id)
        if not track:
            return jsonify({'error': 'Morceau introuvable'}), 404

        try:
            result = agent_process({
                'id':    track.id,
                'name':  track.name,
                'genre': track.genre or '',
            })
            return jsonify({'ok': True, 'result': result})
        except Exception as e:
            logger.error(f'[WATT Agent] process-track/{track_id} error: {e}')
            return jsonify({'error': str(e)}), 500

    # ── Healthcheck ────────────────────────────────────────────────────────

    @app.route('/health')
    def health():
        return jsonify({
            'status': 'ok',
            'db':     db_enabled,
            'r2':     r2_client is not None,
        })

    # ── Catch-all SPA ─────────────────────────────────────────────────────

    @app.errorhandler(404)
    def not_found(e):
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
