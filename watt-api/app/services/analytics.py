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
    # B3 : `signup` et `purchase` restent whitelistés (compatibilité d'ingestion)
    # mais AUCUNE page du front ne les émet, et le funnel ne les lit plus —
    # il prend l'inscription dans `users` et l'achat dans `transactions`.
    # Ne pas rebrancher un chiffre d'activité dessus : ce sont des faits
    # comptables, pas du pistage.
    "signup",           # inscription réussie — jamais émis par le front
    "profile_complete", # profil complété
    # Le seul porteur possible du dénominateur « vues de fiche ». Il n'est
    # émis par aucune page aujourd'hui → GET /admin/beta répond
    # `conversion_fiche_vers_deblocage.mesurable = false` plutôt qu'un chiffre
    # inventé.
    "product_view",     # consultation d'une fiche produit — jamais émis à ce jour
    "drawer_open",      # ouverture du drawer d'achat
    "purchase",         # déblocage / achat réussi — jamais émis par le front
    "purchase_failed",  # achat échoué (solde, erreur)
    "boutique_open",    # ouverture de la boutique
    "onboarding_start", # didacticiel premier-run ouvert (D1)
    "onboarding_complete",  # didacticiel terminé / CTA (D1) → mesure de complétion
    # ── Funnel creator-led (F3-1, 2026-08-02) ─────────────────────────────
    # Le modèle d'acquisition repose sur le partage du lien créateur. Ces
    # événements rendent la boucle mesurable ET alimentent, à terme, le
    # graphe de réputation (recette ↔ résultat ↔ identité ↔ comportement).
    # Ils portent tous `props.creator` quand une attribution est connue.
    "creator_visit",    # arrivée sur /u/<slug> ou /@<slug> (1×/session/créateur)
    "share_click",      # un créateur copie/partage son propre lien
    "listen_30s",       # 30 s écoutées sur un extrait (intention réelle)
    "unlock_click",     # clic sur « débloquer » (avant l'achat)
    "adn_reuse",        # réutilisation d'un ADN possédé
    "trade",            # troc réalisé
    "review",           # avis déposé après achat
    "topup_click",      # clic « recharger » → mesure de l'intention de payer
}

MAX_BATCH = 50          # événements max par requête
MAX_STR = 256           # troncature path/referrer


async def _scalar(db: AsyncSession, sql: str, **params) -> int:
    row = (await db.execute(text(sql), params)).scalar()
    return int(row or 0)


async def funnel_data(db: AsyncSession, days: int = 30) -> dict:
    """Funnel + répartition par événement sur une fenêtre glissante.

    B3 (2026-09-08) — CE FUNNEL MENTAIT. Les marches « Inscrits » et
    « 1er achat » comptaient les événements télémétrie `signup` et `purchase`,
    que le front n'émet nulle part (vérifié : seuls `visit`, `creator_visit`,
    `page_view`, `topup_click`, `share_click`, `onboarding_start` et
    `onboarding_complete` sont émis, et seulement après consentement). Les deux
    marches affichaient donc 0, structurellement, quoi qu'il se passe sur le
    site — et un tableau vide se lit comme « personne ne s'inscrit ».

    Elles sont maintenant lues aux SOURCES COMPTABLES :
      - inscrits  → `users.created_at`      (une ligne par compte, sans condition)
      - 1er achat → `transactions`          (unlock/resale, status completed)
    Ces deux chiffres ne dépendent ni du consentement, ni d'un bloqueur, ni de
    JavaScript. Chaque marche porte désormais sa `source`.

    Les marches « Visiteurs » et « Reviennent » restent télémétriques : une
    visite anonyme n'a aucune trace en base. Elles sous-comptent (consentement
    + Do-Not-Track) et le disent dans `avertissements`.

    Pour l'activité réelle de la bêta (qui a acheté quoi à qui, masse de
    Smyles, créateurs), le tableau de bord est `GET /admin/beta`.
    """
    days = max(1, min(days, 365))
    # F-03 (2026-09-02) : la fenêtre est un PARAMÈTRE lié (`:days`), plus une
    # interpolation dans le SQL — `interval '1 day' * :days` est l'idiome
    # Postgres pour un intervalle variable.

    # ── Télémétrie (partielle par nature : consentement + DNT) ────────────
    visitors = await _scalar(
        db,
        "SELECT COUNT(DISTINCT session_id) FROM analytics_events "
        "WHERE name = 'visit' AND created_at >= now() - interval '1 day' * :days",
        days=days)
    returning = await _scalar(
        db,
        "SELECT COUNT(*) FROM (SELECT session_id FROM analytics_events "
        "WHERE name = 'visit' AND created_at >= now() - interval '1 day' * :days "
        "GROUP BY session_id HAVING COUNT(DISTINCT date(created_at)) >= 2) t",
        days=days)

    # ── Sources comptables (exactes, inconditionnelles) ───────────────────
    signups = await _scalar(
        db,
        "SELECT COUNT(*) FROM users "
        "WHERE created_at >= now() - interval '1 day' * :days",
        days=days)
    buyers = await _scalar(
        db,
        "SELECT COUNT(DISTINCT buyer_id) FROM transactions "
        "WHERE type IN ('unlock', 'resale') AND status = 'completed' "
        "AND created_at >= now() - interval '1 day' * :days",
        days=days)

    def pct(n: int, d: int) -> float:
        return round(n * 100 / d, 1) if d else 0.0

    steps = [
        {"key": "visitors",  "label": "Visiteurs",         "count": visitors,
         "source": "telemetrie", "unite": "sessions"},
        {"key": "signups",   "label": "Inscrits",          "count": signups,
         "source": "comptable", "unite": "comptes"},
        {"key": "buyers",    "label": "1er achat",         "count": buyers,
         "source": "comptable", "unite": "comptes"},
        {"key": "returning", "label": "Reviennent (J+1+)", "count": returning,
         "source": "telemetrie", "unite": "sessions"},
    ]
    for s in steps:
        s["of_top"] = 100.0 if s["key"] == "visitors" else pct(s["count"], visitors)

    # Répartition brute par événement (diagnostic télémétrie).
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
        "avertissements": [
            "Visiteurs et Reviennent viennent de la télémétrie : ils ne "
            "comptent que les sessions ayant accepté la bannière de mesure "
            "(Do-Not-Track exclu). Ils sous-comptent.",
            "Inscrits et 1er achat viennent du registre (users, transactions) : "
            "ils sont exacts et ne dépendent d'aucun consentement.",
            "Les taux mêlant les deux (Visite → Inscription, Visite → Achat) "
            "divisent des comptes par des sessions : à lire comme un ordre de "
            "grandeur, pas comme une conversion.",
            "Pour l'activité réelle de la bêta (ventes, masse de Smyles, "
            "créateurs), utiliser GET /admin/beta.",
        ],
    }
