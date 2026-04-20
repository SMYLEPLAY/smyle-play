"""Compat shim: ré-exporte get_current_user depuis app.auth.jwt.

Les routers Phase 9 (catalog, library, marketplace, unlocks) ont été écrits
avec l'import `from app.auth.dependencies import get_current_user`. Cette
convention venait d'un refactor planifié (sub=user_id) jamais terminé côté
projet Tom. Comme Tom a déjà un get_current_user fonctionnel dans jwt.py
(sub=email), on l'expose simplement ici pour éviter de toucher 7 routers.

Si un jour le refactor sub=user_id est fait, il suffira de remplacer
le contenu de ce fichier par la vraie implémentation UUID-based.
"""
from app.auth.jwt import get_current_user

__all__ = ["get_current_user"]
