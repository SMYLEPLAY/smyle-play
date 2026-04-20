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
