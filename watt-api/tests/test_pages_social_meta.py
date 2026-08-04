"""F1-1 — apercu social (Open Graph / Twitter Card) sur les pages partagees.

Le modele d'acquisition est creator-led : un createur partage /u/<slug> ou
/oeuvre/<slug> sur ses reseaux. Sans balises og:, le lien s'affiche nu.

Tests STRICTEMENT sans base : helpers purs + presence des routes. Voir la
note de la section « Routes » plus bas pour la raison — elle est importante.
"""

from app.routers.pages import (
    _absolute,
    _clip,
    _social_head,
    _tag,
    router,
)


# ── Helpers purs ───────────────────────────────────────────────────────────

def test_tag_echappe_les_guillemets():
    out = _tag("og:title", 'Rock "n" roll & co')
    assert 'content="Rock &quot;n&quot; roll &amp; co"' in out
    assert out.startswith('<meta property="og:title"')


def test_tag_vide_ne_produit_rien():
    assert _tag("og:image", None) == ""
    assert _tag("og:image", "") == ""


def test_clip_tronque_et_normalise():
    assert _clip("  a\n\n  b ") == "a b"
    assert _clip("x" * 300).endswith("…")
    assert len(_clip("x" * 300)) <= 158
    assert _clip(None) == ""


def test_absolute_conserve_les_urls_completes():
    class _Req:
        headers = {"x-forwarded-proto": "https", "host": "watt.test"}

        class url:
            scheme = "https"
            netloc = "watt.test"

    assert _absolute(_Req(), "https://cdn.test/a.png") == "https://cdn.test/a.png"
    assert _absolute(_Req(), "/media/a.png") == "https://watt.test/media/a.png"
    assert _absolute(_Req(), "media/a.png") == "https://watt.test/media/a.png"
    assert _absolute(_Req(), None) is None


def test_social_head_degrade_en_summary_sans_image():
    head = _social_head(
        title="T", description="D", url="https://watt.test/u/x", image=None
    )
    assert 'name="twitter:card" content="summary"' in head
    assert "og:image" not in head
    assert 'property="og:title" content="T"' in head


def test_social_head_large_image_si_image():
    head = _social_head(
        title="T",
        description="D",
        url="https://watt.test/u/x",
        image="https://cdn.test/a.png",
    )
    assert 'content="summary_large_image"' in head
    assert 'property="og:image" content="https://cdn.test/a.png"' in head


# ── Routes (sans base de donnees) ──────────────────────────────────────────
#
# On NE fait PAS d'appel HTTP sur /u/<slug>, /@<slug> ni /oeuvre/<slug> dans
# cette suite. Ces routes ouvrent leur propre session (SessionLocal) pour lire
# les metadonnees ; declenchees depuis un client de test, elles laissaient la
# suite dans un etat ou TOUS les fichiers suivants par ordre alphabetique
# echouaient en cascade (playlists, reports, reserve, smyle_buckets, tiers,
# tracks, users) avec des MissingGreenlet — constate deux fois en CI le
# 2026-08-05 (PR #487 puis #488), avec TestClient comme avec AsyncClient.
#
# L'interaction exacte n'est pas elucidee et merite une investigation a part
# (voir OBSIDIAN — une route qui ouvre une session hors `get_db` est aussi un
# risque de fuite de connexion en production). En attendant, on verifie ce qui
# compte vraiment sans toucher la base : que les routes EXISTENT, et que les
# balises sont bien fabriquees par les helpers (couverts plus haut).

def _chemins() -> set[str]:
    return {getattr(r, "path", None) for r in router.routes}


def test_route_profil_existe():
    assert "/u/{slug}" in _chemins()
    assert "/@{slug}" in _chemins()


def test_route_oeuvre_existe():
    # Regression P0-b : /oeuvre/<slug> n'avait plus de route de page -> 404
    # depuis le 30/07, alors que c'est la page qu'un createur partage.
    assert "/oeuvre/{slug}" in _chemins()


def test_page_index_existe():
    assert "/" in _chemins()
