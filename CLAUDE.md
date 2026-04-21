## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

## Navigation dans le contexte

Quand tu as besoin de comprendre le code, les docs, ou les fichiers de ce projet :
1. TOUJOURS interroger le graphe de connaissance en premier : `/graphify query "ta question"`
2. Ne lis les fichiers bruts que si je dis explicitement "lis le fichier" ou "regarde le fichier brut"
3. Utiliser `graphify-out/wiki/index.md` comme point d'entrée pour naviguer dans la structure

## Obsidian vault (docs stratégiques / produit / créatif)

Le dossier `OBSIDIAN/` est un vault Obsidian. Règles :

- **Tout nouveau document stratégique, produit, créatif, session, tâche → dans `OBSIDIAN/`**, jamais à la racine du projet.
- Utiliser la syntaxe Obsidian native : `[[wikilinks]]`, tags `#produit` `#technique` `#watt` `#session` `#task` `#bug` `#dette` `#bloquant`, frontmatter YAML avec `title / type / tags / updated`.
- Ne **pas** cartographier le code dans Obsidian → c'est le rôle de `graphify-out/`.
- Point d'entrée vault : `OBSIDIAN/00_INDEX.md`.
- Arborescence imposée :
  - `01_PRODUIT/` → roadmap, dette, bugs (stratégie)
  - `02_WATT/` → univers, prompts Suno, artistes, tracks (créatif)
  - `03_SESSIONS/` → récaps datés `YYYY-MM-DD_<sujet>.md`
  - `04_TASKS/` → plans du jour `YYYY-MM-DD.md`
  - `05_TECH/Runbooks/` → procédures actionnables (deploy, watcher, mapping)
  - `05_TECH/Legacy/` → ancien vault Flask (lecture seule, tagué `#legacy`)
  - `99_ARCHIVE/` → anciens handoffs, états historiques, zips
- Le `README.md` racine s'adresse aux humains, le `CLAUDE.md` à toi (IA). Les deux coexistent.

## Autres conventions repo

- `data/config/` → constantes statiques JSON (univers, styles). Source lecture pour seeds et skill `watt-prompt`.
- `data/seeds/` → scripts Python d'init DB (idempotents).
- `data/exports/` → dumps et exports temporaires (gitignored).
- `scripts/` → shell scripts (`.sh`) de déploiement / setup.
- `assets_audio/` → audio brut par univers, gitignored (hébergé Cloudflare R2).
- Quand je crée un doc stratégique, toujours le relier par wikilink depuis `00_INDEX.md` ou une note parente existante.
