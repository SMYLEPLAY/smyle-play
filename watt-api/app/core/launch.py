"""
Gates API du MODE LANCEMENT (S-08, audit A §M8).

Le mode lancement masquait les mécaniques non ouvertes (revente, packs, troc,
voix, THE PLAN) **côté front seulement** : les routeurs `resale`, `packs`,
`trades` et `voices` étaient montés inconditionnellement, donc leurs mutations
d'argent restaient appelables en direct avec un jeton valide (curl, console).
Seul `the_plan` était conditionné — mais par un montage évalué **au boot**,
donc non rallumable sans redéploiement.

`require_launch_item` unifie les deux : une dépendance FastAPI qui relit
`settings.launch_flags_dict()` à CHAQUE requête. Un item masqué répond 404
(pas 403 : on ne révèle pas l'existence de la fonction). Rallumage par simple
variable d'environnement (`MODE_LANCEMENT=False` ou `SHOW_<ITEM>=True`), sans
redéploiement de code, et monkeypatch-able en test.
"""
from fastapi import HTTPException, status

from app.config import settings


def require_launch_item(item: str):
    """Dépendance FastAPI : 404 tant que `item` est masqué par le MODE LANCEMENT.

    `item` est une clé de `settings.launch_flags_dict()` : "resale", "packs",
    "voix", "troc", "thePlan", "paliers".
    """

    async def _dep() -> None:
        # Lu à chaque requête (et non au montage) : rallumable par env seule.
        if not settings.launch_flags_dict()[item]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fonction indisponible pendant le lancement.",
            )

    return _dep
