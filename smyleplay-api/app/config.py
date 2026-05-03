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
    # Toutes nullable pour rester dev-friendly : si aucune var n'est définie
    # côté FastAPI, le service R2 dégrade gracieusement (les opérations de
    # delete/upload deviennent des no-ops loggés). En prod (Railway), les 4
    # vars doivent être définies sinon l'audit `services.r2.is_configured()`
    # retourne False et on log un warning au startup.
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_ENDPOINT_URL: str | None = None
    R2_BUCKET: str = "smyle-play-audio"

    @property
    def cors_origins_list(self) -> list[str]:
        """Retourne la liste des origines CORS, en nettoyant les espaces."""
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]


settings = Settings()
