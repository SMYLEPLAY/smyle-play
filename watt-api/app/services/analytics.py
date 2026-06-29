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
    since_clause = f"created_at >= now() - interval '{days} days'"

    visitors = await _scalar(
        db, f"SELECT COUNT(DISTINCT session_id) FROM analytics_events "
            f"WHERE name = 'visit' AND {since_clause}")
    signups = await _scalar(
        db, f"SELECT COUNT(DISTINCT session_id) FROM analytics_events "
            f"WHERE name = 'signup' AND {since_clause}")
    buyers = await _scalar(
        db, f"SELECT COUNT(DISTINCT session_id) FROM analytics_events "
            f"WHERE name = 'purchase' AND {since_clause}")
    returning = await _scalar(
        db, f"SELECT COUNT(*) FROM (SELECT session_id FROM analytics_events "
            f"WHERE name = 'visit' AND {since_clause} GROUP BY session_id "
            f"HAVING COUNT(DISTINCT date(created_at)) >= 2) t")

    def pct(n: int, d: int) -> float:
        return round(n * 100 / d, 1) if d else 0.0

    steps = [
        {"key": "visitors",  "label": "Visiteurs",        "count": visitors,  "of_top": 100.0},
        {"key": "signups",   "label": "Inscrits",         "count": signups,   "of_top": pct(signups, visitors)},
        {"key": "buyers",    "label": "1er achat",        "count": buyers,    "of_top": pct(buyers, visitors)},
        {"key": "returning", "label": "Reviennent (J+1+)", "count": returning, "of_top": pct(returning, visitors)},
    ]

    # Répartition brute par événement (diagnostic).
    rows = (await db.execute(text(
        f"SELECT name, COUNT(*) AS n FROM analytics_events "
        f"WHERE {since_clause} GROUP BY name ORDER BY n DESC"))).all()
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
