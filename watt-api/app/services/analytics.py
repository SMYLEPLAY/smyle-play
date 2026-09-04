"""
Service télémétrie D0 — whitelist d'événements + calcul du funnel.

Le funnel répond à la seule question qui compte avant le lancement :
« où les gens décrochent-ils, en chiffres réels ? »
    visiteur → inscrit → 1er achat → revient
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Whitelist stricte : on ne stocke que des événements connus (anti-bruit/anti-abus).
ALLOWED_EVENTS: set[str] = {
    "visit",            # arrivée sur une page (1×/session/jour idéalement)
    "page_view",        # navigation interne
    "signup",           # inscription réussie
    "profile_complete", # profil complété
    "product_view",     # consultation d'une fiche produit
    "drawer_open",      # ouverture du drawer d'achat
    "purchase",         # déblocage / achat réussi
    "purchase_failed",  # achat échoué (solde, erreur)
    "boutique_open",    # ouverture de la boutique
    "onboarding_start", # didacticiel premier-run ouvert (D1)
    "onboarding_complete",  # didacticiel terminé / CTA (D1) → mesure de complétion
}

MAX_BATCH = 50          # événements max par requête
MAX_STR = 256           # troncature path/referrer


async def _scalar(db: AsyncSession, sql: str, **params) -> int:
    row = (await db.execute(text(sql), params)).scalar()
    return int(row or 0)


async def funnel_data(db: AsyncSession, days: int = 30) -> dict:
    """Funnel + répartition par événement sur une fenêtre glissante."""
    days = max(1, min(days, 365))
    # F-03 (2026-09-02) : la fenêtre est un PARAMÈTRE lié (`:days`), plus une
    # interpolation dans le SQL — `interval '1 day' * :days` est l'idiome
    # Postgres pour un intervalle variable. Les requêtes sont des littéraux
    # purs : bandit B608 (« hardcoded_sql_expressions ») ne se déclenche plus.
    # (`days` était déjà borné 1..365, donc sans injection réelle — c'est
    # l'hygiène de l'outil de CI qui est en jeu.)

    visitors = await _scalar(
        db,
        "SELECT COUNT(DISTINCT session_id) FROM analytics_events "
        "WHERE name = 'visit' AND created_at >= now() - interval '1 day' * :days",
        days=days)
    signups = await _scalar(
        db,
        "SELECT COUNT(DISTINCT session_id) FROM analytics_events "
        "WHERE name = 'signup' AND created_at >= now() - interval '1 day' * :days",
        days=days)
    buyers = await _scalar(
        db,
        "SELECT COUNT(DISTINCT session_id) FROM analytics_events "
        "WHERE name = 'purchase' AND created_at >= now() - interval '1 day' * :days",
        days=days)
    returning = await _scalar(
        db,
        "SELECT COUNT(*) FROM (SELECT session_id FROM analytics_events "
        "WHERE name = 'visit' AND created_at >= now() - interval '1 day' * :days "
        "GROUP BY session_id HAVING COUNT(DISTINCT date(created_at)) >= 2) t",
        days=days)

    def pct(n: int, d: int) -> float:
        return round(n * 100 / d, 1) if d else 0.0

    steps = [
        {"key": "visitors",  "label": "Visiteurs",        "count": visitors,  "of_top": 100.0},
        {"key": "signups",   "label": "Inscrits",         "count": signups,   "of_top": pct(signups, visitors)},
        {"key": "buyers",    "label": "1er achat",        "count": buyers,    "of_top": pct(buyers, visitors)},
        {"key": "returning", "label": "Reviennent (J+1+)", "count": returning, "of_top": pct(returning, visitors)},
    ]

    # Répartition brute par événement (diagnostic).
    rows = (await db.execute(
        text(
            "SELECT name, COUNT(*) AS n FROM analytics_events "
            "WHERE created_at >= now() - interval '1 day' * :days "
            "GROUP BY name ORDER BY n DESC"
        ),
        {"days": days},
    )).all()
    by_event = [{"name": r[0], "count": int(r[1])} for r in rows]

    return {
        "window_days": days,
        "funnel": steps,
        "conversions": {
            "visit_to_signup": pct(signups, visitors),
            "signup_to_purchase": pct(buyers, signups),
            "visit_to_purchase": pct(buyers, visitors),
        },
        "by_event": by_event,
    }
