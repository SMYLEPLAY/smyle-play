# .relay/ — File de déploiement autonome

Mécanisme du **relais** entre le sandbox (où Claude code, mais ne peut pas pousser)
et GitHub/Railway. Voir le runbook : `OBSIDIAN/05_TECH/Runbooks/2026-06-22_systeme-dev-autonome.md`.

## Comment ça marche

1. **Claude (sandbox)** prépare des changements, puis lance
   `scripts/smyle-enqueue.sh <branche> "<titre>"`.
   → la branche est committée et une tâche est déposée dans `queue/`.
2. **Le relais (Mac, `scripts/smyle-relay.sh`)** — lancé en continu par le
   LaunchAgent `com.smyleplay.relay.plist` :
   - `queue/`  → pousse la branche + ouvre la PR → déplace vers `pushed/`
   - `pushed/` → vérifie la CI ; si **verte** → merge (Railway déploie) →
     `done/` ; si **rouge** → `failed/` (escalade) ; si en cours → attend.

## Dossiers

| Dossier   | Contenu |
|-----------|---------|
| `queue/`  | tâches en attente de push (écrites par `smyle-enqueue.sh`) |
| `pushed/` | PR ouvertes, en attente de CI |
| `done/`   | mergées + déployées |
| `failed/` | CI rouge ou PR fermée → action requise |

## Contrôles

- **Pause** : créer un fichier vide `.relay/PAUSE` → le relais ne fait plus rien.
  Reprendre : supprimer `.relay/PAUSE`.
- **Merge admin** (bypass protection, après CI vérifiée verte) : lancer le relais
  avec `RELAY_ADMIN=1`. Désactivé par défaut.
- **Journal** : `.relay/relay.log` (+ `launchd.out.log` / `launchd.err.log`).

Les dossiers d'état et les logs sont locaux (gitignorés). Seul ce README est versionné.
