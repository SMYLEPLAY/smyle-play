"""Garde-fou XSS front — S-01 (2026-09-04), plan de finition sécurité.

Le front vanilla construit son HTML en `innerHTML` avec des gabarits, et
chaque module porte son propre échappeur local. L'audit du 02/09 (annexe A
§B1, §B2, « Autres injections ») a trouvé quatre XSS stockés qui reposaient
tous sur le même défaut : un échappeur qui ne traite pas les guillemets.

    - `div.textContent = s; return div.innerHTML` n'échappe que & < > : une
      valeur posée dans un attribut (`src="…"`, `onclick="…('…')"`) en sort
      avec un simple `"` ou `'`.
    - `String(s).replace(/</g, '&lt;')` seul : même chose, en pire.
    - certaines interpolations n'appelaient aucun échappeur (`src="${p.audio_url}"`,
      `${track.name}`).

Ce test parcourt `ui/**/*.js` et les JS racine (comme
`test_repo_public_hygiene.py`) et refuse ces trois formes. La référence à
copier est `ui/albums.js` : `& < > " ' \\`` → entités.

Portée S-02 (annexe A §B3, §B4, injection #12), fusionnée ici — le ticket
S-02 créait un fichier de MÊME NOM ; les deux blocs de tests sont concaténés
(aucun nom de test partagé) :

  - liens sociaux : un `href` posé depuis une valeur saisie par l'artiste
    (`javascript:…`, `data:…`) s'exécute au clic → vol du jeton de session.
    La seule source de vérité est `safeSocialHref(key, val)`, dupliquée dans
    `artiste.js` (profil public) et `dashboard.js` (aperçu du profil).
  - marqueur d'échange : `__TRADE_OFFER__<id>` est un message posté par le
    CLIENT via l'endpoint générique `/messages` — son id ne doit jamais être
    interpolé dans un `onclick`. Carte = `data-offer-id` + délégué, id validé
    UUID.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SKIP_DIRS = {
    ".git", "venv", ".venv", "node_modules", "__pycache__", "OBSIDIAN",
    ".pytest_cache", "_masters_backup", "_d2wt", ".relay", ".watcher-logs",
    "e2e", "graphify-out", "watt-api", "scripts", "data",
}

# Échappeur « textContent → innerHTML » : n'échappe pas les guillemets.
_RE_TEXTCONTENT_ESCAPER = re.compile(
    r"createElement\(\s*['\"]div['\"]\s*\)[^;]*;\s*"
    r"\w+\.textContent\s*=[^;]*;\s*"
    r"return\s+\w+\.innerHTML",
    re.DOTALL,
)

# Échappeur dont le corps est UNIQUEMENT `.replace(/</g, '&lt;')`
# (ex. `const esc = (s) => String(s == null ? '' : s).replace(/</g, '&lt;');`).
_RE_LT_ONLY_ESCAPER = re.compile(
    r"(?:const|let|var)\s+_?esc\w*\s*=\s*\(?\s*\w+\s*\)?\s*=>\s*"
    r"String\([^;]*?\)\.replace\(/</g,\s*['\"]&lt;['\"]\)\s*;"
)

# Interpolations brutes qui ont servi de vecteur (annexe A §B2, injection #7),
# en contexte HTML : attribut (`src="${…}"`) ou nœud texte (`>${track.name}<`).
# Un `${track.name}` passé à showToast (textContent) n'est pas concerné.
_RAW_INTERPOLATIONS = (
    r'src="\$\{p\.audio_url\}"',
    r'src="\$\{p\.preview_url\}"',
    r"[>\"']\$\{track\.name\}",
)


def _fichiers_js():
    """`ui/**/*.js` + JS à la racine du dépôt (artiste.js, dashboard.js…)."""
    seen = set()
    for p in list(REPO_ROOT.glob("*.js")) + list((REPO_ROOT / "ui").rglob("*.js")):
        if not p.is_file():
            continue
        rel = p.relative_to(REPO_ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if p.name.endswith(".min.js") or p in seen:
            continue
        seen.add(p)
        yield p


def _lire(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def test_scan_couvre_le_front():
    """Le parcours doit voir les fichiers de portée de S-01 (sinon le garde-fou
    ne garde rien)."""
    noms = {str(p.relative_to(REPO_ROOT)) for p in _fichiers_js()}
    for attendu in (
        "artiste.js", "library.js", "ui/hub/marketplace.js",
        "ui/topbar/topbar.js", "ui/messaging/messaging.js", "ui/core/trade-view.js",
    ):
        assert attendu in noms, f"{attendu} absent du scan : {sorted(noms)[:10]}…"


def test_aucun_echappeur_textcontent_innerhtml():
    """`div.textContent → innerHTML` laisse passer `"` et `'` : interdit."""
    fautifs = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in _RE_TEXTCONTENT_ESCAPER.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            fautifs.append(f"{p.relative_to(REPO_ROOT)}:{ligne}")
    assert not fautifs, (
        "échappeur textContent→innerHTML (n'échappe pas les guillemets) : "
        f"{fautifs} — copier ui/albums.js:_esc"
    )


def test_aucun_echappeur_lt_seul():
    """Un échappeur réduit à `.replace(/</g, '&lt;')` n'en est pas un."""
    fautifs = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in _RE_LT_ONLY_ESCAPER.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            fautifs.append(f"{p.relative_to(REPO_ROOT)}:{ligne}")
    assert not fautifs, (
        f"échappeur `replace(/</g,'&lt;')` seul : {fautifs} — copier ui/albums.js:_esc"
    )


