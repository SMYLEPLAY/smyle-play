"""Constantes légales partagées (Lot D — conformité DSA / RGPD).

`CGU_VERSION` : version des conditions d'utilisation en vigueur. Elle est
enregistrée sur le compte à l'inscription et à chaque ré-acceptation
(`users.accepted_terms_version`). Un compte dont la version diffère doit
accepter les nouvelles conditions avant toute action qui écrit (achat,
publication, vente…) ; la lecture reste possible.

Changer cette date = demander à TOUS les comptes d'accepter à nouveau.
La page /legal porte la même date (texte rédigé à part).

`CONTACT_EMAIL` : adresse de recours indiquée dans les décisions de
modération (DSA art. 17 et 20) et dans le pied de page. Elle figure déjà en
clair dans le front (ui/modals/contact.js).
"""

CGU_VERSION = "2026-11-01"

CONTACT_EMAIL = "smyletheplan@gmail.com"

# Code d'erreur renvoyé (403) quand les CGU en vigueur n'ont pas été acceptées.
CODE_CGU_A_ACCEPTER = "cgu_a_accepter"

# Durée de conservation des données de mesure d'audience (CNIL : 13 mois max).
MESURE_RETENTION_MOIS = 13
