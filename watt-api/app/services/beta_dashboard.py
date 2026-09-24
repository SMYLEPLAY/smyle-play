"""
B3 — Tableau de bord de bêta (admin, lecture seule).

PRINCIPE DIRECTEUR
------------------
Les chiffres d'activité viennent du **registre des transactions** et des
**tables métier**, jamais de la télémétrie.

Une vente est un fait comptable : elle est dans `transactions` (append-only,
trigger `enforce_transaction_no_delete`, champs financiers immuables — cf.
migration 0070). Elle ne dépend ni du consentement cookies, ni d'un bloqueur
de publicité, ni de JavaScript. Un compte est une ligne de `users`. Une
publication est une ligne de `prompts` / `adns` / `visual_adns` / `voices_for_sale` /
`tracks`.

La télémétrie (`analytics_events`) reste utile pour ce qui n'a AUCUNE trace en
base — la vue d'une fiche produit, un clic. Elle n'apparaît ici que dans une
section à part, explicitement étiquetée « partielle » : elle est soumise au
consentement (`_consented()` côté front) et à Do-Not-Track, donc elle
sous-compte par construction. Elle n'est jamais la source d'un chiffre
d'activité.

Coût : 8 requêtes SQL bornées, toutes des agrégats ou des LIMIT explicites.
Aucune donnée sensible n'est renvoyée : pas de mot de passe, pas d'IP, pas
d'e-mail. Les personnes sont désignées par leur pseudo (`artist_name`), avec
un repli non réversible `compte-<8 premiers caractères de l'UUID>`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.publications import SQL_OEUVRES_EN_LIGNE
from app.services.credits import count_bucket_inconsistencies

# Types de transaction qui CRÉENT des Smyles (crédit d'un compte, sans débit
# d'un autre) — cf. `_TXTYPE_BUCKET` dans services/credits.py.
_TYPES_CREATION = ("bonus", "grant", "credit_purchase", "earning", "refund")

# Types de transaction qui DÉPLACENT des Smyles d'un acheteur vers un vendeur
# (et en détruisent la commission) : c'est la définition d'une vente.
_TYPES_VENTE = ("unlock", "resale")

# Pseudo de repli — non réversible vers une personne, et surtout pas l'e-mail.
_PSEUDO = "COALESCE(NULLIF({t}.artist_name, ''), 'compte-' || left({t}.id::text, 8))"

# Un compte anonymisé par la purge RGPD (services/account_deletion.py) porte ce
# suffixe d'e-mail. On ne renvoie jamais l'e-mail : seulement ce compteur.
_SUFFIXE_SUPPRIME = "@deleted.watt"

# Toutes les surfaces de publication d'un créateur, dans un seul jeu de lignes.
# `is_deleted` est le soft-delete commun ; `tracks` n'a pas de `is_published`
# (un morceau déposé est visible sur le profil).
# Définition partagée avec le programme Pionnier (source unique) :
# cf. app/services/publications.py.
_SQL_PUBLICATIONS = SQL_OEUVRES_EN_LIGNE

# Motif UUID canonique : garde-fou avant le cast `::uuid`. Sans lui, une
# métadonnée mal formée ferait planter la requête entière (invalid input
# syntax for type uuid) au lieu de laisser un titre à NULL.
_RE_UUID = (
    "'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    "-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'"
)


def _pct(n: int, d: int) -> float | None:
    """Pourcentage, ou None si le dénominateur est nul. « Aucune donnée » et
    « 0 % » ne veulent pas dire la même chose : on ne divise jamais par zéro
    et on ne renvoie pas un 0 % qui se lirait comme un échec."""
    return round(n * 100 / d, 1) if d else None


async def beta_dashboard_data(
    db: AsyncSession, *, days: int = 7, limit: int = 20
) -> dict:
    """Agrège le tableau de bord de bêta. `days` borné 1..365, `limit` 1..100."""
    days = max(1, min(int(days), 365))
    limit = max(1, min(int(limit), 100))

    # ── 1. Comptes + masse de Smyles réellement détenue ───────────────────
    c = (await db.execute(
        text(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE created_at >= now() - interval '1 day' * :days) "
            "  AS nouveaux, "
            "count(*) FILTER (WHERE is_banned) AS bannis, "
            "count(*) FILTER (WHERE email LIKE :suppr) AS supprimes, "
            "COALESCE(sum(credits_balance), 0) AS solde, "
            "COALESCE(sum(smyles_achetes), 0) AS achetes, "
            "COALESCE(sum(smyles_gagnes), 0) AS gagnes, "
            "COALESCE(sum(smyles_promo), 0) AS promo, "
            "COALESCE(sum(smyles_gagnes_bloque), 0) AS gele, "
            "COALESCE(sum(smyles_promo_gagnes), 0) AS promo_gagnes "
            # Brique 1 : la trésorerie société est hors circulation (sa
            # commission encaissée n'est ni détenue par un créateur, ni
            # achetée en euros). Exposée à part, pas agrégée ici.
            "FROM users WHERE NOT is_treasury"
        ),
        {"days": days, "suppr": "%" + _SUFFIXE_SUPPRIME},
    )).first()

    # ── 2. Publications (tables métier) ───────────────────────────────────
    p = (await db.execute(
        text(
            "WITH pubs AS (" + _SQL_PUBLICATIONS + ") "
            "SELECT count(*) AS total, count(DISTINCT uid) AS createurs, "
            "count(*) FILTER (WHERE created_at >= now() - interval '1 day' * :days) "
            "  AS nouvelles FROM pubs"
        ),
        {"days": days},
    )).first()

    # ── 3. Ledger agrégé par type (une seule passe) ───────────────────────
    lignes = (await db.execute(
        text(
            "SELECT type::text AS tx_type, count(*) AS n, "
            "COALESCE(sum(credits_amount), 0) AS montant, "
            "COALESCE(sum(platform_fee), 0) AS commission, "
            "count(*) FILTER (WHERE created_at >= now() - interval '1 day' * :days) "
            "  AS n_fen, "
            "COALESCE(sum(credits_amount) FILTER "
            "  (WHERE created_at >= now() - interval '1 day' * :days), 0) "
            "  AS montant_fen "
            "FROM transactions WHERE status = 'completed' GROUP BY type"
        ),
        {"days": days},
    )).all()
    par_type = {
        r.tx_type: {
            "nombre": int(r.n),
            "smyles": int(r.montant),
            "commission": int(r.commission),
            "nombre_fenetre": int(r.n_fen),
            "smyles_fenetre": int(r.montant_fen),
        }
        for r in lignes
    }

    def _agg(types: tuple[str, ...], champ: str) -> int:
        return sum(par_type.get(t, {}).get(champ, 0) for t in types)

    ventes_nb = _agg(_TYPES_VENTE, "nombre")
    ventes_smyles = _agg(_TYPES_VENTE, "smyles")
    commission = _agg(_TYPES_VENTE, "commission")
    crees = _agg(_TYPES_CREATION, "smyles")

    # ── 4. Combien de gens achètent / vendent vraiment ────────────────────
    q = (await db.execute(
        text(
            "SELECT count(DISTINCT buyer_id) AS acheteurs, "
            "count(DISTINCT seller_id) AS vendeurs "
            "FROM transactions "
            "WHERE status = 'completed' AND type IN ('unlock', 'resale')"
        )
    )).first()

    # ── 5. Qui a acheté quoi, quand, à qui, pour combien ──────────────────
    ventes = await _dernieres_ventes(db, limit=limit)

    # ── 6. Créateurs par activité ─────────────────────────────────────────
    createurs = await _createurs_actifs(db, limit=limit)

    # ── 7. Télémétrie : uniquement ce qui n'a pas de trace en base ────────
    tele = (await db.execute(
        text(
            "SELECT count(DISTINCT session_id) FILTER (WHERE name = 'product_view') "
            "  AS vues, "
            "count(DISTINCT session_id) FILTER (WHERE name = 'unlock_click') AS clics "
            "FROM analytics_events "
            "WHERE created_at >= now() - interval '1 day' * :days"
        ),
        {"days": days},
    )).first()

    # ── 8. Canari des sous-soldes (réutilise le service existant) ─────────
    incoherences = await count_bucket_inconsistencies(db)

    # Réconciliation de la masse monétaire.
    #   attendu = tout ce qui a été créé − la commission détruite à chaque vente
    # Le transfert acheteur → vendeur est neutre : l'acheteur perd
    # `credits_amount`, le(s) vendeur(s) reçoivent `credits_amount −
    # platform_fee` (vrai pour UNLOCK comme pour RESALE, où la part revendeur
    # et la royaltie d'origine se partagent ce reste). Seule la commission
    # sort de la circulation.
    attendu = crees - commission
    constate = int(c.solde)

    return {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "fenetre_jours": days,
        "source": (
            "registre des transactions (append-only) + tables métier. "
            "Aucun chiffre d'activité ne vient de la télémétrie."
        ),
        # ── Qui est là, et qui fait quelque chose ─────────────────────────
        "comptes": {
            "total": int(c.total),
            "nouveaux_sur_la_fenetre": int(c.nouveaux),
            "ont_publie": int(p.createurs),
            "ont_achete_au_moins_une_fois": int(q.acheteurs),
            "ont_vendu_au_moins_une_fois": int(q.vendeurs),
            "bannis": int(c.bannis),
            "supprimes_rgpd": int(c.supprimes),
            "pct_qui_publient": _pct(int(p.createurs), int(c.total)),
            "pct_qui_achetent": _pct(int(q.acheteurs), int(c.total)),
        },
        # ── Ce qui est publié ────────────────────────────────────────────
        "publications": {
            "total": int(p.total),
            "sur_la_fenetre": int(p.nouvelles),
            "perimetre": (
                "prompts + ADN + ADN visuels + voix publiés, et morceaux déposés"
            ),
        },
        # ── Les ventes : le fait comptable ───────────────────────────────
        "ventes": {
            "total": ventes_nb,
            "smyles_echanges": ventes_smyles,
            "part_reversee_aux_createurs": ventes_smyles - commission,
            "commission_plateforme": commission,
            "sur_la_fenetre": {
                "nombre": _agg(_TYPES_VENTE, "nombre_fenetre"),
                "smyles": _agg(_TYPES_VENTE, "smyles_fenetre"),
            },
            "panier_moyen_smyles": (
                round(ventes_smyles / ventes_nb, 1) if ventes_nb else None
            ),
            "dernieres": ventes,
        },
        # ── La masse de Smyles, et si elle réconcilie ────────────────────
        "masse_smyles": {
            "crees": {
                "bonus_bienvenue_et_recompenses": par_type.get("bonus", {}).get(
                    "smyles", 0
                ),
                "credits_administratifs": par_type.get("grant", {}).get("smyles", 0),
                "achats_de_packs": par_type.get("credit_purchase", {}).get(
                    "smyles", 0
                ),
                "gains_credites_directement": par_type.get("earning", {}).get(
                    "smyles", 0
                ),
                "remboursements": par_type.get("refund", {}).get("smyles", 0),
                "total": crees,
            },
            "depenses_par_les_acheteurs": ventes_smyles,
            "redistribues_aux_createurs": ventes_smyles - commission,
            "detruits_en_commission": commission,
            "en_circulation": {
                "achetes": int(c.achetes),
                "gagnes": int(c.gagnes),
                "dont_gagnes_geles": int(c.gele),
                "promo": int(c.promo),
                # Lot 3 : dont gains de vente NON retirables (payés en promo).
                "dont_promo_gagnes_non_retirables": int(c.promo_gagnes),
                "total": constate,
            },
            "reconciliation": {
                "attendu": attendu,
                "constate": constate,
                "ecart": constate - attendu,
                "reconcilie": constate == attendu,
                "comptes_aux_sous_soldes_incoherents": incoherences,
                "regle": (
                    "attendu = Smyles créés − commission détruite. Un écart non "
                    "nul signale un mouvement de Smyles passé hors du ledger."
                ),
            },
        },
        # ── Les créateurs, par activité ─────────────────────────────────
        "createurs": createurs,
        # ── Le taux qui décide, et ce qu'on ne sait pas mesurer ──────────
        "conversion_fiche_vers_deblocage": _conversion(
            vues=int(tele.vues), clics=int(tele.clics), acheteurs=int(q.acheteurs)
        ),
    }


def _conversion(*, vues: int, clics: int, acheteurs: int) -> dict:
    """« Parmi ceux qui ont vu une fiche, combien ont débloqué ? »

    La vue d'une fiche ne laisse AUCUNE trace en base : il n'existe pas de
    table `product_views`. Le seul porteur possible serait l'événement
    télémétrie `product_view` — whitelisté côté serveur mais émis par AUCUNE
    page du front (seuls `visit`, `creator_visit`, `page_view`, `topup_click`,
    `share_click`, `onboarding_start`, `onboarding_complete` le sont), et de
    toute façon soumis au consentement.

    On le DIT plutôt que d'inventer un chiffre.
    """
    if vues <= 0:
        return {
            "mesurable": False,
            "taux_pct": None,
            "vues_de_fiche_mesurees": 0,
            "acheteurs_uniques": acheteurs,
            "pourquoi": (
                "La vue d'une fiche n'a aucune trace comptable, et l'événement "
                "télémétrie 'product_view' n'est émis par aucune page du front. "
                "Le dénominateur n'existe donc pas : aucun taux n'est calculé "
                "ici, volontairement."
            ),
            "pour_l_obtenir": (
                "Émettre 'product_view' à l'ouverture d'une fiche produit "
                "(ui/core/telemetry.js). Le chiffre restera partiel : la "
                "télémétrie est soumise au consentement et à Do-Not-Track."
            ),
        }
    return {
        "mesurable": True,
        "taux_pct": _pct(acheteurs, vues),
        "vues_de_fiche_mesurees": vues,
        "clics_debloquer_mesures": clics,
        "acheteurs_uniques": acheteurs,
        "avertissement": (
            "Numérateur comptable (transactions), dénominateur télémétrique "
            "(sessions ayant consenti) : le taux est donc un PLAFOND, la vraie "
            "conversion est plus basse."
        ),
    }


async def _dernieres_ventes(db: AsyncSession, *, limit: int) -> list[dict]:
    """Les `limit` dernières ventes, lisibles : acheteur, vendeur, objet,
    montant, date.

    Une seule requête. Le sous-ensemble est borné AVANT les jointures (CTE
    `v` + LIMIT), donc les LEFT JOIN ne touchent que `limit` lignes, par clé
    primaire. Le type d'objet et son identifiant sont dérivés de
    `metadata_json` : le ledger est financier, pas un catalogue, et c'est la
    seule chose qu'il conserve du bien vendu.
    """
    rows = (await db.execute(
        text(
            "WITH v AS ("
            "  SELECT id, created_at, type::text AS tx_type, buyer_id, seller_id, "
            "         credits_amount, artist_revenue, platform_fee, "
            "         metadata_json AS m "
            "  FROM transactions "
            "  WHERE status = 'completed' AND type IN ('unlock', 'resale') "
            "  ORDER BY created_at DESC LIMIT :limit"
            "), r AS ("
            "  SELECT v.*, "
            "    CASE "
            "      WHEN m->>'kind' = 'oeuvre_pack'      THEN 'oeuvre' "
            "      WHEN m->>'prompt_id'     IS NOT NULL THEN 'prompt' "
            "      WHEN m->>'voice_id'      IS NOT NULL THEN 'voix' "
            "      WHEN m->>'track_id'      IS NOT NULL THEN 'morceau' "
            "      WHEN m->>'adn_id'        IS NOT NULL THEN 'adn_musical' "
            "      WHEN m->>'visual_adn_id' IS NOT NULL THEN 'adn_visuel' "
            "      WHEN m->>'playlist_id'   IS NOT NULL THEN 'adn_playlist' "
            "      WHEN m->>'album_id'      IS NOT NULL THEN 'adn_album' "
            "      WHEN m->>'target_id'     IS NOT NULL "
            "           THEN COALESCE(m->>'target_type', 'offre') "
            "      ELSE 'non_identifie' END AS objet_type, "
            "    NULLIF(COALESCE(m->>'prompt_id', m->>'voice_id', m->>'track_id', "
            "                    m->>'adn_id', m->>'visual_adn_id', "
            "                    m->>'playlist_id', m->>'album_id', "
            "                    m->>'target_id'), '') AS oid "
            "  FROM v"
            "), w AS ("
            "  SELECT r.*, CASE WHEN r.oid ~ " + _RE_UUID + " "
            "         THEN r.oid::uuid END AS ouuid FROM r"
            ") "
            "SELECT w.id, w.created_at, w.tx_type, w.credits_amount, w.artist_revenue, "
            "       w.platform_fee, w.objet_type, "
            "       " + _PSEUDO.format(t="ab") + " AS acheteur, "
            "       " + _PSEUDO.format(t="av") + " AS vendeur, "
            "       COALESCE(w.m->>'oeuvre_slug', pr.title, vo.name, tr.title, "
            "                pl.title, al.title, "
            "                left(ad.description, 60), left(va.description, 60)) "
            "         AS objet_titre "
            "FROM w "
            "LEFT JOIN users       ab ON ab.id = w.buyer_id "
            "LEFT JOIN users       av ON av.id = w.seller_id "
            "LEFT JOIN prompts     pr ON pr.id = w.ouuid "
            "LEFT JOIN voices_for_sale vo ON vo.id = w.ouuid "
            "LEFT JOIN tracks      tr ON tr.id = w.ouuid "
            "LEFT JOIN playlists   pl ON pl.id = w.ouuid "
            "LEFT JOIN albums      al ON al.id = w.ouuid "
            "LEFT JOIN adns        ad ON ad.id = w.ouuid "
            "LEFT JOIN visual_adns va ON va.id = w.ouuid "
            "ORDER BY w.created_at DESC"
        ),
        {"limit": limit},
    )).all()

    return [
        {
            "date": r.created_at.isoformat() if r.created_at else None,
            "acheteur": r.acheteur,
            # None si le compte vendeur a été supprimé (FK ON DELETE SET NULL).
            "vendeur": r.vendeur,
            "objet_type": r.objet_type,
            "objet_titre": r.objet_titre or "(objet non retrouvé)",
            "montant_smyles": int(r.credits_amount),
            "part_createur": int(r.credits_amount) - int(r.platform_fee),
            "commission": int(r.platform_fee),
            # 'unlock' = vente primaire, 'resale' = revente entre membres.
            "nature": r.tx_type,
        }
        for r in rows
    ]


async def _createurs_actifs(db: AsyncSession, *, limit: int) -> list[dict]:
    """Créateurs classés par activité : publications, ventes réalisées,
    Smyles gagnés.

    `credits_earned_total` est le cumul de gains maintenu par TOUS les chemins
    de crédit vendeur (unlock, offre ADN, revente, royaltie d'origine, pack) :
    c'est la seule valeur exacte par personne. La reconstruire depuis
    `transactions.artist_revenue` la fausserait sur les reventes, où la part
    revendeur vit dans `metadata_json.seller_cut`, hors colonne.
    """
    rows = (await db.execute(
        text(
            "WITH pubs AS (" + _SQL_PUBLICATIONS + "), "
            "pub_agg AS (SELECT uid, count(*) AS n FROM pubs GROUP BY uid), "
            "ventes AS ("
            "  SELECT seller_id AS uid, count(*) AS n "
            "  FROM transactions "
            "  WHERE status = 'completed' AND type IN ('unlock', 'resale') "
            "    AND seller_id IS NOT NULL "
            "  GROUP BY seller_id"
            ") "
            "SELECT " + _PSEUDO.format(t="us") + " AS pseudo, "
            "       COALESCE(pa.n, 0) AS publications, "
            "       COALESCE(ve.n, 0) AS ventes, "
            "       us.credits_earned_total AS gagnes, "
            "       us.tier AS palier "
            "FROM users us "
            "LEFT JOIN pub_agg pa ON pa.uid = us.id "
            "LEFT JOIN ventes  ve ON ve.uid = us.id "
            "WHERE COALESCE(pa.n, 0) > 0 OR COALESCE(ve.n, 0) > 0 "
            "   OR us.credits_earned_total > 0 "
            "ORDER BY us.credits_earned_total DESC, COALESCE(ve.n, 0) DESC, "
            "         COALESCE(pa.n, 0) DESC "
            "LIMIT :limit"
        ),
        {"limit": limit},
    )).all()
    return [
        {
            "pseudo": r.pseudo,
            "publications": int(r.publications),
            "ventes_realisees": int(r.ventes),
            "smyles_gagnes": int(r.gagnes),
            "palier": r.palier,
        }
        for r in rows
    ]