@pytest.mark.parametrize("motif", _RAW_INTERPOLATIONS)
def test_aucune_interpolation_brute(motif: str):
    """Les vecteurs identifiés par l'audit ne doivent pas réapparaître bruts."""
    rx = re.compile(motif)
    fautifs = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in rx.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            fautifs.append(f"{p.relative_to(REPO_ROOT)}:{ligne}")
    assert not fautifs, f"interpolation brute `{motif}` : {fautifs}"


def test_echappeurs_de_reference_complets():
    """Les échappeurs des fichiers de portée S-01 traitent bien `"` et `'`
    (la forme exacte importe peu : entités présentes dans le corps)."""
    attendus = {
        "ui/hub/marketplace.js": r"function _esc\(s\)",
        "library.js": r"function esc\(s\)",
        "ui/core/page-services.js": r"function _esc\(s\)",
        "ui/messaging/messaging.js": r"function _esc\(s\)",
        "ui/topbar/topbar.js": r"function _esc\(s\)",
        "ui/core/dom.js": r"function _esc\(s\)",
        "ui/core/trade-view.js": r"const _esc = ",
    }
    for rel, tete in attendus.items():
        src = _lire(REPO_ROOT / rel)
        m = re.search(tete, src)
        assert m, f"{rel} : échappeur `{tete}` introuvable"
        corps = src[m.start(): m.start() + 600]
        assert "&quot;" in corps and "&#39;" in corps, (
            f"{rel} : l'échappeur n'échappe pas `\"` et `'` — copier ui/albums.js:_esc"
        )


# ── S-02 : liens sociaux sûrs, marqueur d'échange, self-XSS ───────────────────
# `_lire` ci-dessus prend un Path ; ce raccourci prend un chemin relatif au dépôt.
def _lire_rel(rel: str) -> str:
    return _lire(REPO_ROOT / rel)


# Formes vulnérables retirées par S-02 : elles ne doivent pas réapparaître.
_S02_INTERDITS = (
    ("artiste.js", "a.href = val;"),                       # href social brut
    ("artiste.js", "a.href   = val;"),
    ("dashboard.js", 'href="${p.soundcloud}"'),            # innerHTML += avec URL profil
    ("dashboard.js", 'href="${p.youtube}"'),
    ("dashboard.js", 'href="${p.spotify}"'),
    ("dashboard.js", "${d.sampleName}</strong>"),          # self-XSS nom de fichier
    ("ui/messaging/messaging.js", "SmyleTradeView.open('${offerId}')"),  # onclick inline
)


