from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.achievements import (
    me_router as achievements_me_router,
    public_router as achievements_public_router,
)
from app.routers.auth import router as auth_router
from app.routers.catalog import (
    catalog_router,
    me_pricing_router,
)
from app.routers.credits import router as credits_router
from app.routers.follows import router as follows_router
from app.routers.library import router as library_router
from app.routers.marketplace import router as marketplace_router
from app.routers.playlists import (
    public_router as playlists_public_router,
    router as playlists_router,
)
from app.routers.search import router as search_router
from app.routers.tracks import router as tracks_router
from app.routers.transactions import router as transactions_router
from app.routers.unlocks import router as unlocks_router
from app.routers.users import router as users_router
from app.routers.voices import router as voices_router
from app.routers.watt_compat import router as watt_compat_router


def create_app() -> FastAPI:
    app = FastAPI(title="Smyle Play API", version="1.0.0")

    # ── CORS ────────────────────────────────────────────────────────────
    # Permet au front Flask (http://localhost:8080) et aux autres origines
    # listées dans settings.CORS_ALLOWED_ORIGINS d'appeler cette API.
    # Les credentials sont autorisés pour que les cookies ou l'en-tête
    # Authorization (JWT) soient transmis côté browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        """Healthcheck Railway — NE PAS renommer ni monter Flask au-dessus."""
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(tracks_router)
    app.include_router(credits_router)
    app.include_router(transactions_router)
    app.include_router(marketplace_router)
    app.include_router(unlocks_router)
    app.include_router(catalog_router)
    app.include_router(library_router)
    app.include_router(me_pricing_router)
    app.include_router(achievements_public_router)
    app.include_router(achievements_me_router)
    app.include_router(watt_compat_router)
    app.include_router(follows_router)
    app.include_router(playlists_router)
    app.include_router(playlists_public_router)
    app.include_router(search_router)
    app.include_router(voices_router)

    return app


app = create_app()
