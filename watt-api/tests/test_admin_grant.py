"""K-02 (2026-09-04) — crédit admin d'un compte tiers (annexe B §2 / B-M1).

Avant : aucun moyen de créditer un testeur. `POST /credits/grant` ne crédite
que l'appelant (`user_id=current_user.id`, schéma `extra="forbid"`), et le
routeur `admin.py` n'était jamais monté → `/admin/*` en 404. La seule voie
était du SQL manuel, hors ledger applicatif et sans trace de l'auteur.

On vérifie ici la garde, l'effet économique (solde, bucket promo, invariant
des buckets), l'audit (ligne `grant` avec `granted_by`), les bornes et la
lecture `GET /admin/grants`.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update

from app.database import SessionLocal
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import user_bucket_consistent
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _set_flags(user_id, **values) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(**values))
        await db.commit()


async def _wallet(uid):
    async with SessionLocal() as db:
        return (await db.execute(
            text(
                "SELECT credits_balance, smyles_promo, smyles_achetes, smyles_gagnes "
                "FROM users WHERE id = :uid"
            ),
            {"uid": uid},
        )).first()


@pytest_asyncio.fixture(loop_scope="session")
async def admin_headers(test_user: dict, auth_headers: dict):
    """Le user de test devient admin via `is_admin` (K-01)."""
    await _set_flags(test_user["id"], is_admin=True)
    try:
        yield auth_headers
    finally:
        await _set_flags(test_user["id"], is_admin=False)


@pytest_asyncio.fixture(loop_scope="session")
async def target_user():
    """Bénéficiaire du crédit — un compte distinct de l'admin."""
    email = f"pytest-k02-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    try:
        yield {"id": uid, "email": email}
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


# ── Garde ──────────────────────────────────────────────────────────────────

async def test_non_admin_403(client: AsyncClient, auth_headers: dict, target_user: dict):
    r = await client.post(
        f"/admin/users/{target_user['id']}/credits",
        json={"credits": 10, "reason": "test"},
        headers=auth_headers,
    )
    assert r.status_code == 403, r.text


# ── Chemin nominal ─────────────────────────────────────────────────────────

async def test_grant_credite_le_tiers_en_promo_et_trace_l_auteur(
    client: AsyncClient, admin_headers: dict, test_user: dict, target_user: dict
):
    uid = target_user["id"]
    before = await _wallet(uid)
    reason = f"beta_tester_{uuid.uuid4().hex[:6]}"

    r = await client.post(
        f"/admin/users/{uid}/credits",
        json={"credits": 500, "reason": reason},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "grant"
    assert body["status"] == "completed"
    assert body["credits_amount"] == 500

    after = await _wallet(uid)
    assert after.credits_balance == before.credits_balance + 500
    assert after.smyles_promo == before.smyles_promo + 500  # non encaissable
    assert after.smyles_achetes == before.smyles_achetes
    assert after.smyles_gagnes == before.smyles_gagnes

    async with SessionLocal() as db:
        assert await user_bucket_consistent(db, uid) is True
        rows = (await db.execute(
            select(Transaction).where(
                Transaction.buyer_id == uid,
                Transaction.type == TransactionType.GRANT,
            )
        )).scalars().all()
    assert len(rows) == 1
    meta = rows[0].metadata_json or {}
    assert meta["reason"] == reason
    assert meta["granted_by"] == str(test_user["id"])
    assert meta["granted_by_email"] == test_user["email"]
    assert meta["source"] == "admin_grant"

    # L'admin n'est pas crédité par ricochet.
    admin_wallet = await _wallet(test_user["id"])
    assert admin_wallet.smyles_promo < after.smyles_promo


# ── Erreurs ────────────────────────────────────────────────────────────────

async def test_utilisateur_inconnu_404(client: AsyncClient, admin_headers: dict):
    r = await client.post(
        f"/admin/users/{uuid.uuid4()}/credits",
        json={"credits": 10, "reason": "x"},
        headers=admin_headers,
    )
    assert r.status_code == 404, r.text


async def test_compte_banni_400(
    client: AsyncClient, admin_headers: dict, target_user: dict
):
    await _set_flags(target_user["id"], is_banned=True)
    try:
        r = await client.post(
            f"/admin/users/{target_user['id']}/credits",
            json={"credits": 10, "reason": "x"},
            headers=admin_headers,
        )
        assert r.status_code == 400, r.text
    finally:
        await _set_flags(target_user["id"], is_banned=False)


@pytest.mark.parametrize(
    "payload",
    [
        {"credits": 0, "reason": "x"},           # borne basse
        {"credits": 10001, "reason": "x"},       # borne haute
        {"credits": 10},                          # raison obligatoire
        {"credits": 10, "reason": ""},            # raison vide
        {"credits": 10, "reason": "x" * 501},     # raison trop longue
        {"credits": 10, "reason": "x", "user_id": "autre"},  # extra="forbid"
    ],
)
async def test_bornes_422(
    client: AsyncClient, admin_headers: dict, target_user: dict, payload: dict
):
    r = await client.post(
        f"/admin/users/{target_user['id']}/credits",
        json=payload,
        headers=admin_headers,
    )
    assert r.status_code == 422, r.text


# ── Lecture ────────────────────────────────────────────────────────────────

async def test_get_grants_liste(
    client: AsyncClient, admin_headers: dict, auth_headers: dict, target_user: dict
):
    reason = f"lecture_{uuid.uuid4().hex[:6]}"
    r = await client.post(
        f"/admin/users/{target_user['id']}/credits",
        json={"credits": 7, "reason": reason},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text

    r = await client.get("/admin/grants?limit=50", headers=admin_headers)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    mine = [i for i in items if (i.get("metadata_json") or {}).get("reason") == reason]
    assert len(mine) == 1
    assert mine[0]["type"] == "grant"
    assert mine[0]["buyer_id"] == str(target_user["id"])
    assert (mine[0]["metadata_json"] or {})["source"] == "admin_grant"


async def test_get_grants_non_admin_403(client: AsyncClient, auth_headers: dict):
    r = await client.get("/admin/grants", headers=auth_headers)
    assert r.status_code == 403, r.text