@pytest.mark.parametrize("rel,motif", _S02_INTERDITS)
def test_forme_vulnerable_absente(rel: str, motif: str):
    assert motif not in _lire_rel(rel), f"{rel} : `{motif}` réintroduit"


@pytest.mark.parametrize("rel", ("artiste.js", "dashboard.js"))
def test_safe_social_href_present(rel: str):
    """Un seul point d'entrée pour un href social, avec handle encodé."""
    src = _lire_rel(rel)
    assert "function safeSocialHref(key, val)" in src, f"{rel} : safeSocialHref absent"
    assert "encodeURIComponent(v.replace(/^@/, ''))" in src, f"{rel} : handle non encodé"
    # Tout schéma autre que http(s) est refusé (javascript:, data:, vbscript:).
    assert r"if (/^[a-z][a-z0-9+.\-]*:/i.test(v)) return '';" in src, (
        f"{rel} : le refus des schémas non http(s) a disparu"
    )


def test_liens_sociaux_dashboard_en_create_element():
    """Plus d'`innerHTML +=` pour les liens du profil : createElement + textContent."""
    src = _lire_rel("dashboard.js")
    assert "pvLinks.innerHTML +=" not in src, "dashboard.js : innerHTML += réintroduit"
    assert "pvLinks.appendChild(a);" in src, "dashboard.js : createElement('a') attendu"


def test_marqueur_echange_valide_uuid():
    """`__TRADE_OFFER__<id>` n'est une carte cliquable que si l'id est un UUID."""
    src = _lire_rel("ui/messaging/messaging.js")
    assert "const _UUID_RE = /^[0-9a-f]{8}-" in src, "messaging.js : _UUID_RE absent"
    assert "_UUID_RE.test(content0.slice('__TRADE_OFFER__'.length))" in src, (
        "messaging.js : le marqueur n'est plus validé UUID au rendu"
    )
    assert 'data-offer-id="${_esc(offerId)}"' in src, (
        "messaging.js : la carte doit porter data-offer-id (plus d'onclick inline)"
    )
    assert "_UUID_RE.test(btn.dataset.offerId" in src, (
        "messaging.js : le délégué doit revalider l'id avant SmyleTradeView.open"
    )


def test_self_xss_titres_du_proprietaire():
    """Injection #12 : titres/nom de fichier du propre compte échappés aussi."""
    dash = _lire_rel("dashboard.js")
    assert "htmlEscape(d.sampleName)" in dash, "dashboard.js : sampleName non échappé"
    assert "&#39;" in dash, "dashboard.js : htmlEscape n'échappe pas l'apostrophe"
    wp = _lire_rel("ui/panels/watt-panel.js")
    assert "&#39;" in wp and "&quot;" in wp, (
        "watt-panel.js : le titre n'est plus échappé complètement"
    )


# ── D1→D5 : plus aucun gestionnaire en ligne interpolé ────────────────────────
# Pourquoi ce garde-fou existe malgré S-01/S-02 : l'échappeur HTML complet
# (`& < > " ' \``) posé par ces deux tickets NE protège PAS à l'intérieur d'un
# attribut de gestionnaire. Le parseur HTML décode les entités (`&#39;` → `'`)
# AVANT que le contenu de l'attribut ne soit compilé comme du JavaScript :
#
#     onclick="f('${_esc(x)}')"   avec x = "a');alert(1);//"
#     → l'attribut contient  f('a&#39;);alert(1);//')
#     → décodé par le parseur en  f('a');alert(1);//')  → exécuté.
#
# La seule correction sûre est `data-*` + délégation d'événement (le délégué lit
# `dataset`, jamais évalué comme du code). C'est le motif de S-01/S-02.
#
# Ce test interdit donc TOUT NOUVEAU gestionnaire en ligne interpolé. Les sites
# encore présents sont listés nommément ci-dessous : ils interpolent tous soit
# un identifiant produit par le SERVEUR (UUID), soit un indice de tableau, soit
# une constante figée dans le front — aucun tiers ne peut y glisser
# d'apostrophe. Ils ont été laissés parce que les convertir demanderait de
# réécrire de grosses portions de rendu (risque de régression > gain), pas
# parce que le motif serait acceptable. Toute NOUVELLE occurrence — y compris
# la modification d'une occurrence tolérée — fait échouer ce test : à ce
# moment-là, on convertit, on ne rallonge pas la liste.

