---
title: Roadmap SMYLE PLAY
type: roadmap
tags: [produit, roadmap]
updated: 2026-04-21
---

# Roadmap

## Sprint stabilisation (en cours — 2026-04-21)
Objectif : rendre la prod **sûre** avant toute nouvelle feature.

- [[2026-04-21#2. Protection prod (CI)|CI migrations Alembic]]
- [[2026-04-21#3. Dette Flask legacy|Purge dette Flask UUID]]
- [[2026-04-21#4. Observabilité|Sentry + backups]]
- Tests smoke minimum

Critère de sortie : push bloqué si CI rouge + monitoring actif.

## Sprint suivant — Qualité produit
- Staging env dédié
- OpenAPI doc auto
- Re-seed comptes démo reproductible
- Migration complète Flask → FastAPI des routes actives

## Backlog moyen terme
- PostHog analytics users
- Cloudflare (WAF + cache)
- Marketplace tracks (tables prêtes en DB, pas encore exposées)
- Système de suivi artistes (tables `0014_add_follow_system`)
- Playlists publiques (`0021_add_playlists`)
- **Échange d'ADN entre artistes** (type TCG Pocket) : deux artistes qui se suivent peuvent échanger leurs prompts contre des crédits SMYLES. Prérequis : suivi + messagerie. Table `prompt_trades` dédiée, double validation, prix-plancher en crédits pour éviter le farming. L'échange EST une transaction (respecte la règle "prompt invisible sans transaction").

## Backlog créatif WATT
Voir [[Univers]] et [[Prompts_Suno]].
- Finaliser les 4 albums univers : JUNGLE OSMOSE, NIGHT CITY, SUNSET LOVER, HIT MIX
- Automatiser la génération Suno via skill [[Prompts_Suno]]

## Liens
- [[Dette_technique]]
- [[Bugs_connus]]
- [[2026-04-21_deploy-api]]
