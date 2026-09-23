"""« Prêt à sortir » — Lot 2 (plan de pré-lancement, section 2).

Une ligne par sortie mensuelle (M1 … M6), avec son critère, la valeur
actuelle, un feu (vert / orange / rouge) et la fiabilité de la mesure. C'est
la base du futur agent analytique qui décidera quand allumer quoi.

PRINCIPE : tous les chiffres viennent de la BASE (tables métier, registre des
transactions, activité par jour), jamais de la télémétrie (soumise au
consentement cookies, donc incomplète par construction).

Définitions (validées par le coordinateur, 23/09) :
  - ACTIF = compte « vérifié » (email vérifié, OU compte créé avant la mise en
    place de la vérification d'email) ET au moins une action réelle sur les
    30 derniers jours : publier une œuvre, écouter un son en étant connecté,
    s'abonner à un créateur, débloquer un contenu. Comptes techniques exclus
    (trésorerie, vitrine officielle, administrateurs, suspendus, supprimés).
  - CRÉATEUR ACTIF = a publié une œuvre dans les 30 derniers jours.
  - DÉBLOCAGES CUMULÉS = achats de contenu réussis, HORS reventes.
  - SIGNALEMENTS = délai médian de traitement + nombre de signalements
    encore ouverts depuis plus de 48 h.
  - RÉTENTION À 7 JOURS = par cohorte d'inscription (semaine) : part des
    inscrits revenus (vus connectés) entre le 7e et le 13e jour.

Date de mise en place de la vérification d'email : première émission d'un
jeton de vérification (`email_verification_tokens`). Avant cette date, un
compte est réputé « vérifié » (il n'a jamais pu l'être).

Feux :
  - vert   : le critère de la sortie est atteint ;
  - orange : pas encore, mais on s'en approche (≥ 70 % de chaque seuil), ou
             une donnée manque / doit être confirmée par Tom ;
  - rouge  : loin du compte.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.publications import SQL_OEUVRES_EN_LIGNE

_FENETRE_JOURS = 30
_PROCHE = 0.7  # « on s'en approche » : ≥ 70 % du seuil

_EXCLUSIONS = (
    "NOT u.is_treasury AND NOT u.is_official AND NOT u.is_admin "
    "AND NOT u.is_banned AND u.email NOT LIKE '%@deleted.watt'"
)


async def _debut_verification(db: AsyncSession) -> datetime | None:
    return (await db.execute(
        text("SELECT MIN(created_at) FROM email_verification_tokens")
    )).scalar_one_or_none()


async def _actifs(db: AsyncSession, debut_verif: datetime | None) -> dict:
    """Nombre d'actifs (définition stricte) + abonnements faits par ces actifs."""
    row = (await db.execute(
        text(
            "WITH actions AS ( "
            "  SELECT uid FROM (" + SQL_OEUVRES_EN_LIGNE + ") o "
            "    WHERE o.created_at >= now() - make_interval(days => :j) "
            "  UNION SELECT user_id FROM user_activity_days "
            "    WHERE listened AND day >= CURRENT_DATE - :j "
            "  UNION SELECT follower_id FROM user_follows "
            "    WHERE created_at >= now() - make_interval(days => :j) "
            "  UNION SELECT buyer_id FROM transactions "
            "    WHERE type = 'unlock' AND status = 'completed' "
            "    AND created_at >= now() - make_interval(days => :j) "
            "), actifs AS ( "
            "  SELECT u.id FROM users u JOIN actions a ON a.uid = u.id "
            "  WHERE " + _EXCLUSIONS + " "
            "  AND (u.email_verified OR CAST(:debut AS timestamptz) IS NULL "
            "       OR u.created_at < CAST(:debut AS timestamptz)) "
            ") "
            "SELECT (SELECT count(*) FROM actifs) AS n, "
            "       (SELECT count(*) FROM user_follows f "
            "          WHERE f.follower_id IN (SELECT id FROM actifs)) AS abonnements"
        ),
        {"j": _FENETRE_JOURS, "debut": debut_verif},
    )).first()
    return {"actifs": int(row.n), "abonnements": int(row.abonnements)}