# Gestionnaire en ligne (`onclick=`, `onchange=`, `onerror=`, `ondrop=`…) dont
# la valeur, entre guillemets doubles, contient une interpolation `${…}`.
_RE_HANDLER_INTERPOLE = re.compile(r'\bon[a-z]+\s*=\s*"[^"]*\$\{[^"]*"')

# Même chose en guillemets simples : aucune occurrence aujourd'hui, aucune
# tolérée — la liste ci-dessous ne couvre que la forme en guillemets doubles.
_RE_HANDLER_INTERPOLE_SQ = re.compile(r"\bon[a-z]+\s*=\s*'[^']*\$\{[^']*'")


def _handlers_interpoles():
    """[(chemin relatif, ligne, attribut normalisé)] pour tout le front."""
    trouves = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in _RE_HANDLER_INTERPOLE.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            trouves.append((
                str(p.relative_to(REPO_ROOT)),
                ligne,
                " ".join(m.group(0).split()),
            ))
    return trouves


# Sites tolérés : (fichier, attribut exact) → nombre d'occurrences autorisées.
# La raison est donnée par bloc. L'attribut est comparé au caractère près :
# changer la donnée interpolée d'un site toléré le fait sortir de la liste.
_HANDLERS_TOLERES = {
    # — Identifiants d'échange / de notification : UUID v4 produits par l'API
    #   (trades.id, notifications.id, users.id). Le rendu de ces écrans est un
    #   gros gabarit `innerHTML` sans conteneur stable évident ; conversion
    #   reportée.
    ("ui/core/trade-view.js", """onclick="SmyleTradeView._adnAct('${_esc(o.id)}','accept')\""""): 1,
    ("ui/core/trade-view.js", """onclick="SmyleTradeView._adnAct('${_esc(o.id)}','reject')\""""): 1,
    ("ui/core/trade-view.js", """onclick="SmyleTradeView._adnAct('${_esc(o.id)}','cancel')\""""): 1,
    ("ui/core/trade-view.js", """onclick="SmyleTradeView._act('${_esc(o.id)}','accept')\""""): 1,
    ("ui/core/trade-view.js", """onclick="SmyleTradeView._act('${_esc(o.id)}','reject')\""""): 1,
    ("ui/core/trade-view.js", """onclick="SmyleTradeView._act('${_esc(o.id)}','cancel')\""""): 1,
    ("ui/core/trade-view.js", """onclick="if(window.SmyleMessaging){document.getElementById('smyle-tradeview').remove();SmyleMessaging.open('${_esc(otherId)}');}\""""): 1,
    ("ui/topbar/topbar.js", """onclick="SmyleTopbar._tradeAct('${esc(o.id)}','accept')\""""): 1,
    ("ui/topbar/topbar.js", """onclick="SmyleTopbar._tradeAct('${esc(o.id)}','reject')\""""): 1,
    ("ui/topbar/topbar.js", """onclick="SmyleTopbar._tradeAct('${esc(o.id)}','cancel')\""""): 1,
    ("ui/topbar/topbar.js", """onclick="SmyleTopbar._adnOfferAct('${esc(o.id)}','accept')\""""): 1,
    ("ui/topbar/topbar.js", """onclick="SmyleTopbar._adnOfferAct('${esc(o.id)}','reject')\""""): 1,
    ("ui/topbar/topbar.js", """onclick="SmyleTopbar._adnOfferAct('${esc(o.id)}','cancel')\""""): 1,
    ("ui/topbar/topbar.js", """onclick="if(window.SmyleMessaging){document.getElementById('smyle-adnofferview').remove();SmyleMessaging.open('${esc(otherId)}');}\""""): 1,
    ("ui/topbar/topbar.js", """onclick="window.SmyleTopbar.followBack(event, '${_esc(n.actor_id)}')\""""): 1,
    # `${extraClick}` est un fragment de code construit dans le module, dont la
    # seule partie variable est `_esc(n.actor_id)` / `_esc(n.target_id)` (UUID).
    ("ui/topbar/topbar.js", """onclick="window.SmyleTopbar.markRead(event, '${_esc(n.id)}');${extraClick}\""""): 1,
    ("ui/core/page-services.js", """onclick="window.__pageMarkRead('${_esc(n.id)}', this)${tradeClick}\""""): 1,
    ("ui/core/page-services.js", """onclick="window.__pageOpenThread('${_esc(t.other_user_id)}')\""""): 1,

    # — dashboard.js : ids de sons / de voix (UUID serveur), clés de rôle et de
    #   genre venant de constantes front figées (DASH_ID_ROLES,
    #   DASH_VOICE_GENRES), couleurs d'un tableau littéral de 6 hex.
    ("dashboard.js", """onclick="openTrackEdit('${t.id}')\""""): 1,
    ("dashboard.js", """onclick="deleteTrack('${t.id}')\""""): 1,
    ("dashboard.js", """onclick="dte2Select('${t.id}')\""""): 1,
    ("dashboard.js", """onclick="selectEditColor('${c}',this)\""""): 1,
    ("dashboard.js", """onclick="dashIdentityToggleRole('${r.key}')\""""): 1,
    ("dashboard.js", """onclick="dashVoiceToggleGenre('${g.key}')\""""): 1,
    ("dashboard.js", """onclick="dashVoicePublishToggle('${v.id}', false)\""""): 1,
    ("dashboard.js", """onclick="dashVoicePublishToggle('${v.id}', true)\""""): 1,
    ("dashboard.js", """onclick="dashVoiceEditFromList('${v.id}')\""""): 1,
    ("dashboard.js", """onclick="dashVoiceDeleteFromList('${v.id}')\""""): 1,
    ("dashboard.js", """onclick="cancelTrade('${t.id}', this)\""""): 1,
    ("dashboard.js", """onclick="acceptTrade('${t.id}', this)\""""): 1,
    ("dashboard.js", """onclick="rejectTrade('${t.id}', this)\""""): 1,

    # — artiste.js : `type` est un littéral du module ('son' | 'voix' |
    #   'adn-artist' | 'visual-adn'), les autres sont des UUID serveur.
    ("artiste.js", """onclick="boutiqueDrawerUnlock('${type}','${data.id}')\""""): 1,
    ("artiste.js", """onclick="submitTradeOffer('${escH(promptId)}', '${escH(receiverId)}')\""""): 1,
    ("artiste.js", """onclick="submitTradeOfferProfile('${artist.id || ''}')\""""): 1,

    # — library.js : `${i}` est l'indice de la boucle de rendu (entier),
    #   `${p.prompt_id}` un UUID serveur. 20 sites, tous du même gabarit.
    ("library.js", """onclick="copyContent('lib-imgset-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-imgneg-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-imgprompt-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-lyrics-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-prompt-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-pl-adn-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-al-adn-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-al-pal-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-vadn-desc-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-vadn-pal-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-vadn-guide-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-vadn-ex-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-usage-${i}', this)\""""): 1,
    ("library.js", """onclick="copyContent('lib-ex-${i}', this)\""""): 1,
    ("library.js", """onclick="libDownloadImage('${p.prompt_id}', this)\""""): 1,
    ("library.js", """onclick="libDownloadProduct('${p.prompt_id}', this)\""""): 1,
    ("library.js", """onclick="libUnlistResale('${p.prompt_id}')\""""): 2,
    ("library.js", """onclick="libListResale('${p.prompt_id}')\""""): 2,
    ("library.js", """onclick="event.stopPropagation();event.preventDefault();libToggleAudio(this,'lib-audio-${i}')\""""): 1,
    ("library.js", """onclick="event.stopPropagation();event.preventDefault();libToggleAudio(this,'lib-vaudio-${i}')\""""): 1,

    # — ui/panels/ : indices de boucle, clés de cellule figées (`m.key`), ids de
    #   playlist et de son produits par le serveur, clé de playlist statique
    #   passée par le HTML (`openPlaylist('jungle')`…).
    ("ui/panels/mix.js", """ondragstart="mixDragStart(event,${i})\""""): 1,
    ("ui/panels/mix.js", """ondragover="mixDragOver(event,${i})\""""): 1,
    ("ui/panels/mix.js", """ondrop="mixDrop(event,${i})\""""): 1,
    ("ui/panels/mix.js", """onclick="playMixFromIdx(${i})\""""): 1,
    ("ui/panels/mix.js", """onclick="removeFromMix(event,${i})\""""): 1,
    ("ui/panels/mix.js", """onclick="loadSavedPlaylist('${_mixEsc(wishlist.id)}')\""""): 1,
    ("ui/panels/mix.js", """onclick="loadSavedPlaylist('${_mixEsc(p.id)}')\""""): 1,
    ("ui/panels/mix.js", """onclick="loadSavedPlaylist('${_mixEsc(p.id)}', true)\""""): 1,
    ("ui/panels/mix.js", """onclick="deleteSavedPlaylist(event, '${_mixEsc(p.id)}')\""""): 1,
    ("ui/panels/mix.js", """onclick="deleteSavedPlaylist(event, '${_mixEsc(p.id)}', true)\""""): 1,
    ("ui/panels/playlist.js", """onclick="loadTrack('${key}', ${i})\""""): 1,
    ("ui/panels/playlist.js", """onclick="addToMix(event,'${key}',${i})\""""): 1,
    ("ui/panels/watt-panel.js", """onclick="_wattCellToggle('${m.key}')\""""): 1,
    ("ui/panels/watt-panel.js", """onclick="window.location.href='/dashboard?edit-track=${id}'\""""): 1,
}


