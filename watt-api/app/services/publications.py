"""Définition UNIQUE d'une « œuvre en ligne » (publiée et visible).

Source de vérité partagée par :
  - le tableau de bord de bêta (`beta_dashboard.py`) — c'est elle qui compte les
    « créateurs » (= comptes ayant au moins une œuvre en ligne) ;
  - le programme Pionnier (`pioneer.py`, Brique 2) — un créateur ne devient
    Pionnier que s'il a au moins une œuvre en ligne.
Une seule définition → le chiffre « créateurs » que voit Tom et l'éligibilité
Pionnier ne peuvent pas diverger.

Ce qui compte comme œuvre (une ligne par œuvre, `uid` = créateur) :
  - prompts (dont prompts image et beats, stockés dans la même table),
  - ADN (profil), ADN visuels, voix mises en vente : publiés ET non supprimés ;
  - tracks : non supprimées (pas de drapeau de publication sur cette table).
Ce qui NE compte PAS : albums, playlists et « œuvres » son+image (ce sont des
COLLECTIONS qui regroupent des œuvres déjà comptées), commentaires, messages.

« En ligne » exclut automatiquement ce que la modération a retiré : un retrait
de prompt/image passe `is_published` à false, un retrait de track passe
`is_deleted` à true (cf. moderation.takedown_content). Lot 2 : le retrait pose
aussi `taken_down_at`, exclu EXPLICITEMENT ici — une œuvre retirée ne qualifie
plus jamais personne, même republiée (le trigger 0092 l'en empêche de toute
façon ; double filet).

Date : `created_at`. Il n'existe AUCUNE colonne de date de publication dans le
schéma : un brouillon créé tôt puis publié tard est daté de sa création.
"""

SQL_OEUVRES_EN_LIGNE = """
    SELECT artist_id AS uid, created_at FROM prompts
        WHERE is_published AND NOT is_deleted AND taken_down_at IS NULL
    UNION ALL
    SELECT artist_id, created_at FROM adns
        WHERE is_published AND NOT is_deleted AND taken_down_at IS NULL
    UNION ALL
    SELECT artist_id, created_at FROM visual_adns
        WHERE is_published AND NOT is_deleted AND taken_down_at IS NULL
    UNION ALL
    SELECT artist_id, created_at FROM voices_for_sale
        WHERE is_published AND NOT is_deleted AND taken_down_at IS NULL
    UNION ALL
    SELECT artist_id, created_at FROM tracks
        WHERE NOT is_deleted AND taken_down_at IS NULL
"""