async def _createurs_actifs(db: AsyncSession) -> int:
    return int((await db.execute(
        text(
            "SELECT count(DISTINCT o.uid) FROM (" + SQL_OEUVRES_EN_LIGNE + ") o "
            "JOIN users u ON u.id = o.uid "
            "WHERE o.created_at >= now() - make_interval(days => :j) AND " + _EXCLUSIONS
        ),
        {"j": _FENETRE_JOURS},
    )).scalar_one())


async def _deblocages_cumules(db: AsyncSession) -> int:
    return int((await db.execute(
        text("SELECT count(*) FROM transactions WHERE type = 'unlock' AND status = 'completed'")
    )).scalar_one())


async def _stock_tirable(db: AsyncSession) -> int:
    """Œuvres qui peuvent sortir d'un pack mystère (même règle que la pioche
    des packs, sans l'exclusion propre à un acheteur)."""
    return int((await db.execute(
        text(
            "SELECT count(*) FROM prompts p "
            "WHERE p.is_published AND NOT p.is_deleted AND p.taken_down_at IS NULL "
            "AND p.pack_eligible AND p.product_type <> 'image' "
            "AND (p.max_supply IS NULL OR (SELECT count(*) FROM unlocked_prompts up "
            "     WHERE up.prompt_id = p.id) < p.max_supply)"
        )
    )).scalar_one())


async def _signalements(db: AsyncSession) -> dict:
    row = (await db.execute(
        text(
            "SELECT "
            " (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY "
            "    EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0) "
            "  FROM content_reports WHERE resolved_at IS NOT NULL "
            "  AND created_at >= now() - interval '90 days') AS mediane_h, "
            " (SELECT count(*) FROM content_reports WHERE resolved_at IS NULL "
            "  AND created_at < now() - interval '48 hours') AS ouverts_48h, "
            " (SELECT count(*) FROM content_reports "
            "  WHERE created_at >= now() - interval '90 days') AS recus_90j"
        )
    )).first()
    return {
        "mediane_heures": round(float(row.mediane_h), 1) if row.mediane_h is not None else None,
        "ouverts_plus_48h": int(row.ouverts_48h),
        "recus_90j": int(row.recus_90j),
    }


async def _retention_j7(db: AsyncSession) -> dict:
    """Rétention à 7 jours par cohorte hebdomadaire d'inscription.

    Seules les cohortes dont la fenêtre J7–J13 est ENTIÈREMENT passée ET
    couverte par le suivi d'activité comptent (sinon le chiffre serait faux
    par construction). Fenêtre : inscriptions des 8 dernières semaines."""
    debut_suivi = (await db.execute(
        text("SELECT MIN(day) FROM user_activity_days")
    )).scalar_one_or_none()
    if debut_suivi is None:
        return {"valeur": None, "cohortes": [], "debut_suivi": None}
    rows = (await db.execute(
        text(
            "WITH inscrits AS ( "
            "  SELECT u.id, CAST(u.created_at AS date) AS j0 FROM users u "
            "  WHERE " + _EXCLUSIONS + " "
            "  AND u.created_at >= now() - interval '56 days' "
            "  AND CAST(u.created_at AS date) + 13 < CURRENT_DATE "
            "  AND CAST(u.created_at AS date) + 7 >= CAST(:suivi AS date) "
            ") "
            "SELECT date_trunc('week', i.j0)::date AS semaine, count(*) AS inscrits, "
            "  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_activity_days a "
            "     WHERE a.user_id = i.id AND a.day BETWEEN i.j0 + 7 AND i.j0 + 13)) AS revenus "
            "FROM inscrits i GROUP BY 1 ORDER BY 1"
        ),
        {"suivi": debut_suivi},
    )).all()
    cohortes = [
        {
            "semaine": r.semaine.isoformat(),
            "inscrits": int(r.inscrits),
            "revenus": int(r.revenus),
            "pourcentage": round(100.0 * int(r.revenus) / int(r.inscrits), 1) if r.inscrits else None,
        }
        for r in rows
    ]
    total = sum(c["inscrits"] for c in cohortes)
    revenus = sum(c["revenus"] for c in cohortes)
    return {
        "valeur": round(100.0 * revenus / total, 1) if total else None,
        "cohortes": cohortes,
        "debut_suivi": debut_suivi.isoformat(),
    }


