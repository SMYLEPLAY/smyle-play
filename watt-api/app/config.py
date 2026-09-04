from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"

    DATABASE_URL: str

    # Clerk : optionnel — non utilisé en prod actuelle (auth via JWT interne).
    # Si activation future de Clerk, définir ces vars en env Railway.
    CLERK_SECRET_KEY: str | None = None
    CLERK_JWKS_URL: str | None = None

    SENTRY_DSN: str | None = None

    # --- Emails transactionnels (Resend) — chantier hygiène revenu 2026-06-10.
    # Sans clé : les emails sont DÉSACTIVÉS proprement (aucune erreur, aucun
    # envoi) — le produit fonctionne à l'identique. Avec clé mais sans domaine
    # vérifié : Resend n'autorise l'envoi que vers l'adresse du compte Resend
    # (mode test) — suffisant tant que le domaine WATT n'est pas déposé.
    RESEND_API_KEY: str | None = None
    # Expéditeur par défaut : domaine de test Resend. À remplacer par
    # "WATT <hello@domaine-officiel>" quand le domaine sera déposé + vérifié.
    EMAIL_FROM: str = "WATT <onboarding@resend.dev>"

    # --- JWT ---
    # Défaut dev-friendly ; en prod DOIT être défini via SECRET_KEY env var.
    SECRET_KEY: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # --- CORS ---
    # Liste d'origines autorisées, séparées par des virgules dans le .env.
    # Défaut dev-friendly : Flask local (:8080) et éventuels fronts alternatifs.
    # En prod on met l'URL Railway ici.
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:8080,"
        "http://127.0.0.1:8080,"
        "http://localhost:5000,"
        "http://localhost:3000"
    )

    # --- Cloudflare R2 (stockage audio) ---
    # Deux conventions de nommage coexistent :
    #   - Noms "modernes" FastAPI  : R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT_URL
    #   - Noms legacy Railway      : R2_ACCESS_KEY / R2_SECRET_KEY / R2_ACCOUNT_ID
    # Les propriétés ci-dessous résolvent automatiquement les deux formes pour
    # ne jamais avoir à retoucher les secrets Railway.
    R2_ACCESS_KEY_ID: str | None = None      # nom moderne (prioritaire)
    R2_ACCESS_KEY: str | None = None          # alias legacy Railway
    R2_SECRET_ACCESS_KEY: str | None = None  # nom moderne (prioritaire)
    R2_SECRET_KEY: str | None = None          # alias legacy Railway
    R2_ENDPOINT_URL: str | None = None       # URL complète (prioritaire)
    R2_ACCOUNT_ID: str | None = None         # alias legacy → construit l'URL
    R2_BUCKET: str = "smyle-play-audio"
    # --- Bucket PRIVÉ pour les IMAGES ORIGINALES payantes ------------------
    # Sécurité (2026-07-25) : l'original d'une image (`images/originals/{uid}`)
    # partage l'UUID de son aperçu public → sa clé est DEVINABLE. Tant qu'il vit
    # dans le bucket PUBLIC, il est atteignable sans achat via l'URL r2.dev.
    # On l'isole donc dans un bucket PRIVÉ dédié. Le service public
    # (audio/covers/aperçus) reste sur R2_BUCKET, inchangé.
    #   • Non défini → effective_private_bucket retombe sur R2_BUCKET : AUCUNE
    #     rupture avant que Tom crée le bucket privé + lance la migration.
    #   • Défini → les originaux sont écrits/lus dans ce bucket privé (lecture
    #     avec fallback public le temps de la migration).
    R2_PRIVATE_BUCKET: str | None = None
    # Domaine PUBLIC r2.dev du bucket (le même que celui des audio_url stockés,
    # ex. https://pub-XXXX.r2.dev). Sert à rediriger le proxy d'images publiques
    # vers l'objet R2 public directement, au lieu de le streamer via le client
    # boto3 backend (fragile : dépend des secrets R2 + du middleware ASGI, a
    # déjà cassé les covers 2 fois). Surchargeable par variable d'env.
    R2_PUBLIC_BASE_URL: str = "https://pub-5d7696b1acd74214b3314fdcab40121f.r2.dev"

    @property
    def effective_private_bucket(self) -> str:
        """Bucket des IMAGES ORIGINALES payantes.

        Retourne R2_PRIVATE_BUCKET s'il est défini, sinon retombe sur le bucket
        public R2_BUCKET — transition sans rupture tant que Tom n'a pas créé le
        bucket privé (les originaux restent alors dans le public, exactement
        comme aujourd'hui). Une fois R2_PRIVATE_BUCKET défini + la migration
        lancée, les originaux vivent dans le bucket privé.
        """
        return self.R2_PRIVATE_BUCKET or self.R2_BUCKET

    @property
    def effective_r2_public_base_url(self) -> str | None:
        base = (self.R2_PUBLIC_BASE_URL or "").strip().rstrip("/")
        return base or None

    @property
    def effective_r2_access_key_id(self) -> str | None:
        return self.R2_ACCESS_KEY_ID or self.R2_ACCESS_KEY

    @property
    def effective_r2_secret_access_key(self) -> str | None:
        return self.R2_SECRET_ACCESS_KEY or self.R2_SECRET_KEY

    @property
    def effective_r2_endpoint_url(self) -> str | None:
        if self.R2_ENDPOINT_URL:
            return self.R2_ENDPOINT_URL
        if self.R2_ACCOUNT_ID:
            return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return None

    @property
    def cors_origins_list(self) -> list[str]:
        """Retourne la liste des origines CORS, en nettoyant les espaces."""
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    # --- MODE LANCEMENT (masquage RÉVERSIBLE des points d'entrée) ─────────
    # Source unique de vérité pour masquer/rallumer des mécaniques encore
    # vides ou trop avancées à l'ouverture publique. RIEN n'est supprimé : on
    # masque seulement le point d'entrée. Réversibilité par item via env.
    #   • MODE_LANCEMENT = True  → mode lancement actif = on masque par défaut.
    #   • SHOW_<ITEM>    = True  → rallume l'item même en mode lancement.
    #   • MODE_LANCEMENT = False → tout est rallumé (fin du lancement).
    # Un item est VISIBLE si : (not MODE_LANCEMENT) or SHOW_<ITEM>.
    # Défauts : tout masqué (MODE_LANCEMENT=True, tous les SHOW_* à False).
    MODE_LANCEMENT: bool = True
    SHOW_PALIERS: bool = False
    SHOW_RESALE: bool = False
    SHOW_PACKS: bool = False
    SHOW_VOIX: bool = False
    SHOW_TROC: bool = False
    SHOW_THE_PLAN: bool = False
    # S-11 (2026-09-04, annexe A §M5) — l'achat de Smyles est masqué tant
    # que Stripe n'est pas branché : /credits/grant répond 403 à tout
    # compte non is_official, donc la modale d'achat promettait une
    # transaction impossible. Rallumable par SHOW_ACHAT_SMYLES=true.
    SHOW_ACHAT_SMYLES: bool = False

    def _item_visible(self, show: bool) -> bool:
        """VISIBLE si le mode lancement est désactivé, ou si l'item est
        explicitement rallumé via son drapeau SHOW_*."""
        return (not self.MODE_LANCEMENT) or show

    def launch_flags_dict(self) -> dict[str, bool]:
        """Dict des booléens VISIBLE finaux consommé par le front (et l'API).
        True = l'item doit être affiché ; False = masqué."""
        return {
            "paliers": self._item_visible(self.SHOW_PALIERS),
            "resale": self._item_visible(self.SHOW_RESALE),
            "packs": self._item_visible(self.SHOW_PACKS),
            "voix": self._item_visible(self.SHOW_VOIX),
            "troc": self._item_visible(self.SHOW_TROC),
            "thePlan": self._item_visible(self.SHOW_THE_PLAN),
            "achatSmyles": self._item_visible(self.SHOW_ACHAT_SMYLES),
        }


settings = Settings()