def test_aucun_nouveau_gestionnaire_en_ligne_interpole():
    """Aucun gestionnaire en ligne interpolé en dehors de la liste tolérée.

    Échoue dès qu'un `onclick="f('${x}')"` apparaît quelque part dans
    `ui/**/*.js` ou les JS racine — y compris si l'on modifie la donnée
    interpolée d'un site toléré. Correction attendue : `data-*` + délégation
    d'événement (cf. `_bindDelegates` dans ui/messaging/messaging.js).
    """
    from collections import Counter

    vus = Counter((rel, frag) for rel, _ligne, frag in _handlers_interpoles())
    lignes = {}
    for rel, ligne, frag in _handlers_interpoles():
        lignes.setdefault((rel, frag), []).append(ligne)

    nouveaux = []
    for cle, n in sorted(vus.items()):
        autorise = _HANDLERS_TOLERES.get(cle, 0)
        if n > autorise:
            rel, frag = cle
            nouveaux.append(
                f"{rel}:{','.join(str(x) for x in lignes[cle])} → {frag}"
                f"  (toléré : {autorise}, trouvé : {n})"
            )
    assert not nouveaux, (
        "gestionnaire en ligne interpolé non toléré — l'échappeur HTML ne "
        "protège PAS dans un attribut `on…` (le parseur décode `&#39;` en `'` "
        "avant compilation du JS). Convertir en `data-*` + délégation "
        "d'événement (motif S-01/S-02, cf. ui/messaging/messaging.js"
        ":_bindDelegates) :\n  " + "\n  ".join(nouveaux)
    )