# ── Critères & feux ──────────────────────────────────────────────────────────

def _crit(libelle: str, valeur, cible: str, atteint: bool | None, progression: float | None,
          fiable: bool, note: str | None = None) -> dict:
    return {
        "critere": libelle,
        "valeur": valeur,
        "cible": cible,
        "atteint": atteint,
        "progression": None if progression is None else max(0.0, min(1.0, progression)),
        "fiabilite": "fiable" if fiable else "partielle",
        "note": note,
    }


def _au_moins(libelle, valeur, seuil, fiable=True, unite="", note=None):
    v = valeur if valeur is not None else None
    atteint = None if v is None else v >= seuil
    prog = None if v is None else (v / seuil if seuil else 1.0)
    return _crit(libelle, v, f"au moins {seuil}{unite}", atteint, prog, fiable, note)


def _feu(criteres: list[dict], mode: str) -> str:
    """mode 'et' : tous les critères ; 'ou' : un seul suffit."""
    atteints = [c["atteint"] for c in criteres]
    if mode == "ou":
        if any(a is True for a in atteints):
            return "vert"
        proches = any((c["progression"] or 0) >= _PROCHE for c in criteres)
        return "orange" if proches or any(a is None for a in atteints) else "rouge"
    if all(a is True for a in atteints):
        return "vert"
    if all(a is True or (c["progression"] or 0) >= _PROCHE or a is None
           for a, c in zip(atteints, criteres)):
        return "orange"
    return "rouge"


