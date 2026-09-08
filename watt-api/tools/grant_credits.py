"""
Cherche un compte et le crédite en Smyles, sans passer par HTTP.

B1 / annexe B §2. Complément machine d'ops de K-02 : l'endpoint
`POST /admin/users/{user_id}/credits` exige un UUID, et jusqu'ici rien ne
l'exposait. Cet outil fait les deux gestes — trouver, puis créditer — depuis
la même ligne de commande, sur le même chemin que l'API : `grant_credits_atomic`
(transaction `grant`, bucket `promo`, ledger append-only). AUCUNE écriture
directe sur `users.credits_balance` ici, jamais.

Comme `make_admin.py`, il lit DATABASE_URL via app.config (donc la base
pointée par watt-api/.env) et dit explicitement ce qu'il a fait.

USAGE
─────
    python tools/grant_credits.py --find marie              # cherche (lecture seule)
    python tools/grant_credits.py --find ""                 # 20 derniers inscrits
    python tools/grant_credits.py marie@example.com  --credits 500 --reason "beta_tester"
    python tools/grant_credits.py <UUID>             --credits 500 --reason "beta_tester"
    python tools/grant_credits.py marie@example.com  --credits 500 --reason "x" --dry-run

`--reason` est OBLIGATOIRE pour créditer : c'est ce qui atterrit dans le
ledger, et un grant sans motif est un trou dans l'audit.

⚠️ Un crédit n'est PAS idempotent : rejouer la commande crédite une seconde
fois. L'outil est idempotent dans son AFFICHAGE — il imprime le solde avant,
le solde après et l'id de la transaction, pour qu'on voie sans ambiguïté ce
qui vient de se passer. Utiliser --dry-run pour vérifier la cible d'abord.

Sortie : 0 si l'action demandée a abouti, 1 sinon (compte introuvable,
ambigu, banni, supprimé).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import func, or_, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.transaction import TransactionType  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.credits import grant_credits_atomic  # noqa: E402

# Même suffixe que routers/admin.py (anonymisation RGPD).
_DELETED_EMAIL_SUFFIX = "@deleted.watt"

_DEFAULT_LIMIT = 20


def _patterns(q: str) -> list[str]:
    """Motifs ILIKE — mêmes variantes que GET /admin/users (le slug public
    n'est pas une colonne : « marie-dupont » doit matcher « Marie Dupont »)."""
    base = (q or "").strip()
    variants = {base, base.replace("-", " ").replace("_", " "), base.replace(" ", "-")}
    return [f"%{v}%" for v in variants if v]


def _flags(u: User) -> str:
    out = []
    if u.is_banned:
        out.append("BANNI")
    if str(u.email or "").endswith(_DELETED_EMAIL_SUFFIX):
        out.append("SUPPRIMÉ")
    if u.is_admin or u.is_official:
        out.append("admin")
    if u.profile_public:
        out.append("publié")
    return ",".join(out) or "-"


def _print_rows(rows: list[User]) -> None:
    print(f"{'EMAIL':<40}{'PSEUDO':<20}{'SMYLES':>8}  {'INSCRIT':<12}{'ÉTAT':<22}ID")
    print("-" * 132)
    for u in rows:
        created = u.created_at.strftime("%Y-%m-%d") if u.created_at else "?"
        print(
            f"{(u.email or '')[:39]:<40}{(u.artist_name or '')[:19]:<20}"
            f"{int(u.credits_balance or 0):>8}  {created:<12}{_flags(u):<22}{u.id}"
        )


async def find(q: str, limit: int) -> int:
    async with SessionLocal() as db:
        stmt = select(User)
        pats = _patterns(q)
        if pats:
            stmt = stmt.where(
                or_(
                    *[User.email.ilike(p) for p in pats],
                    *[User.artist_name.ilike(p) for p in pats],
                )
            )
        rows = (
            await db.execute(stmt.order_by(User.created_at.desc()).limit(limit))
        ).scalars().all()
    if not rows:
        print(f"Aucun compte pour {q!r}.")
        return 1
    print(f"{len(rows)} compte(s) — les plus récents d'abord :")
    _print_rows(rows)
    return 0


async def _resolve(db, target: str) -> User | None:
    """UUID exact, puis email exact (insensible à la casse), puis recherche
    partielle si et seulement si elle ne ramène qu'un seul compte."""
    raw = (target or "").strip()
    try:
        uid = UUID(raw)
    except (ValueError, AttributeError):
        uid = None
    if uid is not None:
        return (await db.execute(select(User).where(User.id == uid))).scalars().first()

    exact = (
        await db.execute(select(User).where(func.lower(User.email) == raw.lower()))
    ).scalars().first()
    if exact is not None:
        return exact

    pats = _patterns(raw)
    if not pats:
        return None
    rows = (
        await db.execute(
            select(User).where(
                or_(
                    *[User.email.ilike(p) for p in pats],
                    *[User.artist_name.ilike(p) for p in pats],
                )
            ).limit(11)
        )
    ).scalars().all()
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        print(
            f"ERREUR : {len(rows)} comptes correspondent à {raw!r} — "
            "précise l'email complet ou l'identifiant.",
            file=sys.stderr,
        )
        _print_rows(rows[:10])
    return None


async def grant(target: str, credits: int, reason: str, by: str | None, dry_run: bool) -> int:
    async with SessionLocal() as db:
        user = await _resolve(db, target)
        if user is None:
            print(f"ERREUR : aucun compte pour {target!r}.", file=sys.stderr)
            return 1

        # Mêmes refus que l'API (routers/admin.py) : on ne crédite pas un
        # compte suspendu ni un compte anonymisé.
        if user.is_banned:
            print(
                f"REFUS : {user.email} est BANNI (id={user.id}) — aucun crédit accordé.",
                file=sys.stderr,
            )
            return 1
        if str(user.email or "").endswith(_DELETED_EMAIL_SUFFIX):
            print(
                f"REFUS : {user.email} est un compte SUPPRIMÉ (id={user.id}) — "
                "aucun crédit accordé.",
                file=sys.stderr,
            )
            return 1

        before = int(user.credits_balance or 0)
        label = f"{user.email} (pseudo={user.artist_name or '-'}, id={user.id})"

        if dry_run:
            print(f"[dry-run] Cible : {label}")
            print(f"[dry-run] Solde {before} → {before + credits} (+{credits} promo)")
            print(f"[dry-run] Motif : {reason!r} — RIEN n'a été écrit.")
            return 0

        meta = {"source": "admin_cli", "reason_cli": reason}
        if by:
            operator = (
                await db.execute(select(User).where(func.lower(User.email) == by.strip().lower()))
            ).scalars().first()
            if operator is None:
                print(f"ERREUR : --by {by!r} : compte inconnu.", file=sys.stderr)
                return 1
            meta["granted_by"] = str(operator.id)
            meta["granted_by_email"] = operator.email

        try:
            tx = await grant_credits_atomic(
                db=db,
                user_id=user.id,
                amount=credits,
                reason=reason,
                tx_type=TransactionType.GRANT,
                metadata=meta,
            )
            await db.commit()
            await db.refresh(tx)
            tx_id = tx.id
        except ValueError as e:
            await db.rollback()
            print(f"ERREUR : {e}", file=sys.stderr)
            return 1

        after = (
            await db.execute(select(User.credits_balance).where(User.id == user.id))
        ).scalar_one()

    print(f"CRÉDITÉ : {label}")
    print(f"  +{credits} Smyles (bucket promo) — solde {before} → {after}")
    print(f"  motif : {reason!r}")
    print(f"  transaction : {tx_id} (type=grant, ledger append-only)")
    print("  ⚠️ rejouer cette commande créditerait à nouveau.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cherche un compte WATT et le crédite en Smyles (ledger applicatif)."
    )
    ap.add_argument("target", nargs="?", help="Email ou identifiant du compte à créditer.")
    ap.add_argument("--find", dest="find_q", default=None,
                    help="Mode recherche (lecture seule) : email, pseudo ou slug, partiel.")
    ap.add_argument("--credits", type=int, default=None, help="Nombre de Smyles (1..10000).")
    ap.add_argument("--reason", default=None, help="Motif — OBLIGATOIRE, tracé au ledger.")
    ap.add_argument("--by", default=None, help="Email de l'admin qui accorde (tracé au ledger).")
    ap.add_argument("--limit", type=int, default=_DEFAULT_LIMIT, help="Résultats de --find.")
    ap.add_argument("--dry-run", action="store_true", help="Montre la cible sans rien écrire.")
    args = ap.parse_args()

    if args.find_q is not None:
        return asyncio.run(find(args.find_q, max(1, min(args.limit, 100))))

    if not args.target:
        ap.error("cible requise (email ou identifiant), ou --find")
    if args.credits is None:
        ap.error("--credits requis")
    if not 1 <= args.credits <= 10000:
        ap.error("--credits doit être entre 1 et 10000")
    if not (args.reason or "").strip():
        ap.error("--reason requis (motif obligatoire, tracé au ledger)")
    if len(args.reason) > 500:
        ap.error("--reason : 500 caractères maximum")

    return asyncio.run(
        grant(args.target, args.credits, args.reason.strip(), args.by, args.dry_run)
    )


if __name__ == "__main__":
    raise SystemExit(main())
