from datetime import datetime, timedelta, timezone

import jwt  # PyJWT (remplace python-jose, CVE-2024-33663/33664, non maintenue)
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.users import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(subject: str, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    # `tv` = version de jeton (durcissement) : recopiée depuis user.token_version,
    # vérifiée à chaque requête. Un reset de mot de passe l'incrémente → révoque
    # les jetons antérieurs.
    payload = {"sub": subject, "exp": expire, "tv": token_version}
    return jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def _decode_claims(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> str | None:
    claims = _decode_claims(token)
    return claims.get("sub") if claims else None


# Lot D — écritures permises tant que les CGU en vigueur ne sont pas acceptées :
# accepter, supprimer son compte (droit RGPD), marquer le guide vu, lire ses
# notifications. Tout le reste (achat, publication, vente, profil…) attend
# l'acceptation. La lecture (GET) n'est jamais bloquée.
_ECRITURES_SANS_CGU = (
    ("POST", "/users/me/accept-terms"),
    ("DELETE", "/users/me"),
    ("POST", "/users/me/delete"),
    ("POST", "/users/me/onboarding"),
)
_PREFIXES_SANS_CGU = ("/notifications",)
_METHODES_ECRITURE = {"POST", "PUT", "PATCH", "DELETE"}


class CguNonAcceptees(HTTPException):
    """403 « accepte les CGU en vigueur » — le corps porte un code stable
    (`code: cgu_a_accepter`) que le front reconnaît pour ouvrir la fenêtre
    d'acceptation (cf. app/main.py, gestionnaire dédié)."""

    def __init__(self) -> None:
        from app.core.legal import CGU_VERSION

        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accepte les nouvelles conditions d'utilisation pour continuer.",
        )
        self.cgu_version = CGU_VERSION


def cgu_a_jour(user: User) -> bool:
    from app.core.legal import CGU_VERSION

    return (getattr(user, "accepted_terms_version", None) or "") == CGU_VERSION


def _ecriture_soumise_aux_cgu(request: Request | None) -> bool:
    if request is None:
        return False
    methode = request.method.upper()
    if methode not in _METHODES_ECRITURE:
        return False
    chemin = request.url.path.rstrip("/") or "/"
    if (methode, chemin) in _ECRITURES_SANS_CGU:
        return False
    return not any(chemin.startswith(p) for p in _PREFIXES_SANS_CGU)


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    claims = _decode_claims(token)
    email = claims.get("sub") if claims else None
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = await get_user_by_email(db, email)
    if user is None:
        raise credentials_exception
    # Révocation (durcissement) : le `tv` du jeton doit correspondre à la
    # version courante du compte. Un jeton sans `tv` vaut 0 (comptes/jetons
    # antérieurs à la fonctionnalité → restent valides jusqu'à expiration).
    if int(claims.get("tv", 0) or 0) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée, reconnecte-toi.",
        )
    # Modération DSA (Phase 3) : un compte banni ne peut plus rien faire
    # d'authentifié, même avec un jeton encore valide.
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte suspendu.",
        )
    # Lot D — CGU en vigueur non acceptées : les actions qui écrivent sont
    # refusées (code `cgu_a_accepter`), la lecture reste possible.
    if not cgu_a_jour(user) and _ecriture_soumise_aux_cgu(request):
        raise CguNonAcceptees()
    # Lot 2 — activité par jour (mesures « prêt à sortir ») : au plus une
    # écriture par compte et par jour, en tâche de fond, jamais bloquante.
    from app.services.activity import note_activity

    note_activity(user.id)
    return user


async def resolve_optional_user(db: AsyncSession, token: str | None) -> User | None:
    """Lot A (M1) — utilisateur courant OPTIONNEL, pour les LECTURES publiques.

    Mêmes contrôles que `get_current_user` (signature, `tv` = version de
    jeton, compte non suspendu) mais renvoie None au lieu de lever : la page
    reste servie comme à un visiteur. Ne JAMAIS s'en servir pour autoriser
    une écriture : utiliser `get_current_user`.
    """
    if not token:
        return None
    claims = _decode_claims(token)
    email = claims.get("sub") if claims else None
    if not email:
        return None
    try:
        user = await get_user_by_email(db, email)
    except Exception:  # noqa: BLE001 — une lecture publique ne casse jamais
        return None
    if user is None:
        return None
    if int(claims.get("tv", 0) or 0) != int(user.token_version or 0):
        return None
    if user.is_banned:
        return None
    return user


def bearer_from_request(request) -> str | None:
    """Jeton Bearer de l'en-tête Authorization, ou None."""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    return auth[7:].strip() or None
