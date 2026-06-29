"""A4 — cockpit économique : la donnée agrégée a la bonne forme."""
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.services.dashboard import eco_cockpit_data


async def test_eco_cockpit_data_shape():
    async with SessionLocal() as db:
        d = await eco_cockpit_data(db)
    # Solvabilité
    assert "solvabilite" in d
    assert d["solvabilite"]["zone"] in {"🟢", "🟠", "🔴", "⚫"}
    assert "cashable_debt_cents" in d["solvabilite"]
    assert set(d["solvabilite"]["reserve_cents"].keys()) == {
        "payout", "tax", "refund", "cash"
    }
    # Circulation
    circ = d["smyles_en_circulation"]
    assert set(circ.keys()) == {"achetes", "gagnes", "promo", "total"}
    assert circ["total"] == circ["achetes"] + circ["gagnes"] + circ["promo"]
    # Méta
    assert isinstance(d["comptes"], int)
    assert isinstance(d["incoherences_buckets"], int)
    # Business (post-Stripe)
    assert d["business"]["mrr_cents"] == 0
