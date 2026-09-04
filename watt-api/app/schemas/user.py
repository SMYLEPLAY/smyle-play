import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
)

from app.schemas.track import validate_media_url

# S-03 sécurité (2026-09-02) — liens sociaux.
#
# Les valeurs sont posées en `href` sur la page publique /u/<slug> et
# interpolées dans l'aperçu du dashboard : un schéma `javascript:` ou un
# guillemet = XSS. Règle serveur (le front S-02 garde sa propre barrière) :
#   - pseudo nu `@toto` / `toto` (instagram, tiktok, twitter_x) → stocké
#     SANS le `@` ; le front reconstruit l'URL du réseau ;
#   - sinon URL http(s) absolue ≤ 500 caractères, sans `"'<>`` ni
#     caractère de contrôle ; un `domaine.tld/...` sans schéma est
#     normalisé en `https://` (saisie courante) ;
#   - tout le reste → ValueError → 422.
_SOCIAL_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9_.-]{1,60}$")
_SOCIAL_BARE_DOMAIN_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(/.*)?$")
_SOCIAL_FORBIDDEN_CHARS = set('"\'<>`\\') | {chr(c) for c in range(0, 32)} | {chr(127)}
_SOCIAL_URL_MAX_LEN = 500

# artist_name : affiché dans des attributs `alt`/`title`, en texte partout
# (cartes Top Artistes de l'accueil non connecté) et, jusqu'à S-01/S-02,
# dans des `onclick="…('${name}')"` (messagerie, topbar). Défense en
# profondeur : pas de chevrons/guillemets/backtick ni de caractère de
# contrôle. L'apostrophe ASCII (`'`) — fréquente dans les noms français
# (« L'Impératrice ») — n'est pas refusée mais normalisée en apostrophe
# typographique `’` (U+2019), inoffensive dans une chaîne JS, même slug.
_NAME_FORBIDDEN_CHARS = set('<>"`') | {chr(c) for c in range(0, 32)} | {chr(127)}


def validate_social_link(v: str | None, *, allow_handle: bool) -> str | None:
    """Normalise un lien social : pseudo nu (si autorisé) ou URL http(s)."""
    if v is None:
        return None
    v = v.strip()
    if v == "":
        return None
    if any(ch in _SOCIAL_FORBIDDEN_CHARS for ch in v):
        raise ValueError("Lien invalide : URL https:// ou @pseudo attendu")
    if allow_handle and _SOCIAL_HANDLE_RE.match(v):
        return v.lstrip("@")
    if len(v) > _SOCIAL_URL_MAX_LEN:
        raise ValueError("Lien invalide : URL trop longue (500 caractères max)")
    candidate = v
    if "://" not in candidate and _SOCIAL_BARE_DOMAIN_RE.match(candidate):
        candidate = "https://" + candidate
    try:
        u = HttpUrl(candidate)
    except Exception as exc:
        raise ValueError("Lien invalide : URL https:// ou @pseudo attendu") from exc
    if u.scheme not in ("http", "https"):
        raise ValueError("Lien invalide : URL https:// ou @pseudo attendu")
    return candidate


