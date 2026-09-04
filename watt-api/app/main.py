from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# Observabilité — Sentry s'initialise UNIQUEMENT si un DSN est configuré
# (SENTRY_DSN en env). No-op total sinon : aucun impact en dev/CI/local.
# Permet de voir les erreurs prod avant que l'utilisateur ne les signale.
if settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,        # 10 % des requêtes tracées (perf)
        send_default_pii=False,        # pas de données perso par défaut
        environment="production",
    )
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
from app.routers.notifications import router as notifications_router
from app.routers.messages import router as messages_router
from app.routers.trades import router as trades_router
from app.routers.adn_offers import router as adn_offers_router
from app.routers.reports import router as reports_router
from app.routers.referrals import router as referrals_router
from app.routers.streak import router as streak_router
from app.routers.packs import router as packs_router
from app.routers.resale import router as resale_router
from app.routers.beats import router as beats_router
from app.routers.images import router as images_router
from app.routers.links import router as links_router
from app.routers.the_plan import router as the_plan_router
from app.routers.telemetry import router as telemetry_router
from app.routers.albums import (
    public_router as albums_public_router,
    router as albums_router,
)
from app.routers.oeuvre import (
    owner_router as oeuvre_owner_router,
    router as oeuvre_router,
)


def create_app() -> FastAPI:
    # ── Blindage clé secrète (Phase 0.3 lancement, 2026-07-24) ───────────
    # Le JWT est signé HS256 avec SECRET_KEY. Si la variable d'env n'est pas
    # posée, la config retombe sur une valeur PAR DÉFAUT PUBLIQUE — n'importe
    # qui pourrait alors forger un jeton pour n'importe quel compte (y compris
    # le compte officiel). On refuse de démarrer le serveur dans ce cas.
    # Ne se déclenche qu'au boot du serveur (create_app) : les migrations
    # Alembic importent app.config mais PAS app.main → la CI migrations n'est
    # pas affectée. Prod + smoke-test posent une vraie clé → démarrage normal.
    _DEFAULT_SECRET = "dev-secret-change-in-production"
    if settings.SECRET_KEY == _DEFAULT_SECRET or not settings.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY absente ou égale à la valeur par défaut publique. "
            "Définis une SECRET_KEY forte et aléatoire dans les variables "
            "d'environnement avant de démarrer le serveur (génère-la p. ex. "
            "avec: python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
        )

    app = FastAPI(title="Smyle Play API", version="1.0.0")

    # ── Rate-limiting (Tier 1 sécurité) ──────────────────────────────────
    # Limiteur global exposé sur app.state (requis par slowapi) + handler
    # 429 JSON. Les limites elles-mêmes sont posées en décorateurs sur les
    # endpoints sensibles (auth + achats). Désactivé si ENVIRONMENT=test.
    from slowapi.errors import RateLimitExceeded

    from app.core.ratelimit import limiter, rate_limit_handler

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

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

    # ── En-têtes de sécurité HTTP (durcissement, 2026-07-24 — RÉVISÉ) ────
    # IMPORTANT : middleware ASGI PUR (et non @app.middleware("http") =
    # BaseHTTPMiddleware). BaseHTTPMiddleware bufferise le corps des réponses,
    # ce qui casse les réponses en STREAMING (proxy R2 des covers et de l'audio)
    # en prod réelle — c'est ce qui avait fait disparaître toutes les pochettes.
    # Ici on n'ajoute que des en-têtes dans http.response.start, sans jamais
    # toucher au corps. Et on SAUTE explicitement les routes de proxy binaire
    # pour ne rien changer à leur réponse.
    # Pas de Content-Security-Policy pour l'instant (le front a beaucoup
    # d'inline scripts/styles — une CSP stricte casserait des pages).
    from starlette.datastructures import MutableHeaders

    _SEC_SKIP_PREFIXES = ("/watt/images", "/watt/stream", "/images")

    class _SecurityHeadersMiddleware:
        def __init__(self, asgi_app):
            self.asgi_app = asgi_app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http" or any(
                scope.get("path", "").startswith(p) for p in _SEC_SKIP_PREFIXES
            ):
                await self.asgi_app(scope, receive, send)
                return

            async def _send(message):
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers.setdefault("X-Content-Type-Options", "nosniff")
                    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
                    headers.setdefault(
                        "Referrer-Policy", "strict-origin-when-cross-origin"
                    )
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=63072000; includeSubDomains",
                    )
                await send(message)

            await self.asgi_app(scope, receive, _send)

    app.add_middleware(_SecurityHeadersMiddleware)

    @app.get("/health")
    async def health():
        """Healthcheck Railway — NE PAS renommer ni monter Flask au-dessus."""
        return {"status": "ok"}

    @app.get("/health/client-echo")
    async def client_echo(request: Request):
        """Diagnostic rate-limiting : montre la clé IP calculée + les
        en-têtes proxy bruts. Ne révèle que les infos du demandeur
        lui-même (aucune donnée sensible)."""
        from app.core.ratelimit import client_ip

        return {
            "rate_limit_key": client_ip(request),
            "x_forwarded_for": request.headers.get("x-forwarded-for"),
            "x_real_ip": request.headers.get("x-real-ip"),
            "x_envoy_external_address": request.headers.get(
                "x-envoy-external-address"
            ),
            "direct_peer": request.client.host if request.client else None,
        }

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
    app.include_router(notifications_router)
    app.include_router(messages_router)
    app.include_router(trades_router)
    app.include_router(adn_offers_router)
    app.include_router(reports_router)
    app.include_router(referrals_router)
    app.include_router(streak_router)
    app.include_router(packs_router)
    app.include_router(resale_router)
    app.include_router(beats_router)
    app.include_router(images_router)
    app.include_router(links_router)
    # MODE LANCEMENT — S-08 (2026-09-02) : THE PLAN est monté comme les autres
    # routeurs ; le masquage est porté par la dépendance require_launch_item
    # ("thePlan") posée sur son APIRouter, relue à CHAQUE requête. Avant, le
    # montage conditionnel était évalué au boot : rallumer l'item exigeait un
    # redéploiement. Mécanisme désormais unique avec resale/packs/trades/voices.
    app.include_router(the_plan_router)
    app.include_router(telemetry_router)
    app.include_router(albums_router)
    app.include_router(albums_public_router)
    app.include_router(oeuvre_router)
    app.include_router(oeuvre_owner_router)

    from app.routers.creator_stats import router as creator_stats_router
    app.include_router(creator_stats_router)

    # ── Pages + statiques (P0-c : Flask supprimé, plus de drapeau) ───────
    # Enregistrés en TOUT DERNIER : toutes les routes API ci-dessus gardent
    # la précédence, le mount "/" n'attrape que le reste (pages + assets).
    from app.routers.pages import mount_static
    from app.routers.pages import router as pages_router

    app.include_router(pages_router)
    mount_static(app)

    return app


app = create_app()
