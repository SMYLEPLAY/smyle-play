"""Compat shim + dépendances d'autorisation.

Ré-export historique : les routers Phase 9 (catalog, library, marketplace,
unlocks) ont été écrits avec `from app.auth.dependencies import
get_current_user`. Cette convention venait d'un refactor planifié
(sub=user_id) jamais terminé côté projet Tom. Comme Tom a déjà un
get_current_user fonctionnel dans jwt.py (sub=email), on l'expose simplement
ici pour éviter de toucher 7 routers.

K-01 (2026-09-04, annexe B §2) — garde d'administration unique. Avant, chaque
routeur testait `current_user.is_official` dans son coin (reports.py,
users.py, credits.py, telemetry.py) : quatre copies de la même règle, et un
seul compte au monde pouvait la satisfaire — le compte vitrine « Smyle »,
dont le mot de passe est aléatoire et inconnu. Résultat : aucune action
d'administration n'était réalisable. On centralise ici, et on accepte
`is_official` OU `is_admin` (le nouveau rôle, sans effet d'interface).
"""
from fastapi import Depends, HTTPException, status

from app.auth.jwt import get_current_user
from app.models.user import User

__all__ = ["get_current_user", "is_admin_user", "require_admin"]

# Message unique : ne distingue pas « pas admin » de « pas connecté » côté
# contenu, et reste en français comme le reste des erreurs métier.
ADMIN_FORBIDDEN_DETAIL = "Réservé à l'administration"


def is_admin_user(user: User) -> bool:
    """Vrai si l'utilisateur porte un droit d'administration.

    `is_official` reste accepté pour ne casser aucun accès existant (le
    compte vitrine « Smyle » était la seule garde jusqu'ici).
    """
    return bool(getattr(user, "is_official", False) or getattr(user, "is_admin", False))


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dépendance FastAPI : renvoie l'utilisateur courant s'il est admin,
    sinon 403. Drop-in pour `Depends(get_current_user)` dans les endpoints
    d'administration."""
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ADMIN_FORBIDDEN_DETAIL,
        )
    return current_user
