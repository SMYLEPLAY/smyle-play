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
)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


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
    created_at: datetime

    @computed_field
    @property
    def euro_equivalent_earned(self) -> float:
        return round(self.credits_earned_total * 0.70, 2)

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

    @field_validator("genre", "city", "soundcloud", "instagram", "youtube",
                     "tiktok", "spotify", "twitter_x")
    @classmethod
    def empty_string_to_none(cls, v: str | None) -> str | None:
        # Champs optionnels : une string vide devient None pour garder la DB propre.
        if v is None or v.strip() == "":
            return None
        return v.strip()

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
        if v is None or v == "":
            return None
        # Validation HttpUrl via Pydantic
        HttpUrl(v)
        return v

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
