"""Codes Pionnier (Lot I) — le rang Pionnier se gagne SUR INVITATION.

Avant : les 100 places allaient au premier compte qui publiait. N'importe qui
ayant l'adresse du site pouvait créer des comptes et les prendre (10 % de
commission à vie).

Maintenant (réglage `PIONEER_CODE_REQUIRED`, actif par défaut) :
  - l'admin génère des codes à usage unique (`/admin/pioneer/codes`) et les
    envoie en message privé, par exemple sous forme de lien
    `https://watt.place/?pionnier=WATT-7K3QX9` ;
  - le créateur saisit le code à l'inscription, ou plus tard une fois connecté
    (`POST /pioneer/code`) ;
  - en direct, seul un compte qui a utilisé un code reçoit un rang.

Le RATTRAPAGE des créateurs bêta (action admin, aperçu puis confirmation)
n'exige pas de code : l'admin voit et valide la liste lui-même.

Tout le monde peut toujours s'inscrire, écouter, acheter et publier : le code
ne conditionne QUE le rang Pionnier.
"""
from __future__ import annotations

import re
import secrets
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Sans 0/O, 1/I/L : lisible au téléphone et sans confusion.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_PREFIXE = "WATT-"
_LONGUEUR = 6  # 31^6 ≈ 887 millions de combinaisons ; essais limités en débit.
MAX_PAR_LOT = 200


class CodeInvalide(Exception):
    """Code inconnu ou déjà utilisé (message volontairement unique)."""


class CodeDejaUtilise(Exception):
    """Ce compte a déjà utilisé un code."""


class CompteNonEligible(Exception):
    """Compte admin, exclu, ou déjà Pionnier : le code n'est pas consommé."""


def normaliser(code: str | None) -> str:
    """« watt 7k3-qx9 » → « WATT-7K3QX9 ». Tolère espaces, tirets, minuscules."""
    brut = re.sub(r"[^0-9A-Za-z]", "", code or "").upper()
    if brut.startswith("WATT"):
        brut = brut[4:]
    return _PREFIXE + brut if brut else ""


def _nouveau() -> str:
    return _PREFIXE + "".join(secrets.choice(_ALPHABET) for _ in range(_LONGUEUR))


async def generer(db: AsyncSession, n: int, *, note: str | None, admin_id: UUID | None) -> list[str]:
    """Crée `n` codes neufs (1..MAX_PAR_LOT). L'appelant commit."""
    n = max(1, min(int(n), MAX_PAR_LOT))
    note = (note or "").strip()[:120] or None
    codes: list[str] = []
    while len(codes) < n:
        code = _nouveau()
        ok = (await db.execute(text(
            "INSERT INTO pioneer_codes (code, note, created_by) VALUES (:c, :n, :a) "
            "ON CONFLICT (code) DO NOTHING RETURNING code"),
            {"c": code, "n": note, "a": admin_id})).scalar_one_or_none()
        if ok:
            codes.append(ok)
    return codes


async def lister(db: AsyncSession, limit: int = 2000) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT c.code, c.note, c.created_at, c.used_at, u.artist_name, u.pioneer_rank "
        "FROM pioneer_codes c LEFT JOIN users u ON u.id = c.used_by "
        "ORDER BY c.created_at DESC, c.code LIMIT :lim"),
        {"lim": max(1, min(int(limit), 2000))})).all()
    return [
        {
            "code": r.code,
            "note": r.note,
            "cree_le": r.created_at.isoformat() if r.created_at else None,
            "utilise_le": r.used_at.isoformat() if r.used_at else None,
            "utilise_par": (r.artist_name or "(sans pseudo)") if r.used_at else None,
            "rang": int(r.pioneer_rank) if r.pioneer_rank is not None else None,
        }
        for r in rows
    ]


async def a_un_code(db: AsyncSession, user_id: UUID) -> bool:
    return (await db.execute(text(
        "SELECT 1 FROM pioneer_codes WHERE used_by = :u"), {"u": user_id})).first() is not None


async def utiliser(db: AsyncSession, user_id: UUID, code: str) -> str:
    """Rattache le code au compte (usage unique, atomique). L'appelant commit.
    Lève CodeDejaUtilise si le compte en a déjà un, CodeInvalide sinon."""
    if await a_un_code(db, user_id):
        raise CodeDejaUtilise("Tu as déjà utilisé un code Pionnier.")
    # Lot I bis — un code n'est jamais gaspillé sur un compte qui ne peut pas
    # (ou n'a pas besoin de) devenir Pionnier : admin (Tom qui teste un lien),
    # compte exclu, compte déjà Pionnier.
    u = (await db.execute(text(
        "SELECT is_admin, is_official, is_treasury, pioneer_excluded, pioneer_rank "
        "FROM users WHERE id = :u"), {"u": user_id})).first()
    if u is None or u.is_admin or u.is_official or u.is_treasury or u.pioneer_excluded:
        raise CompteNonEligible("Ce compte ne peut pas recevoir de place Pionnier : "
                                "le code n'a pas été utilisé.")
    if u.pioneer_rank is not None:
        raise CompteNonEligible("Tu es déjà Pionnier : garde ce code pour quelqu'un d'autre.")
    c = normaliser(code)
    if not c:
        raise CodeInvalide("Code Pionnier invalide ou déjà utilisé.")
    ok = (await db.execute(text(
        "UPDATE pioneer_codes SET used_by = :u, used_at = now() "
        "WHERE code = :c AND used_at IS NULL RETURNING code"),
        {"u": user_id, "c": c})).scalar_one_or_none()
    if ok is None:
        raise CodeInvalide("Code Pionnier invalide ou déjà utilisé.")
    return ok