def test_aucun_gestionnaire_en_ligne_interpole_en_quotes_simples():
    """Variante `onclick='…${…}…'` : zéro toléré."""
    fautifs = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in _RE_HANDLER_INTERPOLE_SQ.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            fautifs.append(f"{p.relative_to(REPO_ROOT)}:{ligne} → {m.group(0)[:80]}")
    assert not fautifs, f"gestionnaire en ligne interpolé (quotes simples) : {fautifs}"


@pytest.mark.parametrize("rel", (
    "ui/messaging/messaging.js", "ui/modals/auth.js", "ui/hub/marketplace.js",
))
def test_fichiers_convertis_sans_gestionnaire_en_ligne(rel: str):
    """D1/D2 : ces trois fichiers n'ont plus AUCUN gestionnaire interpolé."""
    src = _lire_rel(rel)
    restants = [
        " ".join(m.group(0).split())
        for m in _RE_HANDLER_INTERPOLE.finditer(src)
    ]
    assert not restants, f"{rel} : gestionnaire en ligne réintroduit → {restants}"


# Formes vulnérables retirées par D1/D2 : elles ne doivent pas réapparaître.
_D1_INTERDITS = (
    ("ui/messaging/messaging.js", "_submitTradeFromConv('${receiverId}')"),
    ("ui/modals/auth.js", "copyReferral('${code}')"),
    ("ui/modals/auth.js", "copyReferral('${link"),
    ("ui/hub/marketplace.js", "window.location.href='${_esc(href)}'"),
    ("dashboard.js", "copyPublicProfileLink('${url}')"),
)


