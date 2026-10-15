"""Forme canonique d'un email (Lot I, anti-comptes multiples).

`Tom.Lecomte+watt@gmail.com` et `tomlecomte@gmail.com` arrivent dans la même
boîte : un seul compte. Règle (identique au remplissage de la migration 0107) :
  - tout en minuscules ;
  - partie locale coupée au premier `+` ;
  - Gmail (`gmail.com`, `googlemail.com`) : points retirés, domaine `gmail.com`.
"""
from __future__ import annotations

_GMAIL = {"gmail.com", "googlemail.com"}


def email_canonique(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    if "@" not in e:
        return None
    local, domaine = e.rsplit("@", 1)
    local = local.split("+", 1)[0]
    if domaine in _GMAIL:
        local = local.replace(".", "")
        domaine = "gmail.com"
    if not local or not domaine:
        return None
    return f"{local}@{domaine}"
