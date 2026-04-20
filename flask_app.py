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
from flask import Flask, jsonify, send_from_directory, request, session, redirect, url_for

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
    # En prod (Postgres) : Alembic gère le schéma (migrations chaînées via
    # `alembic upgrade head` en preDeployCommand). On ne touche PAS au schéma
    # côté Flask — les modèles Flask legacy ont des types (INTEGER id) qui
    # rentrent en conflit avec le schéma FastAPI (UUID id). `db.create_all()`
    # en prod ferait crasher le boot avec DatatypeMismatch sur FK user_id.
    # En dev (SQLite) : pas d'Alembic, donc on garde create_all + ensure_schema.
    db_enabled = bool(app.config.get('DATABASE_URL'))
    if db_enabled:
        from models import db
        db.init_app(app)
        logger.info('PostgreSQL connecté — schéma géré par Alembic (FastAPI)')
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

    # Phase 3 refonte marketplace : la page /watt historique (watt.html) est
    # remplacée par la marketplace unifiée sur /. On garde la route pour ne
    # pas casser les liens externes/bookmarks existants, mais elle redirige
    # en 301 vers l'accueil. Le fichier watt.html a été supprimé.
    @app.route('/watt')
    def watt_page_legacy():
        return redirect(url_for('index'), code=301)

    @app.route('/dashboard')
    def dashboard_page():
        return send_from_directory(BASE_DIR, 'dashboard.html')

    @app.route('/u/<slug>')
    def user_page(slug):
        # La page /u/<slug> est l'unique endroit où vit le profil membre :
        # création (mode owner, squelette éditable), édition (édit-in-place),
        # vue publique. URL neutre : on ne présume pas que l'utilisateur est
        # artiste — le statut « artiste » est acquis par l'action (1er son
        # publié), pas par une étape d'inscription. Un compte fan (sans son)
        # existe pleinement : il peut follow, remplir sa bio, etc.
        return send_from_directory(BASE_DIR, 'artiste.html')

    # Alias rétro-compat : les anciens liens /artiste/<slug> continuent à
    # fonctionner (redirection vers /u/<slug>). À retirer quand tous les
    # liens internes auront migré.
    @app.route('/artiste/<slug>')
    def artiste_page_legacy(slug):
        return redirect(url_for('user_page', slug=slug), code=301)

    @app.route('/library')
    def library_page():
        return send_from_directory(BASE_DIR, 'library.html')

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

    # ── API Prompts — CRUD artiste (Phase 2) ──────────────────────────────

    @app.route('/api/watt/prompts', methods=['GET', 'POST'])
    def watt_prompts():
        """GET : mes prompts. POST : créer un nouveau prompt."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import db, Artist, Prompt

        artist = Artist.query.filter_by(user_id=user_id).first()

        if request.method == 'POST':
            if not artist:
                return jsonify({'error': 'Profil artiste requis avant de publier un prompt'}), 400

            data = request.get_json() or {}
            title       = (data.get('title') or '').strip()
            teaser      = (data.get('teaser') or '').strip()[:300]
            prompt_text = (data.get('promptText') or '').strip()

            try:
                price = int(data.get('priceCredits', 3))
            except (TypeError, ValueError):
                return jsonify({'error': 'priceCredits doit être un entier'}), 400

            # Validations métier
            if len(title) < 5:
                return jsonify({'error': 'Titre trop court (min 5 caractères)'}), 400
            if len(prompt_text) < 50:
                return jsonify({'error': 'Prompt trop court (min 50 caractères)'}), 400
            if price < 3:
                return jsonify({'error': 'Prix minimum : 3 crédits'}), 400

            prompt = Prompt(
                artist_id     = artist.id,
                title         = title[:200],
                teaser        = teaser,
                prompt_text   = prompt_text,
                price_credits = price,
                pack_eligible = bool(data.get('packEligible', True)),
                is_published  = bool(data.get('isPublished', True)),
            )
            db.session.add(prompt)
            db.session.commit()
            logger.info(f'[PROMPT] Créé : {prompt.title} (artiste={artist.slug}, {price}c)')
            return jsonify({'ok': True, 'prompt': prompt.to_dict(include_full_text=True)}), 201

        # GET — mes prompts (propriétaire → texte en clair)
        if not artist:
            return jsonify({'prompts': []})
        prompts = artist.prompts.all()
        return jsonify({
            'prompts': [p.to_dict(include_full_text=True) for p in prompts]
        })

    @app.route('/api/watt/prompts/<int:prompt_id>', methods=['PATCH', 'DELETE'])
    def watt_prompt_detail(prompt_id):
        """PATCH : modifier. DELETE : supprimer. Propriétaire uniquement."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import db, Artist, Prompt

        artist = Artist.query.filter_by(user_id=user_id).first()
        if not artist:
            return jsonify({'error': 'Artiste introuvable'}), 404

        prompt = Prompt.query.filter_by(id=prompt_id, artist_id=artist.id).first()
        if not prompt:
            return jsonify({'error': 'Prompt introuvable'}), 404

        if request.method == 'DELETE':
            db.session.delete(prompt)
            db.session.commit()
            logger.info(f'[PROMPT] Supprimé #{prompt_id} (artiste={artist.slug})')
            return jsonify({'ok': True})

        # PATCH
        data = request.get_json() or {}
        if 'title' in data:
            t = (data.get('title') or '').strip()
            if len(t) < 5:
                return jsonify({'error': 'Titre trop court (min 5)'}), 400
            prompt.title = t[:200]
        if 'teaser' in data:
            prompt.teaser = (data.get('teaser') or '').strip()[:300]
        if 'promptText' in data:
            t = (data.get('promptText') or '').strip()
            if len(t) < 50:
                return jsonify({'error': 'Prompt trop court (min 50)'}), 400
            prompt.prompt_text = t
        if 'priceCredits' in data:
            try:
                p = int(data['priceCredits'])
            except (TypeError, ValueError):
                return jsonify({'error': 'priceCredits doit être un entier'}), 400
            if p < 3:
                return jsonify({'error': 'Prix minimum : 3 crédits'}), 400
            prompt.price_credits = p
        if 'packEligible' in data:
            prompt.pack_eligible = bool(data['packEligible'])
        if 'isPublished' in data:
            prompt.is_published = bool(data['isPublished'])

        db.session.commit()
        return jsonify({'ok': True, 'prompt': prompt.to_dict(include_full_text=True)})

    # ── API Prompts — Catalogue public (Phase 2) ──────────────────────────

    @app.route('/api/prompts', methods=['GET'])
    def public_prompts():
        """Catalogue public des prompts publiés (prompt_text gated)."""
        from models import Prompt, Artist
        from sqlalchemy import desc

        rows = (Prompt.query
                .join(Artist)
                .filter(Prompt.is_published == True)
                .order_by(desc(Prompt.created_at))
                .limit(50)
                .all())

        result = []
        for p in rows:
            d = p.to_dict(include_full_text=False)
            d['artistName'] = p.artist.artist_name
            d['artistSlug'] = p.artist.slug
            result.append(d)

        return jsonify({'prompts': result})

    @app.route('/api/prompts/<int:prompt_id>', methods=['GET'])
    def public_prompt_detail(prompt_id):
        """
        Détail d'un prompt.
        prompt_text en clair si :
          - l'utilisateur est propriétaire (artiste qui l'a créé), OU
          - l'utilisateur l'a débloqué via /unlock (Phase 3).
        """
        from models import Prompt, Artist, UnlockedPrompt

        prompt = Prompt.query.get(prompt_id)
        if not prompt or not prompt.is_published:
            return jsonify({'error': 'Prompt introuvable'}), 404

        is_owner   = False
        has_unlock = False
        user_id    = session.get('user_id')
        if user_id:
            artist = Artist.query.filter_by(user_id=user_id).first()
            if artist and artist.id == prompt.artist_id:
                is_owner = True
            if not is_owner:
                has_unlock = UnlockedPrompt.query.filter_by(
                    user_id=user_id, prompt_id=prompt.id
                ).first() is not None

        reveal = is_owner or has_unlock
        d = prompt.to_dict(include_full_text=reveal)
        d['artistName'] = prompt.artist.artist_name
        d['artistSlug'] = prompt.artist.slug
        d['isOwner']    = is_owner
        d['hasUnlock']  = has_unlock
        return jsonify({'prompt': d})

    # ── API Prompts — Unlock (Phase 3) ────────────────────────────────────

    @app.route('/api/prompts/<int:prompt_id>/unlock', methods=['POST'])
    def unlock_prompt(prompt_id):
        """
        Débloque un prompt pour l'utilisateur connecté.
        Débite le solde de Smyles (credits) et crée un UnlockedPrompt.

        Règles :
        - Auth requise (401 sinon)
        - Impossible de se débloquer son propre prompt (400)
        - Impossible de débloquer 2x le même prompt (409)
        - Solde insuffisant → 402 Payment Required
        - Prompt non publié → 404
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import db, User, Artist, Prompt, UnlockedPrompt

        prompt = Prompt.query.get(prompt_id)
        if not prompt or not prompt.is_published:
            return jsonify({'error': 'Prompt introuvable'}), 404

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'Utilisateur introuvable'}), 404

        # L'artiste ne paie pas pour son propre prompt
        my_artist = Artist.query.filter_by(user_id=user_id).first()
        if my_artist and my_artist.id == prompt.artist_id:
            return jsonify({'error': "C'est ton propre prompt — pas besoin de le débloquer"}), 400

        # Déjà débloqué ?
        existing = UnlockedPrompt.query.filter_by(
            user_id=user_id, prompt_id=prompt.id
        ).first()
        if existing:
            return jsonify({
                'error': 'Prompt déjà débloqué',
                'unlock': existing.to_dict(),
            }), 409

        price = int(prompt.price_credits or 0)
        solde = int(user.credits or 0)
        if solde < price:
            return jsonify({
                'error': 'Solde insuffisant',
                'required': price,
                'balance':  solde,
            }), 402

        # Transaction : débit + création unlock + incrément plays
        user.credits = solde - price
        unlock = UnlockedPrompt(
            user_id    = user_id,
            prompt_id  = prompt.id,
            price_paid = price,
        )
        prompt.plays = (prompt.plays or 0) + 1
        db.session.add(unlock)
        db.session.commit()

        logger.info(f'[UNLOCK] u={user_id} p={prompt.id} prix={price}c solde={user.credits}c')

        d = prompt.to_dict(include_full_text=True)
        d['artistName'] = prompt.artist.artist_name
        d['artistSlug'] = prompt.artist.slug
        return jsonify({
            'ok':      True,
            'prompt':  d,
            'unlock':  unlock.to_dict(),
            'balance': user.credits,
        }), 201

    # ── API Library — mes unlocks (Phase 3) ───────────────────────────────

    @app.route('/api/me/library/prompts', methods=['GET'])
    def my_library_prompts():
        """Liste les prompts que l'utilisateur a débloqués (avec texte complet)."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié'}), 401

        from models import UnlockedPrompt, Prompt, Artist

        rows = (UnlockedPrompt.query
                .filter_by(user_id=user_id)
                .order_by(UnlockedPrompt.created_at.desc())
                .all())

        prompts = []
        for u in rows:
            p = u.prompt
            if not p:
                continue
            d = p.to_dict(include_full_text=True)
            d['artistName']   = p.artist.artist_name
            d['artistSlug']   = p.artist.slug
            d['unlockedAt']   = u.created_at.isoformat()
            d['pricePaid']    = int(u.price_paid or 0)
            prompts.append(d)

        return jsonify({'prompts': prompts})

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

        from models import db, Artist, Track, User

        artist = Artist.query.filter_by(user_id=user_id).first()

        if request.method == 'POST':
            # ── Gate "profil publié" (Étape 1) ────────────────────────────────
            # Un son ne peut être publié que si l'utilisateur a déjà rendu son
            # profil public depuis /u/<slug>. Le flag est porté par la colonne
            # users.profile_public (écrite par FastAPI, lue ici). 409 permet
            # au front d'afficher un CTA pédagogique distinct du 400 "pas
            # d'artiste" (qui ne devrait plus arriver en pratique).
            user = User.query.get(user_id)
            if not user or not bool(getattr(user, 'profile_public', False)):
                return jsonify({
                    'error':   'profile_not_published',
                    'message': 'Publie d\'abord ton profil pour pouvoir publier un son.',
                    'redirect': '/u/me',
                }), 409
            if not artist:
                return jsonify({'error': 'Profil artiste requis avant de publier'}), 400
            data = request.get_json() or {}
            # Étape 2 — couleur optionnelle. On valide le format côté API pour
            # rester cohérent avec Pydantic (HEX_COLOR_RE) sans dépendre de
            # la contrainte DB (volontairement absente pour rester additive).
            # Une valeur invalide est silencieusement ignorée (color=NULL →
            # fallback brandColor) plutôt que de 422 l'upload entier, car
            # c'est un champ d'agrément, pas une donnée critique.
            import re as _re
            _raw_color = (data.get('color') or '').strip()
            color = _raw_color if _re.match(r'^#[0-9a-fA-F]{6}$', _raw_color) else None
            track = Track(
                artist_id  = artist.id,
                name       = (data.get('name') or 'Sans titre')[:200],
                genre      = (data.get('genre') or '')[:80],
                stream_url = data.get('streamUrl') or '',
                r2_key     = data.get('r2Key') or '',
                color      = color,
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

    # ── API WATT — Upload d'image de profil (avatar / cover) ──────────────
    #
    # Endpoint dédié aux images de profil artiste (photo de profil + cover
    # photo). Distinct de /api/watt/upload (audio) car :
    #   • types MIME différents (image/* vs audio/*)
    #   • limite de taille plus basse (5 MB vs 50 MB pour l'audio)
    #   • clé R2 namespacée PROFILE/{userId}/{kind}-{ts}.{ext}
    #
    # Usage côté frontend (artiste.js) :
    #   POST /api/watt/upload-image
    #     multipart/form-data : file=<File>, userId=<uuid>, kind=avatar|cover
    #   → 200 { ok: true, url: 'https://…', key: 'PROFILE/…' }
    #
    # Le frontend enchaîne avec PATCH /users/me { avatar_url / cover_photo_url }
    # pour persister l'URL dans la DB.

    @app.route('/api/watt/upload-image', methods=['POST'])
    def watt_upload_image():
        """Upload d'une image de profil (avatar ou cover) vers R2."""
        import time, re, mimetypes

        user_id = request.form.get('userId', '').strip()
        kind    = request.form.get('kind', '').strip().lower()

        if not user_id:
            return jsonify({'error': 'userId manquant'}), 400
        if kind not in ('avatar', 'cover'):
            return jsonify({'error': 'kind doit être "avatar" ou "cover"'}), 400
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier fourni'}), 400

        f = request.files['file']
        if not f.filename:
            return jsonify({'error': 'Fichier vide'}), 400

        # ── Validation MIME + extension (whitelist stricte) ───────────────
        ALLOWED_EXT  = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
        ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext not in ALLOWED_EXT:
            return jsonify({
                'error': f'Format non supporté — utilise {", ".join(sorted(ALLOWED_EXT))}'
            }), 400

        mime, _ = mimetypes.guess_type(f.filename)
        if mime and mime not in ALLOWED_MIME:
            return jsonify({'error': f'MIME non autorisé : {mime}'}), 400
        ct = mime or 'image/jpeg'

        # ── Limite de taille : 5 MB (on lit en mémoire car les images sont petites) ──
        MAX_SIZE = 5 * 1024 * 1024
        f.stream.seek(0, 2)   # seek to end
        size = f.stream.tell()
        f.stream.seek(0)
        if size > MAX_SIZE:
            return jsonify({
                'error': f'Image trop lourde ({size // 1024} KB) — max 5 MB.'
            }), 400

        # ── Clé R2 ─────────────────────────────────────────────────────────
        safe_uid = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)[:60]
        ts       = int(time.time())
        key      = f'PROFILE/{safe_uid}/{kind}-{ts}.{ext}'

        if app.r2_client:
            try:
                app.r2_client.upload_fileobj(
                    f.stream,
                    app.config.get('R2_BUCKET', 'smyle-play-audio'),
                    key,
                    ExtraArgs={
                        'ContentType': ct,
                        # Les images de profil sont publiques par nature
                        'CacheControl': 'public, max-age=604800',
                    },
                )
                base_url = app.config.get('CLOUD_AUDIO_BASE_URL', '').rstrip('/')
                if not base_url:
                    return jsonify({
                        'error': 'Bucket R2 non exposé publiquement (CLOUD_AUDIO_BASE_URL manquant). Utilise "Coller une URL" à la place.'
                    }), 500
                url = f'{base_url}/{key}'
                logger.info(f'[PROFILE] Upload R2 image : {key}')
                return jsonify({'ok': True, 'url': url, 'key': key})
            except Exception as e:
                logger.error(f'[PROFILE] Erreur upload image : {e}')
                return jsonify({'error': str(e)}), 500
        else:
            # Mode dev sans R2 : on renvoie une erreur explicite plutôt
            # qu'une fausse URL qui casserait le rendu de la page.
            return jsonify({
                'error': 'Stockage R2 non configuré en dev local — utilise "Coller une URL" à la place.'
            }), 503

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