@pytest.mark.parametrize("rel,motif", _D1_INTERDITS)
def test_forme_vulnerable_d1_absente(rel: str, motif: str):
    assert motif not in _lire_rel(rel), f"{rel} : `{motif}` réintroduit"


def test_delegues_d1_en_place():
    """Chaque bouton converti est bien repris par un délégué (sinon il ne fait
    plus rien : la conversion casserait le comportement)."""
    msg = _lire_rel("ui/messaging/messaging.js")
    assert 'data-trade-receiver="${_esc(receiverId)}"' in msg, (
        "messaging.js : le bouton d'envoi doit porter data-trade-receiver"
    )
    assert "_submitTradeFromConv(send.dataset.tradeReceiver" in msg, (
        "messaging.js : le délégué de la modale d'échange a disparu"
    )

    auth = _lire_rel("ui/modals/auth.js")
    assert auth.count('data-copy-text="${_authEscHtml(') == 2, (
        "auth.js : les deux boutons « Copier » doivent porter data-copy-text"
    )
    assert "copyReferral(btn.dataset.copyText" in auth, (
        "auth.js : le délégué de #referralModal a disparu"
    )

    mp = _lire_rel("ui/hub/marketplace.js")
    assert mp.count('data-nav-href="${_esc(href)}"') == 2, (
        "marketplace.js : les deux lignes de classement doivent porter data-nav-href"
    )
    assert "function _bindNavRows()" in mp and "_navRowsBound" in mp, (
        "marketplace.js : le délégué _bindNavRows (idempotent) a disparu"
    )
    assert "href.charAt(0) !== '/'" in mp, (
        "marketplace.js : _bindNavRows doit refuser ce qui n'est pas un chemin interne"
    )

    dash = _lire_rel("dashboard.js")
    assert 'data-copy-profile-url="${htmlEscape(url)}"' in dash, (
        "dashboard.js : le bouton « Copier le lien » doit porter data-copy-profile-url"
    )
    assert "copyPublicProfileLink(btn.dataset.copyProfileUrl" in dash, (
        "dashboard.js : le délégué de #pvPublicLink a disparu"
    )


def test_messaging_un_seul_delegue():
    """D3 : les deux délégués posés sur le même conteneur sont fusionnés, et
    la pose reste idempotente."""
    src = _lire_rel("ui/messaging/messaging.js")
    assert "msgOfferDelegated" not in src and "_bindOfferDelegate" not in src, (
        "messaging.js : le second délégué (msgOfferDelegated) est de retour"
    )
    # Un seul écouteur `click` posé sur le conteneur `el` de la messagerie.
    assert src.count("el.addEventListener('click', (ev) => {") == 1, (
        "messaging.js : plus d'un écouteur de clic posé sur le conteneur"
    )
    assert "if (!el || el.dataset.msgDelegated === '1') return;" in src, (
        "messaging.js : la garde d'idempotence du délégué a disparu"
    )
    for marqueur in ("[data-offer-id]", "[data-thread-user-id]"):
        assert marqueur in src, f"messaging.js : aiguillage `{marqueur}` perdu"
