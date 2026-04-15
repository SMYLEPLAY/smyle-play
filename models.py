"""
SMYLE PLAY — Modèles SQLAlchemy (PostgreSQL / SQLite)
Ces modèles remplacent le localStorage en production.
En dev sans DATABASE_URL, SQLite est utilisé automatiquement.
"""

import re
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Génère un slug URL-safe depuis un nom d'artiste."""
    import unicodedata
    s = unicodedata.normalize('NFD', name or '')
    s = s.encode('ascii', 'ignore').decode()
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = s.strip()
    s = re.sub(r'[\s-]+', '-', s)
    return s[:80]


# ── Users ─────────────────────────────────────────────────────────────────────

class User(db.Model):
    """Compte utilisateur SMYLE PLAY."""
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    play_counts = db.relationship('PlayCount', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    saved_mixes = db.relationship('SavedMix',  backref='user', lazy='dynamic', cascade='all, delete-orphan')
    feedbacks   = db.relationship('Feedback',  backref='user', lazy='dynamic', cascade='all, delete-orphan')
    artist      = db.relationship('Artist',    backref='user', uselist=False,  cascade='all, delete-orphan')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'email':      self.email,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<User {self.email}>'


# ── Artist ────────────────────────────────────────────────────────────────────

class Artist(db.Model):
    """Profil artiste WATT (1-to-1 avec User)."""
    __tablename__ = 'artists'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                             unique=True, nullable=False, index=True)
    slug         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    artist_name  = db.Column(db.String(100), nullable=False)
    genre        = db.Column(db.String(80),  default='')
    bio          = db.Column(db.Text,        default='')
    city         = db.Column(db.String(80),  default='')
    avatar_color = db.Column(db.String(20),  default='')   # ex: "#8800ff"
    soundcloud   = db.Column(db.String(200), default='')
    instagram    = db.Column(db.String(200), default='')
    youtube      = db.Column(db.String(200), default='')
    plays_total  = db.Column(db.Integer,     default=0)
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    tracks           = db.relationship('Track',  backref='artist', lazy='dynamic',
                                       cascade='all, delete-orphan',
                                       order_by='Track.uploaded_at.desc()')
    collabs_sent     = db.relationship('Collab', foreign_keys='Collab.sender_id',
                                       backref='sender',   lazy='dynamic',
                                       cascade='all, delete-orphan')
    collabs_received = db.relationship('Collab', foreign_keys='Collab.receiver_id',
                                       backref='receiver', lazy='dynamic',
                                       cascade='all, delete-orphan')

    def to_dict(self, include_tracks: bool = False) -> dict:
        track_count = self.tracks.count()
        data = {
            'id':          self.id,
            'userId':      self.user_id,
            'slug':        self.slug,
            'artistName':  self.artist_name,
            'genre':       self.genre,
            'bio':         self.bio,
            'city':        self.city,
            'avatarColor': self.avatar_color,
            'soundcloud':  self.soundcloud,
            'instagram':   self.instagram,
            'youtube':     self.youtube,
            'plays':       self.plays_total,
            'trackCount':  track_count,
            'created_at':  self.created_at.isoformat(),
        }
        if include_tracks:
            data['tracks'] = [t.to_dict() for t in self.tracks.limit(20).all()]
        return data

    @staticmethod
    def make_slug(name: str, exclude_id: int = None) -> str:
        """Génère un slug unique en ajoutant un suffixe si nécessaire."""
        base = _slugify(name) or 'artiste'
        slug = base
        counter = 1
        while True:
            q = Artist.query.filter_by(slug=slug)
            if exclude_id:
                q = q.filter(Artist.id != exclude_id)
            if not q.first():
                return slug
            slug = f'{base}-{counter}'
            counter += 1

    def __repr__(self):
        return f'<Artist {self.slug}>'


# ── Track ─────────────────────────────────────────────────────────────────────

class Track(db.Model):
    """Son publié par un artiste WATT."""
    __tablename__ = 'watt_tracks'

    id          = db.Column(db.Integer,     primary_key=True)
    artist_id   = db.Column(db.Integer,     db.ForeignKey('artists.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    name        = db.Column(db.String(200), nullable=False)
    genre       = db.Column(db.String(80),  default='')
    stream_url  = db.Column(db.Text,        default='')   # URL publique R2
    r2_key      = db.Column(db.String(300), default='')   # clé R2 (pour suppression)
    plays       = db.Column(db.Integer,     default=0)
    uploaded_at = db.Column(db.DateTime,    default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'genre':      self.genre,
            'streamUrl':  self.stream_url,
            'r2Key':      self.r2_key,
            'plays':      self.plays,
            'uploadedAt': int(self.uploaded_at.timestamp() * 1000),
            'date':       self.uploaded_at.strftime('%-d %b'),
        }

    def __repr__(self):
        return f'<Track {self.name}>'


# ── Collab ────────────────────────────────────────────────────────────────────

class Collab(db.Model):
    """Demande de collaboration entre artistes WATT."""
    __tablename__ = 'collabs'

    id          = db.Column(db.Integer,    primary_key=True)
    sender_id   = db.Column(db.Integer,    db.ForeignKey('artists.id', ondelete='CASCADE'), nullable=False)
    receiver_id = db.Column(db.Integer,    db.ForeignKey('artists.id', ondelete='CASCADE'), nullable=False)
    message     = db.Column(db.Text,       nullable=False)
    status      = db.Column(db.String(20), default='pending')   # pending | seen | accepted | declined
    created_at  = db.Column(db.DateTime,   default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'from':       {'name': self.sender.artist_name,   'slug': self.sender.slug},
            'to':         {'name': self.receiver.artist_name, 'slug': self.receiver.slug},
            'message':    self.message,
            'status':     self.status,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<Collab {self.sender_id}→{self.receiver_id}>'


# ── PlayCount (playlists officielles) ─────────────────────────────────────────

class PlayCount(db.Model):
    """Compteur de lectures par track des playlists officielles."""
    __tablename__ = 'play_counts'
    __table_args__ = (
        db.UniqueConstraint('track_id', 'user_id', name='uq_track_user'),
    )

    id          = db.Column(db.Integer,     primary_key=True)
    track_id    = db.Column(db.String(60),  nullable=False, index=True)
    user_id     = db.Column(db.Integer,     db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    count       = db.Column(db.Integer,     default=0, nullable=False)
    last_played = db.Column(db.DateTime,    default=datetime.utcnow)

    def __repr__(self):
        return f'<PlayCount track={self.track_id} count={self.count}>'


# ── SavedMix ──────────────────────────────────────────────────────────────────

class SavedMix(db.Model):
    """Playlist personnalisée sauvegardée par un user."""
    __tablename__ = 'saved_mixes'

    id         = db.Column(db.Integer,     primary_key=True)
    user_id    = db.Column(db.Integer,     db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name       = db.Column(db.String(200), nullable=False)
    tracks     = db.Column(db.JSON,        nullable=False, default=list)
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'tracks':     self.tracks,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<SavedMix {self.name}>'


# ── Feedback ──────────────────────────────────────────────────────────────────

class Feedback(db.Model):
    """Messages envoyés via le formulaire Contact."""
    __tablename__ = 'feedbacks'

    id         = db.Column(db.Integer,     primary_key=True)
    user_id    = db.Column(db.Integer,     db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    name       = db.Column(db.String(100))
    email      = db.Column(db.String(200))
    type       = db.Column(db.String(50))
    message    = db.Column(db.Text,        nullable=False)
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'email':      self.email,
            'type':       self.type,
            'message':    self.message,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<Feedback {self.type} from {self.email}>'
