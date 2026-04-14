"""
SMYLE PLAY — Modèles SQLAlchemy (PostgreSQL / SQLite)
Ces modèles remplacent le localStorage en production.
En dev sans DATABASE_URL, SQLite est utilisé automatiquement.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Compte utilisateur SMYLE PLAY."""
    __tablename__ = 'users'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(200), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    play_counts   = db.relationship('PlayCount',  backref='user', lazy='dynamic', cascade='all, delete-orphan')
    saved_mixes   = db.relationship('SavedMix',   backref='user', lazy='dynamic', cascade='all, delete-orphan')
    feedbacks     = db.relationship('Feedback',   backref='user', lazy='dynamic', cascade='all, delete-orphan')

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


class PlayCount(db.Model):
    """Compteur de lectures par track (et optionnellement par user)."""
    __tablename__ = 'play_counts'
    __table_args__ = (
        db.UniqueConstraint('track_id', 'user_id', name='uq_track_user'),
    )

    id       = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.String(60), nullable=False, index=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    count    = db.Column(db.Integer, default=0, nullable=False)
    last_played = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<PlayCount track={self.track_id} count={self.count}>'


class SavedMix(db.Model):
    """Playlist personnalisée sauvegardée par un user."""
    __tablename__ = 'saved_mixes'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name       = db.Column(db.String(200), nullable=False)
    tracks     = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'tracks':     self.tracks,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<SavedMix {self.name}>'


class Feedback(db.Model):
    """Messages envoyés via le formulaire Contact."""
    __tablename__ = 'feedbacks'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    name       = db.Column(db.String(100))
    email      = db.Column(db.String(200))
    type       = db.Column(db.String(50))
    message    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
