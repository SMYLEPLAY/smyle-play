# _archive_bak

Anciennes versions de fichiers (`.bak`) sauvegardées avant les changements Phase 9.

Déplacées ici le 2026-04-18 pendant la consolidation session Cowork.

Contenu :
- `__init__.py.bak` — version pré-Phase 9 du package models (sans Achievement, Adn, OwnedAdn, Prompt, UnlockedPrompt).
- `transaction.py.bak` — version sans le fix `values_callable` sur les SQLEnum Transaction.type/status.
- `user.py.bak` — version sans `brand_color`, sans les CheckConstraints credits_balance/earned_total, sans les defaults, sans le commentaire de section.
- `docker-compose.yml.bak` — version sans le volume hot-reload `.:/app` ni le flag `--reload`.

Conservés par prudence. Peuvent être supprimés sans risque car :
1. Les versions actuelles sont valides (1618 tests OK).
2. Git garde de toute façon l'historique.