async def readiness(db: AsyncSession) -> dict:
    debut_verif = await _debut_verification(db)
    a = await _actifs(db, debut_verif)
    actifs = a["actifs"]
    abos_par_actif = round(a["abonnements"] / actifs, 2) if actifs else None
    createurs = await _createurs_actifs(db)
    deblocages = await _deblocages_cumules(db)
    stock = await _stock_tirable(db)
    sig = await _signalements(db)
    ret = await _retention_j7(db)

    debut_suivi = (await db.execute(
        text("SELECT MIN(day) FROM user_activity_days")
    )).scalar_one_or_none()
    aujourd_hui = datetime.now(timezone.utc).date()
    # Tant que le suivi d'activité n'a pas 30 jours, « écouter connecté » ne
    # couvre pas toute la fenêtre → nombre d'actifs sous-estimé.
    actifs_fiable = debut_suivi is not None and (aujourd_hui - debut_suivi).days >= _FENETRE_JOURS
    note_actifs = None if actifs_fiable else (
        "Le suivi des écoutes a commencé il y a moins de 30 jours : "
        "le nombre d'actifs est encore un peu sous-estimé."
    )

    # Rétention : la sortie M1 s'allume si elle est BASSE (< 20 %) — c'est
    # le signal qu'il faut donner une raison de revenir.
    rv = ret["valeur"]
    ret_crit = _crit(
        "Part des nouveaux inscrits revenus la 2e semaine", rv, "moins de 20 %",
        None if rv is None else rv < 20.0,
        None if rv is None else (1.0 if rv < 20.0 else 20.0 / rv),
        fiable=rv is not None,
        note=None if rv is not None else
        "Pas encore mesurable : il faut au moins deux semaines de suivi après une inscription.",
    )

    # Signalements : délai médian < 48 h ET aucun signalement ouvert depuis > 48 h.
    med = sig["mediane_heures"]
    sig_ok = sig["ouverts_plus_48h"] == 0 and (med is None or med < 48.0)
    sig_crit = _crit(
        "Signalements traités en moins de 48 h",
        {"delai_median_heures": med, "ouverts_depuis_plus_de_48h": sig["ouverts_plus_48h"]},
        "délai médian sous 48 h et aucun en retard",
        sig_ok, 1.0 if sig_ok else 0.5, fiable=True,
        note=None if sig["recus_90j"] else "Aucun signalement reçu sur 90 jours.",
    )

    commission_on = bool(settings.FEATURE_MARKET_SMYLES)
    lancement = _date_lancement()
    mois = None if lancement is None else max(0, (aujourd_hui - lancement).days) / 30.44

    sorties = [
        {
            "mois": "M1", "sortie": "Trophées et série quotidienne", "regle": "un des deux critères",
            "criteres": [
                _au_moins("Utilisateurs actifs (30 derniers jours)", actifs, 100,
                          fiable=actifs_fiable, note=note_actifs),
                ret_crit,
            ], "mode": "ou",
        },
        {
            "mois": "M2", "sortie": "Messagerie privée", "regle": "tous les critères",
            "criteres": [
                _au_moins("Utilisateurs actifs (30 derniers jours)", actifs, 300,
                          fiable=actifs_fiable, note=note_actifs),
                _au_moins("Abonnements par utilisateur actif", abos_par_actif, 3,
                          fiable=actifs_fiable),
                sig_crit,
            ], "mode": "et",
        },
        {
            "mois": "M3", "sortie": "Packs mystère", "regle": "tous les critères",
            "criteres": [
                _au_moins("Œuvres pouvant sortir d'un pack", stock, 300),
            ], "mode": "et",
        },
        {
            "mois": "M4", "sortie": "Beats, voix, albums", "regle": "tous les critères",
            "criteres": [
                _au_moins("Créateurs actifs (ont publié dans les 30 derniers jours)", createurs, 50),
            ], "mode": "et",
        },
        {
            "mois": "M5", "sortie": "Revente, troc, offres ADN", "regle": "tous les critères",
            "criteres": [
                _au_moins("Déblocages depuis l'ouverture (hors reventes)", deblocages, 500),
                _crit("Commission de la plateforme allumée", "oui" if commission_on else "non",
                      "oui", commission_on, 1.0 if commission_on else 0.0, fiable=True),
            ], "mode": "et",
        },
        {
            "mois": "M6", "sortie": "Retrait en euros et paliers", "regle": "(1000 actifs OU 6 mois) ET juridique prêt",
            "criteres": [
                _au_moins("Utilisateurs actifs (30 derniers jours)", actifs, 1000,
                          fiable=actifs_fiable, note=note_actifs),
                _crit("Mois depuis le lancement", None if mois is None else round(mois, 1),
                      "au moins 6", None if mois is None else mois >= 6,
                      None if mois is None else mois / 6, fiable=True),
                _crit("Juridique prêt (expert-comptable, DAC7, Stripe Connect)", "à confirmer par Tom",
                      "confirmé", None, None, fiable=False,
                      note="Ne se mesure pas : c'est Tom qui le confirme."),
            ], "mode": "m6",
        },
    ]
    for s in sorties:
        crits = s["criteres"]
        if s["mode"] == "m6":
            volume = _feu(crits[:2], "ou")
            juridique = crits[2]["atteint"]
            s["feu"] = "vert" if volume == "vert" and juridique is True else (
                "rouge" if volume == "rouge" else "orange")
        else:
            s["feu"] = _feu(crits, s["mode"])
        s["fiabilite"] = "fiable" if all(c["fiabilite"] == "fiable" for c in crits) else "partielle"
        del s["mode"]

    return {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "source": "base de données uniquement (jamais la télémétrie)",
        "definitions": {
            "actif": ("Compte vérifié (ou créé avant la vérification d'email) qui a, "
                      "sur les 30 derniers jours, publié, écouté un son connecté, "
                      "suivi un créateur ou débloqué un contenu."),
            "createur_actif": "A publié une œuvre dans les 30 derniers jours.",
            "deblocages": "Achats de contenu réussis depuis l'ouverture, hors reventes.",
            "retention": ("Par semaine d'inscription : part des inscrits revenus "
                          "entre le 7e et le 13e jour."),
        },
        "chiffres": {
            "actifs": actifs,
            "abonnements_par_actif": abos_par_actif,
            "createurs_actifs": createurs,
            "deblocages_cumules": deblocages,
            "stock_tirable": stock,
            "signalements": sig,
            "retention_j7": ret,
            "verification_email_depuis": debut_verif.isoformat() if debut_verif else None,
            "suivi_activite_depuis": debut_suivi.isoformat() if debut_suivi else None,
        },
        "sorties": sorties,
    }


def _date_lancement() -> date | None:
    try:
        return date.fromisoformat(str(settings.DATE_LANCEMENT))
    except Exception:  # noqa: BLE001
        return None
