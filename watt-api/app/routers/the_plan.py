"""
Router THE PLAN — produit éditorial digital (pack PDF officiel par Smyle).

Deux éditions vendues en Smyles (jamais en €) :
  - "ia"      → THE PLAN — Édition IA  (produit phare WATT)
  - "classic" → THE PLAN — Édition classique (artistes physiques)

Prix : 35 Smyles (barré 70). Conversion sur EUR_PER_CREDIT = 0,70 €/Smyle.

Endpoints :
  GET  /products/the-plan/{edition}                   → infos + possession (auth)
  POST /products/the-plan/{edition}/buy               → débite, débloque (auth)
  GET  /products/the-plan/{edition}/download/{slug}   → PDF gaté (lien signé)

Possession persistée SANS migration : `download_events` (product_id = UUID
namespace fixe par édition, kind='the_plan:<edition>'). Débit via le helper
atomique existant `debit_with_priority`. Liens de téléchargement signés HMAC
(SECRET_KEY) → fonctionnent depuis un simple <a href>.
"""
import hashlib
import hmac
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.launch import require_launch_item
from app.auth.dependencies import get_current_user
from app.config import settings
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.download_event import DownloadEvent
from app.models.user import User
from app.services.credits import debit_with_priority

# S-08 (2026-09-02) — MODE LANCEMENT gaté côté API : tant que l'item est
# masqué, toutes les routes de ce routeur répondent 404 (audit A §M8).
router = APIRouter(
    prefix="/products/the-plan",
    tags=["the-plan"],
    dependencies=[Depends(require_launch_item("thePlan"))],
)

PRICE = 35           # Smyles — prix réel
PRICE_STRIKE = 70    # Smyles — prix barré (−50 %)
_TOKEN_TTL = 7 * 24 * 3600

_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "the-plan"

# slug public → (fichier, libellé) — commun aux deux éditions
FILES: dict[str, tuple[str, str]] = {
    "welcome":         ("01_WELCOME.pdf",         "01 · Welcome"),
    "the-plan":        ("02_THE_PLAN.pdf",        "02 · The Plan"),
    "fiche-technique": ("03_FICHE_TECHNIQUE.pdf", "03 · Fiche technique"),
}

# édition → métadonnées
EDITIONS: dict[str, dict] = {
    "ia": {
        "label": "Édition IA",
        "dir": "ia",
        "product_id": uuid.uuid5(uuid.NAMESPACE_URL, "smyle:product:the-plan:ia"),
    },
    "classic": {
        "label": "Édition classique",
        "dir": "classic",
        "product_id": uuid.uuid5(uuid.NAMESPACE_URL, "smyle:product:the-plan:classic"),
    },
}


def _edition_or_404(edition: str) -> dict:
    ed = EDITIONS.get(edition)
    if ed is None:
        raise HTTPException(status_code=404, detail="Édition inconnue.")
    return ed


def _kind(edition: str) -> str:
    return f"the_plan:{edition}"


# ── Signature des liens ──────────────────────────────────────────────────────
def _sign(user_id: uuid.UUID, edition: str, slug: str, exp: int) -> str:
    msg = f"{user_id}:{edition}:{slug}:{exp}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def _make_url(user_id: uuid.UUID, edition: str, slug: str) -> str:
    exp = int(time.time()) + _TOKEN_TTL
    sig = _sign(user_id, edition, slug, exp)
    return f"/products/the-plan/{edition}/download/{slug}?u={user_id}&exp={exp}&sig={sig}"


def _files_payload(user_id: uuid.UUID, edition: str) -> list[dict]:
    return [
        {"slug": slug, "name": label, "url": _make_url(user_id, edition, slug)}
        for slug, (_, label) in FILES.items()
    ]


# ── Possession ───────────────────────────────────────────────────────────────
async def _owns(db: AsyncSession, user_id: uuid.UUID, ed: dict) -> bool:
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM download_events "
                "WHERE user_id = :u AND product_id = :p AND kind = :k LIMIT 1"
            ),
            {"u": user_id, "p": ed["product_id"], "k": _kind(ed["dir"])},
        )
    ).first()
    return row is not None


@router.get("/{edition}")
async def the_plan_info(
    edition: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ed = _edition_or_404(edition)
    owned = await _owns(db, current_user.id, ed)
    return {
        "product": "the_plan",
        "edition": edition,
        "label": ed["label"],
        "price": PRICE,
        "price_strike": PRICE_STRIKE,
        "owned": owned,
        "files": _files_payload(current_user.id, edition) if owned else None,
    }


@router.post("/{edition}/buy")
@limiter.limit(LIMIT_PURCHASE)
async def buy_the_plan(
    edition: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ed = _edition_or_404(edition)
    if await _owns(db, current_user.id, ed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "already_owned", "message": f"Tu possèdes déjà THE PLAN ({ed['label']})."},
        )
    try:
        await debit_with_priority(db, current_user.id, PRICE)
    except ValueError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "insufficient_credits",
                "message": f"Il te faut {PRICE} Smyles.",
                "required": PRICE,
            },
        )
    db.add(DownloadEvent(user_id=current_user.id, product_id=ed["product_id"], kind=_kind(ed["dir"])))
    await db.commit()
    return {
        "product": "the_plan",
        "edition": edition,
        "price_paid": PRICE,
        "owned": True,
        "files": _files_payload(current_user.id, edition),
    }


@router.get("/{edition}/download/{slug}")
async def download_the_plan(
    edition: str,
    slug: str,
    request: Request,
    u: str | None = None,
    exp: int | None = None,
    sig: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    ed = _edition_or_404(edition)
    entry = FILES.get(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail="Fichier inconnu.")
    filename, _label = entry

    if not (u and exp and sig):
        raise HTTPException(status_code=401, detail="Lien non signé.")
    if exp < int(time.time()):
        raise HTTPException(status_code=403, detail="Lien expiré — rouvre la boutique.")
    if not hmac.compare_digest(sig, _sign(uuid.UUID(u), edition, slug, exp)):
        raise HTTPException(status_code=403, detail="Lien invalide.")
    if not await _owns(db, uuid.UUID(u), ed):
        raise HTTPException(status_code=403, detail="Achat requis.")

    path = _ASSETS / ed["dir"] / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Fichier indisponible.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
