from datetime import datetime
from urllib.parse import quote
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

# Étape 2 — format couleur hex "#RRGGBB" utilisé partout (track.color,
# futures extensions UI). Regex volontairement stricte (6 chars, majuscules
# ou minuscules) pour éviter les formats à 3 chars ou sans dièse. Null reste
# permis et signifie "hérite de la brandColor de l'artiste".
HEX_COLOR_RE = r"^#[0-9a-fA-F]{6}$"


class TrackCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    full_prompt: str = Field(min_length=1)
    # Optionnel ; null = fallback brandColor. Validé par la longueur
    # VARCHAR(7) en base + la regex Pydantic pour garantir l'intégrité.
    color: str | None = Field(default=None, pattern=HEX_COLOR_RE)
    # Sprint 1 PR2 (2026-05-04) — migration POST track Flask → FastAPI.
    # audio_url + r2_key sont les retours de l'upload R2 du fichier audio
    # (endpoint Flask /api/watt/upload existant). On accepte aussi
    # cover_url (endpoint Flask /api/watt/upload-image) pour la pochette,
    # et prompt_id pour lier à un prompt préexistant si dispo.
    audio_url: str | None = Field(default=None, max_length=2048)
    # P2 durée audio (2026-07-30) — renvoyée par POST /watt/upload (calcul
    # serveur pydub) et repostée telle quelle par le front. Borne 10 h.
    duration_seconds: float | None = Field(default=None, ge=0, le=36000)
    r2_key: str | None = Field(default=None, max_length=500)
    cover_url: str | None = Field(default=None, max_length=2048)
    prompt_id: UUID | None = None
    # Tags libres — séparés par des virgules ("chill, dark, guitare, 90bpm")
    tags: str | None = Field(default=None, max_length=500)
    # Plateforme/IA d'origine du son (suno, udio, riffusion, stable_audio,
    # autre). Validation souple ici (jamais de 422 sur la création) ; la
    # borne stricte est tenue par le CHECK DB ck_tracks_platform_enum + le
    # <select> frontend. Vide → None.
    platform: str | None = Field(default=None, max_length=20)
    # C2 — drapeau de placement « beat » (étagère /beats) + BPM optionnel.
    # Le beat n'est PLUS un produit distinct : la recette est LE produit.
    is_beat: bool = False
    bpm: int | None = Field(default=None, ge=40, le=300)


class TrackUpdate(BaseModel):
    """
    PATCH partiel d'un track. Permet d'attacher un prompt_id après coup
    (workflow dashboard : créer track → créer prompt → PATCH track avec
    prompt_id obtenu) ou de mettre à jour la cover.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    color: str | None = Field(default=None, pattern=HEX_COLOR_RE)
    cover_url: str | None = Field(default=None, max_length=2048)
    prompt_id: UUID | None = None
    # C1 WattBoard v3 (2026-06-10) — liaison beat. Le workflow création
    # Audio (modes "Beat seul" / "Recette + beat") crée le track, puis le
    # beat (POST /artist/me/beats), puis lie les deux ici. Les colonnes
    # tracks.beat_id / tracks.pack_price_credits existaient en DB depuis la
    # migration beats mais n'étaient PAS écrivables via l'API (gap détecté
    # à l'audit C1). Ownership du beat vérifiée dans services.tracks.
    beat_id: UUID | None = None
    # Prix du pack recette+beat (crédits). Pertinent seulement si le track
    # a un prompt_id ET un beat_id — consommé par POST /pack/{track_id}/buy.
    pack_price_credits: int | None = Field(default=None, ge=1)
    # Tags libres — séparés par des virgules ("chill, dark, guitare, 90bpm")
    tags: str | None = Field(default=None, max_length=500)
    # C2 — drapeau beat + BPM modifiables après coup.
    is_beat: bool | None = None
    bpm: int | None = Field(default=None, ge=40, le=300)


class DNARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_prompt: str


class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    audio_url: str | None
    r2_key: str | None = None       # exposé pour que le front puisse construire /watt/stream/{r2_key}
    color: str | None
    cover_url: str | None = None
    prompt_id: UUID | None = None
    # C1 — exposés pour le front (cards beat /beats en C2, drawer pack).
    beat_id: UUID | None = None
    pack_price_credits: int | None = None
    # Prix du prompt lié — None si pas de prompt ou non injecté.
    # Peuplé uniquement dans les endpoints playlist detail.
    prompt_price_credits: int | None = None
    tags: str | None = None
    platform: str | None = None
    # C2 — drapeau beat + BPM (cards /beats).
    is_beat: bool = False
    bpm: int | None = None
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def stream_url(self) -> str:
        """URL de stream à utiliser côté frontend.

        Priorité :
          1. Proxy same-origin /watt/stream/{r2_key} (pas de CORS, pas de CSP)
             → préféré dès que r2_key est disponible.
          2. URL R2 directe audio_url (fallback si pas de r2_key).
          3. Chaîne vide si aucune des deux n'est disponible.

        La r2_key est encodée segment par segment pour gérer les espaces
        et caractères spéciaux (tirets, accents…) dans les noms de fichiers.
        """
        if self.r2_key:
            encoded = "/".join(quote(seg, safe="") for seg in self.r2_key.split("/"))
            return f"/watt/stream/{encoded}"
        if self.audio_url:
            return self.audio_url
        return ""


class TrackWithDNA(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track: TrackRead
    dna: DNARead