# ──────────────────────────────────────────────────────────────────────────
# Liste canonique des casquettes / rôles déclarables sur /u/<slug>.
# Chantier "Positionnement fan/artiste" — migration 0018.
#
# Les rôles sont stockés côté DB comme JSON array de ces codes exacts
# (slugs ASCII, snake_case). Le mapping code → label humain est côté
# frontend (artiste.js) — la DB ne voit que les codes.
#
# L'ordre ci-dessous est celui de l'affichage du dropdown (plus
# "coté" en haut, plus accessoire en bas). Modifier cette liste =
# changement de contrat public : prévoir une migration pour nettoyer
# les arrays historiques qui référencent un code retiré.
# ──────────────────────────────────────────────────────────────────────────
ROLE_CODES: tuple[str, ...] = (
    # ── Casquettes AUDIO (migration 0018) ──────────────────────────────────
    "artiste",
    "producteur",
    "beatmaker",
    "topliner",
    "ghostwriter",
    "compositeur",
    "parolier",
    "arrangeur",
    "editeur",
    "dj",
    "ingenieur_son",
    "auditeur",
    # ── Casquettes VISUELLES / Monde Image (C4, 2026-06-16) ─────────────────
    # CONNECT image : ces codes sont validés EXACTEMENT comme les rôles audio
    # (validation purement Pydantic ; la colonne DB `users.roles` est un JSON
    # array sans enum SQL — AUCUNE migration nécessaire pour les étendre).
    # La recherche d'artistes par rôle (GET /watt/search/artists?role=<code>)
    # n'a PAS de whitelist interne : elle filtre par LIKE JSON sur users.roles,
    # donc tout nouveau code matche dès qu'il est accepté en écriture ici.
    "illustrateur",
    "graphiste",
    "directeur_artistique",
    "photographe",
    "concept_artist",
    "character_designer",
    "retoucheur",
    "coloriste",
    "artiste_3d",
    "prompteur",
    "designer",
    "collectionneur",
)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    # Code de parrainage optionnel saisi à l'inscription (mécanique 1).
    # Best-effort : un code invalide n'empêche pas l'inscription.
    referral_code: str | None = Field(default=None, max_length=16)
    # Inscription encadrée (Phase 3) : l'utilisateur DOIT accepter les CGU et
    # confirmer avoir l'âge minimum. Défaut False → un front qui ne les envoie
    # pas est refusé (validation dans le endpoint register).
    accept_terms: bool = False
    age_confirmed: bool = False


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ── Reset mot de passe (mission Tier 1, 2026-06-10) ─────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    # Mêmes règles que l'inscription (min 8).
    new_password: str = Field(min_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    artist_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    universe_description: str | None = None
    # Chantier 1.2 — champs profil remontés dans la table users
    genre: str | None = None
    city: str | None = None
    soundcloud: str | None = None
    instagram: str | None = None
    youtube: str | None = None
    # Chantier "Profil artiste type" (migration 0016)
    cover_photo_url: str | None = None
    influences: str | None = None
    tiktok: str | None = None
    spotify: str | None = None
    twitter_x: str | None = None
    language: Literal["en", "fr", "es"] = "en"
    brand_color: str | None = None  # Phase 9.2 — hex #RRGGBB normalisé MAJ
    # Chantier "Profil artiste type" (migration 0017) — 2 couleurs de thème
    profile_bg_color:    str | None = None
    profile_brand_color: str | None = None
    profile_public: bool = False  # Chantier 1 — visible sur la vitrine /watt
    # Chantier "Positionnement fan/artiste" (migration 0018) — casquettes
    # déclarées par l'utilisateur. Liste de codes ROLE_CODES. None = pas
    # encore choisi. Cf. ROLE_CODES au début du module.
    roles: list[str] | None = None
    credits_balance: int = 0
    credits_earned_total: int = 0
    # C6 — palier créateur (standard/premium/mythique). Pilote commission,
    # emplacements de vente et visibilité (cf. app/services/tiers.py).
    tier: str = "standard"
    created_at: datetime

    @computed_field
    @property
    def euro_equivalent_earned(self) -> float:
        return round(self.credits_earned_total * 0.70, 2)

    @computed_field
    @property
    def tier_info(self) -> dict:
        """Récap du palier courant (commission, emplacements, visibilité)
        pour la page Offres et l'UI dashboard."""
        from app.services.tiers import tier_public_info

        return tier_public_info(self.tier)

    @computed_field
    @property
    def fiat_withdrawal_status(self) -> str:
        return "planned_roadmap"


class UserUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    artist_name: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=500)
    universe_description: str | None = Field(default=None, max_length=1000)
    # Chantier 1.2 — profil étendu
    genre:      str | None = Field(default=None, max_length=100)
    city:       str | None = Field(default=None, max_length=100)
    soundcloud: str | None = Field(default=None, max_length=500)
    instagram:  str | None = Field(default=None, max_length=255)
    youtube:    str | None = Field(default=None, max_length=500)
    # Chantier "Profil artiste type" (migration 0016)
    cover_photo_url: str | None = Field(default=None, max_length=500)
    influences:      str | None = Field(default=None, max_length=2000)
    tiktok:          str | None = Field(default=None, max_length=255)
    spotify:         str | None = Field(default=None, max_length=500)
    twitter_x:       str | None = Field(default=None, max_length=255)
    # Chantier 1.2 — couleur de marque (#RRGGBB uppercase)
    brand_color: str | None = Field(default=None, max_length=7)
    # Chantier "Profil artiste type" (migration 0017) — thème page publique
    profile_bg_color:    str | None = Field(default=None, max_length=7)
    profile_brand_color: str | None = Field(default=None, max_length=7)
    # Chantier "Positionnement fan/artiste" (migration 0018) — casquettes.
    # On accepte None (pas de changement) ou une liste de codes valides.
    # Une liste vide [] est valide et remet le champ à "aucune casquette".
    # Validation : chaque code doit appartenir à ROLE_CODES.
    roles: list[str] | None = Field(default=None, max_length=len(ROLE_CODES))
    language: Literal["en", "fr", "es"] | None = None

    @field_validator("artist_name", "bio", "universe_description", "influences")
    @classmethod
    def reject_empty_string(cls, v: str | None) -> str | None:
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Field cannot be empty or whitespace only")
        return v

    @field_validator("artist_name")
    @classmethod
    def reject_html_in_artist_name(cls, v: str | None) -> str | None:
        # S-03 — défense en profondeur (l'échappement front reste la vraie
        # barrière) : le nom est interpolé dans des attributs alt/title et
        # des chaînes JS inline. Cf. _NAME_FORBIDDEN_CHARS.
        if v is None:
            return None
        if any(ch in _NAME_FORBIDDEN_CHARS for ch in v):
            raise ValueError("Le nom d'artiste contient des caractères interdits")
        return v.replace("'", "’")

    @field_validator("genre", "city")
    @classmethod
    def empty_string_to_none(cls, v: str | None) -> str | None:
        # Champs optionnels : une string vide devient None pour garder la DB propre.
        if v is None or v.strip() == "":
            return None
        return v.strip()

    @field_validator("instagram", "tiktok", "twitter_x")
    @classmethod
    def validate_social_with_handle(cls, v: str | None) -> str | None:
        # S-03 — @pseudo nu accepté (stocké sans @) ou URL http(s).
        return validate_social_link(v, allow_handle=True)

    @field_validator("soundcloud", "youtube", "spotify")
    @classmethod
    def validate_social_url_only(cls, v: str | None) -> str | None:
        # S-03 — URL http(s) uniquement (pas de notion de pseudo nu).
        return validate_social_link(v, allow_handle=False)

    @field_validator("brand_color", "profile_bg_color", "profile_brand_color")
    @classmethod
    def validate_brand_color(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        import re
        s = v.strip().upper()
        if not re.match(r"^#[0-9A-F]{6}$", s):
            raise ValueError("La couleur doit être au format hex #RRGGBB")
        return s

    @field_validator("avatar_url", "cover_photo_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        # S-03 — même validateur que les médias de tracks : URL relative
        # limitée au proxy same-origin (/watt/images/… ; /watt/stream/… toléré
        # par le validateur partagé) ou URL http(s) absolue, sans guillemet ni
        # chevron. Avant : toute chaîne commençant par "/" passait
        # (`/x" onload="alert(1)` → XSS stocké sur l'accueil).
        return validate_media_url(v)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str] | None) -> list[str] | None:
        """
        Chaque code rôle doit appartenir à ROLE_CODES. On déduplique en
        conservant l'ordre d'apparition (stable). Les strings sont
        normalisées en lowercase avant comparaison — on refuse les
        codes inconnus plutôt que de les silencieusement virer, pour
        que le front remonte clairement une erreur de typage.
        """
        if v is None:
            return None
        seen: set[str] = set()
        out: list[str] = []
        for raw in v:
            if not isinstance(raw, str):
                raise ValueError("Chaque rôle doit être une string")
            code = raw.strip().lower()
            if code not in ROLE_CODES:
                raise ValueError(
                    f"Rôle inconnu : {raw!r}. Valeurs acceptées : {', '.join(ROLE_CODES)}"
                )
            if code in seen:
                continue
            seen.add(code)
            out.append(code)
        return out


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
