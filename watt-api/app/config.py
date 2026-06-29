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


settings = Settings()
