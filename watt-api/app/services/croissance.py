"""Lot K — tableau de croissance : LA mesure des six premières semaines.

Deux questions, rien d'autre :
  1. combien de créateurs publient vraiment ;
  2. combien de personnes chacun amène (inscrits par son lien de parrainage,
     dont emails vérifiés, et ventes faites à des acheteurs qu'il a amenés).

Les comptes techniques (admin, vitrine officielle, trésorerie) sont exclus.
Lecture seule.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SQL_CREATEURS = text("""
    SELECT u.id, u.artist_name,
           count(DISTINCT t.id)                                         AS oeuvres,
           (SELECT count(*) FROM referrals r WHERE r.referrer_id = u.id) AS inscrits,
           (SELECT count(*) FROM referrals r JOIN users f ON f.id = r.referred_id
             WHERE r.referrer_id = u.id AND f.email_verified)          AS inscrits_verifies,
           (SELECT count(*) FROM transactions x
             WHERE x.seller_id = u.id AND x.type = 'unlock' AND x.status = 'completed')
                                                                         AS ventes,
           (SELECT count(*) FROM transactions x
             WHERE x.seller_id = u.id AND x.type = 'unlock' AND x.status = 'completed'
               AND x.metadata_json ->> 'via_createur' = 'true')         AS ventes_via_createur,
           min(t.created_at)                                            AS premiere_oeuvre
      FROM users u
      JOIN tracks t ON t.artist_id = u.id AND t.is_deleted = false
     WHERE NOT u.is_admin AND NOT u.is_official AND NOT u.is_treasury
     GROUP BY u.id, u.artist_name
     ORDER BY inscrits DESC, oeuvres DESC
     LIMIT 300
""")


async def tableau(db: AsyncSession) -> dict:
    rows = (await db.execute(_SQL_CREATEURS)).all()
    createurs = [
        {
            "pseudo": r.artist_name or "(sans pseudo)",
            "oeuvres": int(r.oeuvres),
            "inscrits": int(r.inscrits),
            "inscritsVerifies": int(r.inscrits_verifies),
            "ventes": int(r.ventes),
            "ventesViaCreateur": int(r.ventes_via_createur),
            "premiereOeuvre": r.premiere_oeuvre.isoformat() if r.premiere_oeuvre else None,
        }
        for r in rows
    ]
    n = len(createurs)
    total_inscrits = sum(c["inscrits"] for c in createurs)
    return {
        "createursPubliants": n,
        "inscritsAmenes": total_inscrits,
        "inscritsParCreateur": round(total_inscrits / n, 2) if n else 0.0,
        "createursQuiAmenent": sum(1 for c in createurs if c["inscrits"] > 0),
        "ventesViaCreateur": sum(c["ventesViaCreateur"] for c in createurs),
        "createurs": createurs,
    }
