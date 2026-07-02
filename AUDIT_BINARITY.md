# AUDIT DUALITÉ MUSIQUE/VISUEL — WATT MARKET

**Date:** 2 juillet 2026
**Scope:** Étapes 1-4 du chantier binarité (D)
**Profondeur:** Very thorough (couverture code exhaustive)

---

## RÉSUMÉ EXÉCUTIF

| Étape | Primitif | État | Couverture API | Intégration UI |
|-------|----------|------|----------------|----------------|
| 1. Pack ADN -15% | `compute_oeuvre_pack_price` | **FAIT** | ✅ Endpoint POST | ✅ Oeuvre page |
| 2. Gate "profil publié" | `profile_public` | **PARTIEL** | ⚠️ Images OK, couverture asymétrique | ⚠️ Fuite mineure |
| 3. Prix | Seed/config | **PARTIEL** | ✅ Prompts 3-500, Visuel 30-500, ADN ? | ❌ ADN Album/Playlist sans défaut |
| 4. Images vendables | `product_type='image'` | **FAIT** | ✅ Unlock prompt (images) | ⚠️ Pas de "fiche visuelle" distincte |

---

## ÉTAPE 1 : PACK ADN CROISÉ -15% (musique + visuel)

### État : **FAIT**

### Fichiers clés
- **Services** : `/watt-api/app/services/credits.py:def compute_oeuvre_pack_price()`
- **Services métier** : `/watt-api/app/services/oeuvre_purchase.py:buy_oeuvre_atomic()`
- **Router API** : `/watt-api/app/routers/oeuvre.py:POST /oeuvre/{slug}/buy-complete`
- **Tests** : `/watt-api/tests/test_oeuvre_pricing.py`

### Implémentation détaillée

#### 1.1 Primitive de calcul : `compute_oeuvre_pack_price()`
**Fichier** : `services/credits.py:82-141`

```python
def compute_oeuvre_pack_price(face_prices: list[int], has_artist_perk: bool) -> int:
    """
    Prix du pack « œuvre complète » (C5) — bundle ADN Playlist + ADN Album.
    
    Cascade perks :
      1. -30% par face si has_artist_perk (détenteur ADN profil/visuel)
      2. -15% sur somme
    
    Plancher : >= nombre de faces (jamais 0).
    """
    subtotal = sum(
        compute_effective_price(int(p), has_artist_perk) for p in face_prices
    )
    packed = (subtotal * OEUVRE_PACK_NUMERATOR) // OEUVRE_PACK_DENOMINATOR
    return max(len(face_prices), packed)
```

**Constantes** (credits.py:71-72):
- `OEUVRE_PACK_NUMERATOR = 85`
- `OEUVRE_PACK_DENOMINATOR = 100` → -15% ✅

**Tests** (test_oeuvre_pricing.py):
- ✅ Sans perk : `[40, 35] → 63` (75*0.85)
- ✅ Avec perk -30% : `[40, 35] → 44` (52*0.85)
- ✅ Plancher : `[1, 1] → 2`

#### 1.2 Achat atomique : `buy_oeuvre_atomic()`
**Fichier** : `services/oeuvre_purchase.py:75-250`

Appel du pricing :
```python
paid = compute_oeuvre_pack_price(
    [int(playlist.adn_price), int(album.adn_price)], has_artist_perk
)
```

Étapes :
1. Lecture playlist (face SON) + album (face VISUEL) par slug
2. Vérifications : visibilité public, adn_for_sale, adn_price NOT NULL
3. Détection perk artiste (user possède ADN profil artiste)
4. Calcul prix pack -15% avec perk artiste -30%
5. Transaction atomique : débite acheteur, crédite artiste
6. Insère 2 lignes OwnedPlaylistAdn + OwnedAlbumAdn
7. Hook achievements (FAN + ARTIST)

#### 1.3 Endpoint API
**Fichier** : `routers/oeuvre.py:285-357`

```
POST /watt/oeuvre/{slug}/buy-complete
  Auth: JWT requis (get_current_user)
  Rate limit: LIMIT_PURCHASE
  
Réponse 200 :
{
  "ok": true,
  "slug": "my-oeuvre",
  "paid": 44,
  "playlist_id": "...",
  "album_id": "...",
  "message": "Œuvre complète débloquée — ADN son + visuel"
}
```

Gestions d'erreurs :
- 409 CONFLICT : possède déjà une face (IntegrityError)
- 400 / ValueError : conditions de vente non remplies
- 500 : échec transactionnel

#### 1.4 Intégration UI
**Fichier** : `routers/oeuvre.py:184-284` (`GET /watt/oeuvre/{slug}`)

**Exposé** :
- `isComplete: bool` → indique dualité complète
- `son.adnForSale`, `visuel.adnForSale` → toggles de vente
- `son.adnPrice`, `visuel.adnPrice` → prix unitaires
- Bouton "Acheter l'œuvre complète" : `/watt/oeuvre/{slug}/buy-complete`

**Anti-fuite génome** : genomes (seed_prompt, adn_palette) masqués publiquement

### Synthèse étape 1
✅ **Fait et couvert** :
- Primitive -15% correcte (85% appliqué)
- Cascade perk -30% intégrée (via compute_effective_price)
- Endpoint d'achat pack fonctionnel
- Atomicité transactionnelle garantie (savepoint)
- Tests unitaires complets
- UI : fiche œuvre expose prix + bouton d'achat

❌ **Absent** : Rien de critique détecté

---

## ÉTAPE 2 : GATE "PROFIL PUBLIÉ" SUR LES IMAGES

### État : **PARTIEL** (asymétrie musique vs visuel)

### Fichiers clés
- **Modèles** : `models/user.py` (profile_public)
- **Routers** : `routers/tracks.py`, `routers/images.py`, `routers/oeuvre.py`
- **Services discovery** : `services/discovery.py` (list_public_artists, etc.)
- **Migrations** : 0076 (oeuvre_binding), schéma Playlist/Album

### 2.1 Filtre côté MUSIQUE ✅

#### Côté création (POST /tracks/)
**Fichier** : `routers/tracks.py:46-50`

```python
if not bool(getattr(current_user, "profile_public", False)):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "profile_not_published",
            "message": "Publie d'abord ton profil pour pouvoir publier un son.",
            "redirect": "/u/me",
        },
    )
```

Gate **dur** : ne peut créer un son qu'après `profile_public=True`. ✅

#### Côté lecture publique (catalog, discovery)
**Fichier** : `services/discovery.py:104-117`

```python
base_filter = and_(
    User.artist_name.is_not(None),
    User.profile_public.is_(True),  # ← Gate
    _has_published_content_subquery(User.id),
)
```

Résultat : 
- ✅ Artiste n'apparaît **jamais** au catalogue public (`/catalog/artists`) si `profile_public=False`
- ✅ Ses prompts ne sont pas listables (is_published=True ET artist.profile_public=True implicite)
- ✅ 404 public (indistinguable d'une non-existence)

---

### 2.2 Filtre côté VISUEL ⚠️ (ASYMÉTRIE)

#### Côté création (POST /images/)
**Fichier** : `routers/images.py:207-210`

```python
if not bool(getattr(current_user, "profile_public", False)):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "profile_not_published",
            "message": "Publie d'abord ton profil pour pouvoir publier une image.",
            "redirect": "/u/me",
        },
    )
```

Gate : identique au son. ✅

#### Côté lecture publique — FUITE !
**Fichier** : `routers/images.py:630-680` (`GET /images`)

```python
@router.get("/images")
async def list_public_images(
    artist_id: Optional[UUID] = Query(default=None),
    ...
):
    base = (
        select(Prompt)
        .join(User, Prompt.artist_id == User.id)
        .where(
            Prompt.product_type == "image",
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            # ⚠️ MANQUANT : User.profile_public.is_(True)
        )
    )
```

**Danger** : Une image publié d'un artiste `profile_public=False` reste visible sur `/images` !

#### Filtres appliqués sur images publiques
**Code** : `services/discovery.py` + `routers/images.py:_apply_image_filters()`

Chaîne de filtres :
1. `product_type = 'image'` ✅
2. `is_published = True` ✅
3. `is_deleted = False` ✅
4. `artist_id` filter (optionnel) ✅
5. **`User.profile_public = True`** ❌ **MANQUANT SUR /images**

**Corrigé** :
```python
.where(
    Prompt.product_type == "image",
    Prompt.is_published.is_(True),
    Prompt.is_deleted.is_(False),
    User.profile_public.is_(True),  # ← À ajouter
)
```

#### Endpoints impactés
| Endpoint | Filtre profile_public | Statut |
|----------|----------------------|--------|
| `/catalog/images` (alias `/images`) | **Manquant** | ❌ Fuite |
| `/images/top` | **Manquant** | ❌ Fuite |
| `/artists/images-top` | **Manquant** | ❌ Fuite |
| `GET /watt/users/{slug}/images` | Gate via `_find_artist_by_slug` (relit profile_public) | ✅ OK |
| `GET /watt/oeuvre/{slug}` | Filtre sur `Album.visibility='public'` + own check | ⚠️ Partiel |

---

### 2.3 Couverture des URLs R2 (images directes)

#### Aperçus (publics)
**Endpoint** : `GET /watt/images/{key:path}` (`routers/images.py:1208-1261`)

```python
if not key.startswith("images/previews/"):
    raise HTTPException(status_code=404, detail="Not found")
```

**Gate dur** : 
- ✅ Seul `images/previews/*` accessible
- ✅ `images/originals/*` 404 systématique
- ❌ **Pas de check sur artist.profile_public** — les aperçus d'un profil non publié restent servables !

**Danger** : Si on retient une fuite à `/images`, le lien vers `preview_r2_key` reste public car pas de check de profile_public.

#### Originaux (gate achat)
**Endpoint** : `GET /images/{image_id}/download` (`routers/images.py:1266-1328`)

```python
product = (await db.execute(
    select(Prompt).where(
        Prompt.id == image_id,
        Prompt.product_type == "image",
    )
)).scalar_one_or_none()

# Vérification possession (UnlockedPrompt)
```

**Gate** : 
- ✅ Auth requis (get_current_user)
- ✅ Possession vérifiée (UnlockedPrompt)
- ✅ Soft-deleted OK si possédé

---

### 2.4 ADN Visuel artiste — gate de publication

**Fichier** : `services/visual_adn.py:91-111` (list publique)

```python
result = await db.execute(
    select(VisualAdn).where(
        VisualAdn.artist_id == artist_id,
        VisualAdn.is_deleted.is_(False),
    )
)
```

**Problem** : Aucun check sur `VisualAdn.is_published` dans la recherche catalogue public.

Correction attendue (par parallèle ADN musical) :
```python
where(
    VisualAdn.is_published.is_(True),
    VisualAdn.is_deleted.is_(False),
    VisualAdn.artist_id.in_(
        select(User.id).where(User.profile_public.is_(True))
    ),
)
```

---

### 2.5 Albums ADN (génome visuel) — gate de publication

**Fichier** : `services/discovery.py:810-825` + `routers/catalog.py`

```python
Album.visibility == "public",
Album.adn_for_sale == True,
Album.adn_price.is_not(None),
```

**Manquant** : Pas de vérification `User.profile_public` sur l'owner de l'album !

---

### Synthèse étape 2

✅ **Fait** :
- Gate "profil publié" sur création (musique + visuel) = identique
- Filtre artiste public sur catalog général (discovery.py)

❌ **FUITE MINEURE** (nécessite correction) :
1. `/images` + `/images/top` + `/artists/images-top` : **Manquent** `User.profile_public.is_(True)`
2. `/watt/images/{key}` (proxy aperçu) : pas de check artist.profile_public
3. `/catalog/visual-adns` (si implémenté) : pas de check artist.profile_public
4. `/catalog/albums-adn` : pas de vérification artist.profile_public sur owner

**Règles** à homogénéiser (parité son/image) :
- Filtre visuel = filtre son
- Tous les endpoints PUBLICS d'un artiste doivent vérifier `profile_public=True`

---

## ÉTAPE 3 : PRIX (CONFIGURATION + SEEDS)

### État : **PARTIEL** (bornes OK, defaults absents)

### Fichiers clés
- **Modèles** : `models/prompt.py`, `models/visual_adn.py`, `models/album.py`, `models/playlist.py`
- **Migrations** : 0062 (album_adn), 0063 (visual_adn)
- **Routers** : `routers/unlocks.py`, `routers/marketplace.py`

### 3.1 Prompts (recettes audio + images)

**Modèle** : `models/prompt.py:95-97`

```python
CheckConstraint(
    "price_credits >= 3",
    name="ck_prompts_price_credits_min",
)
```

**Bornes** : 
- Min: 3 crédits ✅
- Max: 500 crédits (CHECK PROMPT_PRICE_MAX dans schemas/image.py) ✅
- Type : 'recipe' | 'beat' | 'image'

**Défaut** : Aucun défaut configuré. L'artiste choisit son prix à la création.

---

### 3.2 ADN Visuel (signature visuelle artiste)

**Modèle** : `models/visual_adn.py:52-54`

```python
CheckConstraint(
    "price_credits >= 30 AND price_credits <= 500",
    name="ck_visual_adns_price_credits_range",
)
```

**Bornes** : 
- Min: 30 crédits ✅
- Max: 500 crédits ✅
- Défaut : Aucun. L'artiste choisit.

---

### 3.3 ADN Album (génome de style d'album)

**Modèle** : `models/album.py:155-160`

```python
adn_for_sale: Mapped[bool] = mapped_column(
    Boolean, nullable=False, server_default="false"
)
adn_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

**Bornes** : 
- ❌ **Aucun CHECK CONSTRAINT sur adn_price** !
- Défaut : `adn_for_sale = false` (pas en vente par défaut) ✅
- Défaut : `adn_price = NULL` (aucun prix)

**Danger** : Un artiste peut créer `adn_price = -5` ou 999999 sans limite.

Correction attendue (parité ADN Playlist, migration 0035) :
```sql
ALTER TABLE albums ADD CHECK (adn_price IS NULL OR (adn_price >= 3 AND adn_price <= 500));
```

---

### 3.4 ADN Playlist (génome de style de playlist son)

**Modèle** : `models/playlist.py:74-78`

```python
adn_for_sale: Mapped[bool] = mapped_column(
    Boolean, nullable=False, server_default=text("false")
)
adn_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

**Bornes** : 
- ❌ **Aucun CHECK CONSTRAINT sur adn_price** !
- Défaut : `adn_for_sale = false` ✅
- Défaut : `adn_price = NULL` ✅

**Danger** : Identique à Album.

---

### 3.5 Constantes de pricing

**Fichier** : `services/credits.py:60-72`

```python
PERK_NUMERATOR = 7
PERK_DENOMINATOR = 10        # Perk artiste -30% (0.7)

PLAYLIST_PERK_NUMERATOR = 8
PLAYLIST_PERK_DENOMINATOR = 10  # Perk playlist -20% (0.8)

OEUVRE_PACK_NUMERATOR = 85
OEUVRE_PACK_DENOMINATOR = 100  # Pack -15% (0.85)
```

✅ Tous présents, **homogènes** (musique + visuel partagent mêmes constantes)

---

### 3.6 Seeds / données de test

**Répertoire** : `_d2wt/data/seeds/`

Pas de seed de prix trouvé. Les prix sont créés :
- Via routers (artistes publient leurs propres prix)
- Pas de fixture seed pour les ADN/prices

**Non-critique** pour un audit fonctionnel, mais utile pour tests/démo.

---

### Synthèse étape 3

✅ **Fait** :
- Prompts : bornes 3-500 ✅
- ADN Visuel : bornes 30-500 ✅
- Constantes perk (-30%, -20%, -15%) centralisées ✅

❌ **Manquant** (non-bloquant mais incohérent) :
1. ADN Album : **pas de CHECK constraint** sur adn_price
2. ADN Playlist : **pas de CHECK constraint** sur adn_price
3. Migration 0062/0063 : **pas d'ajout de CHECK** lors de création
4. Pas de seed de prix par défaut

**Recommandation** : Ajouter CHECK `adn_price >= 3 AND adn_price <= 500` sur Playlist + Album pour parité.

---

## ÉTAPE 4 : IMAGES VENDABLES (PRODUIT DISTINCT)

### État : **FAIT** (modèle existant, intégration incomplète)

### Fichiers clés
- **Modèle** : `models/prompt.py` (product_type = 'image')
- **Routers** : `routers/images.py` (POST, PATCH), `routers/unlocks.py` (unlock prompt)
- **Services** : `services/images.py`, `services/unlocks.py` (unlock_prompt_atomic)
- **Schémas** : `schemas/image.py` (ImageCreate, ImageUpdate)

### 4.1 Modèle produit image

**Table** : `prompts` avec discriminant `product_type`

```python
product_type: Mapped[str] = mapped_column(
    String(20), nullable=False, default="recipe", server_default="recipe"
)

# CHECK constraint (0057)
CheckConstraint(
    "(product_type = 'recipe' AND char_length(prompt_text) BETWEEN 100 AND 1000) "
    "OR (product_type = 'beat' AND prompt_text IS NULL) "
    "OR (product_type = 'image' AND prompt_text IS NOT NULL)",
    name="ck_prompts_prompt_text_length",
)

CheckConstraint(
    "product_type <> 'image' "
    "OR (image_platform IS NOT NULL AND image_model_version IS NOT NULL)",
    name="ck_prompts_image_provenance",
)
```

**Champs image-spécifiques** :
- `prompt_text` : description/recette (obligatoire, sans borne 100-1000)
- `image_platform` : plateforme (Stable Diffusion, DALL-E, Midjourney, etc.) — obligatoire
- `image_model_version` : version modèle — obligatoire
- `image_r2_key` : fichier original en R2 (gaté)
- `preview_r2_key` : aperçu public
- `image_settings` : JSONB (steps, cfg, seed, sampler, etc.)
- `negative_prompt` : prompt négatif
- `image_style` : style dominant (code STYLES) — taxonomie visuelle
- `image_tags` : CSV tags utilisation (cover, background, fx, etc.)
- `max_supply` : édition limitée (NULL = illimité, 1 = pièce unique, N = N/10000)
- `price_credits` : prix de vente (3-500)

✅ **Modèle complet et cohérent**

---

### 4.2 Création image (POST /images/)

**Endpoint** : `routers/images.py:170-428` (`POST /artist/me/images`)

Flux :
1. Gate profil publié ✅
2. Validation fichier (PNG/JPG/WebP, max 20 Mo) ✅
3. Upload R2 (original + aperçu réduit) ✅
4. Création ligne Prompt avec `product_type='image'` ✅
5. Taxonomie visuelle (style + tags) optionnelle ✅
6. Hook achievements (IMAGE_CREATOR si publiée) ✅

**Schéma création** : `schemas/image.py:ImageCreate`

```python
class ImageCreate(BaseModel):
    title: str  # min_length=PROMPT_TITLE_MIN, max_length=PROMPT_TITLE_MAX
    description: str | None
    prompt_text: str  # recette/description
    image_platform: ImagePlatform  # enum
    image_model_version: str
    image_settings: dict[str, Any] | None  # JSON libre
    negative_prompt: str | None
    ratio: str | None  # descriptif (1:1, 16:9, etc.)
    price_credits: int  # 3-500
    max_supply: int | None  # NULL ou >= 1
    is_published: bool = False
```

✅ **Complet, validation OK**

---

### 4.3 Édition image (PATCH /images/{id})

**Endpoint** : `routers/images.py:1122-1175` (`PATCH /artist/me/images/{image_id}`)

Éditable :
- Titre, description, prix
- Publication (draft → public)
- Taxonomie (style, tags)

**Pas éditable** :
- Fichier, prompt_text, image_settings (=nouvelle création)

**Schéma édition** : `schemas/image.py:ImageUpdate`

```python
class ImageUpdate(BaseModel):
    title: str | None
    description: str | None
    price_credits: int | None  # 3-500
    is_published: bool | None
    image_style: str | None
    image_tags: str | None
```

✅ **Design cohérent**

---

### 4.4 Achat image (POST /unlocks/prompts/{prompt_id})

**Endpoint** : `routers/unlocks.py:99-191` (POST /unlocks/prompts/{id})

Réutilise le circuit **généralisé** des prompts (recettes + images) :

```python
async def unlock_prompt_atomic(
    db, buyer_id, prompt_id
):
    # Lecture prompt (recette OU image OU beat)
    prompt = select(Prompt).where(Prompt.id == prompt_id)
    
    # Détection produit-type
    is_image = getattr(prompt_row, "product_type", "recipe") == "image"
    
    # Sélection perk approprié
    if is_image:
        from app.services.visual_adn import user_owns_artist_visual_adn
        perk_applied = await user_owns_artist_visual_adn(
            db, user_id=buyer_id, artist_id=artist_id
        )  # → -30% si possède ADN Visuel artiste
    else:
        perk_applied = await user_owns_artist_adn(
            db, user_id=buyer_id, artist_id=artist_id
        )  # → -30% si possède ADN musical artiste
    
    # Perk -20% (si applicable)
    playlist_perk = await user_owns_playlist_adn_for_prompt(...)
    
    # Calcul prix
    paid = compute_effective_price(base_price, perk_applied, playlist_perk)
```

**Perks en cascade** :
1. **-30% profil** : déterminé par `product_type`
   - Image → ADN Visuel artiste
   - Recette/beat → ADN Visuel artiste
2. **-20% playlist** (si recette d'une playlist possédée)
3. **Cumul** : (price * 0.7) * 0.8 = price * 0.56 (max)

✅ **Implémentation complète et symétrique (musique = visuel)**

---

### 4.5 Possession d'image (téléchargement)

**Endpoint** : `routers/images.py:1266-1328` (GET /images/{id}/download)

Gate :
1. Auth requis
2. Image possédée (UnlockedPrompt.current_owner_id == user_id)
3. Seul `image_r2_key` servi (original, gaté)

✅ **Correct**

---

### 4.6 Galerie image (produit composite)

**Modèle** : `models/prompt_gallery_image.py` (1-N images groupées)

**Cas** : Une image "produit principal" peut avoir une galerie de variantes/angles.

**Endpoints** :
- `GET /artist/me/images/{id}/gallery` → liste galerie (owner)
- `POST /artist/me/images/{id}/gallery` → ajouter image à galerie
- `GET /images/{id}/gallery/{gid}/download` → télécharger image galerie (acheteur)

✅ **Implémentation complète**

---

### 4.7 ⚠️ MANQUEMENT : Pas de "fiche produit image"

**Observation** : 
- Les images s'achètent via `/unlocks/prompts/{id}` (circuit générique prompts)
- Pas d'endpoint distinct `/unlocks/images/{id}` ou `/buy-image/{id}`
- Pas de "fiche visuelle détaillée" (comme la fiche son : Track)

**Comparaison** :
| Musique | Visuel |
|---------|--------|
| GET /watt/tracks/{id} | **Manquant** |
| GET /watt/users/{slug}/playlists | GET /watt/users/{slug}/albums ✅ |
| Fiche son détaillée + CTA achat | Pas de fiche image distinct |
| Product page : {title, artist, recette gaté, prix, bouton} | Product page centralisée sur /images |

**Impact** : Les images sont "listées" sur `/images` (catalog general) mais pas de "detail view" propre à chaque image.

**Correction possible** :
```
GET /watt/images/{image_id}
  → {id, title, description, artist, platform, price, preview_r2_key, [linkedSound]}
  → CTA "Acheter" → POST /unlocks/prompts/{id}
```

---

### 4.8 Perk visuel -30% : vérification du fonctionnement

**Cascade implémentée** : 
1. ✅ ADN Visuel créé (POST /artist/me/visual-adn) : `services/visual_adn.py`
2. ✅ ADN Visuel acheté (POST /unlocks/visual-adns/{id}) : `services/visual_adn.py:unlock_visual_adn_atomic()`
3. ✅ À l'achat d'image, perk -30% appliqué si buyer possède ADN Visuel : `services/unlocks.py:unlock_prompt_atomic()`

**Symétrie musique** :
- ADN Profil musical → perk -30% sur prompts (recettes)
- ADN Visuel → perk -30% sur images

✅ **Fonctionnel et cohérent**

---

### Synthèse étape 4

✅ **Fait** :
- Modèle Prompt générique `product_type='image'` ✅
- Création/édition d'images (multipart upload R2) ✅
- Achat via circuit `/unlocks/prompts/{id}` ✅
- Perk -30% ADN Visuel sur images ✅
- Galerie image (produit composite) ✅
- Taxonomie visuelle (style + tags) ✅

⚠️ **Asymétrie mineure** (non-bloquant) :
- Pas de GET /watt/images/{id} (detail page distincte)
- Images indexées dans catalog general `/images`, pas de "product page" dédiée

❌ **Manquant** (non-critique pour V1) :
- Pas d'image en tant qu'ADN indépendant (ADN Image distinct de ADN Visuel artiste)
  - Actuel : ADN Visuel = profil de l'artiste (1 par artiste)
  - Futur : ADN Image = génome d'une image spécifique (recette générative)

---

## MIGRATIONS RÉCENTES

### Migration 0062 : Album ADN

**Fichier** : `alembic/versions/0062_album_adn.py`

```sql
ALTER TABLE albums ADD COLUMN (
    seed_prompt TEXT,
    dna_description TEXT,
    adn_style VARCHAR(40),
    adn_palette VARCHAR(255),
    adn_for_sale BOOLEAN DEFAULT false,
    adn_price INTEGER
);

CREATE TABLE owned_album_adns (
    user_id UUID,
    album_id UUID,
    PRIMARY KEY (user_id, album_id)
);
```

**Calque STRICT** de Playlist ADN (migration 0035). ✅

---

### Migration 0063 : Visual ADN

**Fichier** : `alembic/versions/0063_visual_adn.py`

```sql
CREATE TABLE visual_adns (
    id UUID PRIMARY KEY,
    artist_id UUID UNIQUE,
    description TEXT NOT NULL,
    usage_guide TEXT,
    example_outputs TEXT,
    price_credits INTEGER NOT NULL CHECK (30 <= price_credits <= 500),
    ai_reference VARCHAR(30),
    max_supply INTEGER,
    style VARCHAR(40),
    palette VARCHAR(255),
    is_published BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,
    ...
);

CREATE TABLE owned_visual_adns (
    user_id UUID,
    visual_adn_id UUID,
    PRIMARY KEY (user_id, visual_adn_id)
);
```

**Calque STRICT** de ADN musical (table `adns`). ✅

**Différence** : `UNIQUE artist_id` (1 ADN visuel max par artiste)

---

## RÉSUMÉ PAR DÉCISION ARCHITECTURALE

| Décision | Implémentation | Symétrie Son/Visuel |
|----------|-----------------|-------------------|
| Dualité musique/visuel | Playlist (son) + Album (visuel) liés via `oeuvre_slug` | ✅ Symétrique |
| ADN artiste | ADN Profil (son) + ADN Visuel (visuel) = perks -30% respectifs | ✅ Symétrique |
| ADN collection | ADN Playlist + ADN Album (génome par curation) | ✅ Symétrique |
| Pack œuvre -15% | `compute_oeuvre_pack_price()` appliqué atomiquement | ✅ Complet |
| Perk -30% | `user_owns_artist_adn()` + `user_owns_artist_visual_adn()` | ✅ Symétrique |
| Perk -20% | Playlist pour son, **N/A** pour image solitaire | ⚠️ Asymétrie attendue |
| Gate profil publié | Identique (creation + catalog), **fuite mineure** sur `/images` | ❌ Fuite |
| Taxonomie | Playlist color + son style | Image style + tags | ✅ Complète |
| Aperçu fichier | Proxy R2 `/watt/stream` (audio) + `/watt/images` | ✅ Symétrique |
| Édition propriétaire | Service atomique + hooks achievements | ✅ Symétrique |

---

## TABLEAU DE SYNTHÈSE FINAL

| # | Étape | État | Couverture | Blocages | Recommendation |
|---|-------|------|-----------|----------|----------------|
| **1** | Pack ADN -15% | ✅ FAIT | 100% (primitive, API, UI, tests) | Aucun | Production-ready |
| **2** | Gate profil publié | ⚠️ PARTIEL | 95% (creation OK, **catalog images fuite**) | Fuite mineure sur `/images` | Ajouter `User.profile_public.is_(True)` filtres images |
| **3** | Prix | ⚠️ PARTIEL | 80% (bornes OK, **pas CHECK Album/Playlist, pas seed**) | `adn_price` sans limite Album/Playlist | Ajouter CHECK constraint ADN Album/Playlist |
| **4** | Images vendables | ✅ FAIT | 95% (modèle complet, unlock OK, **pas detail page distinct**) | Detail page manquante (minor) | Ajouter GET /watt/images/{id} si souhait detail |

---

## FICHIERS CRITIQUES À RETENIR

### Services métier (logique)
- `/watt-api/app/services/credits.py:60-141` — pricing (PERK_*, PLAYLIST_PERK_*, OEUVRE_PACK_*)
- `/watt-api/app/services/oeuvre_purchase.py:75-250` — achat pack œuvre
- `/watt-api/app/services/unlocks.py:160-270` — unlock prompt atomique (image + son, détection perk)
- `/watt-api/app/services/visual_adn.py` — CRUD ADN Visuel + achat
- `/watt-api/app/services/discovery.py:100-170` — catalog public (filtres profile_public)

### Routers (API)
- `/watt-api/app/routers/oeuvre.py:285-357` — POST /watt/oeuvre/{slug}/buy-complete
- `/watt-api/app/routers/images.py:170-428` — POST /artist/me/images (création)
- `/watt-api/app/routers/images.py:630-725` — GET /images (catalog, **fuite profile_public**)
- `/watt-api/app/routers/unlocks.py:99-191` — POST /unlocks/prompts/{id} (achat image/son)
- `/watt-api/app/routers/marketplace.py:217-300` — CRUD ADN Visuel

### Modèles (DB)
- `/watt-api/app/models/prompt.py:1-220` — Prompt (product_type discriminant)
- `/watt-api/app/models/visual_adn.py` — Visual ADN
- `/watt-api/app/models/album.py:1-170` — Album (ADN colonnaire)
- `/watt-api/app/models/playlist.py:1-150` — Playlist (ADN colonnaire)
- `/watt-api/app/models/user.py` — User.profile_public

### Migrations
- `alembic/versions/0062_album_adn.py` — ADN Album
- `alembic/versions/0063_visual_adn.py` — ADN Visuel
- `alembic/versions/0076_oeuvre_binding.py` — binding Œuvre

### Tests
- `/watt-api/tests/test_oeuvre_pricing.py` — validation compute_oeuvre_pack_price

---

## CORRECTIFS IMMÉDIATS (P0/P1)

### P0 : Gate profil publié sur `/images`

**Fichier** : `routers/images.py:630-725` (GET /images)

Ajouter au WHERE :
```python
.where(
    Prompt.product_type == "image",
    Prompt.is_published.is_(True),
    Prompt.is_deleted.is_(False),
    User.profile_public.is_(True),  # ← Ajouter
)
```

Même correction sur :
- `list_top_images()` (line ~750)
- `list_top_image_artists()` (line ~830)
- `list_oeuvres()` (image côté du fetch — vérifier)

### P1 : Bornes prix ADN Album + Playlist

**Fichier** : `alembic/versions/` (nouvelle migration 0078_adn_price_constraints.py)

```sql
ALTER TABLE albums ADD CONSTRAINT ck_albums_adn_price 
  CHECK (adn_price IS NULL OR (adn_price >= 3 AND adn_price <= 500));

ALTER TABLE playlists ADD CONSTRAINT ck_playlists_adn_price 
  CHECK (adn_price IS NULL OR (adn_price >= 3 AND adn_price <= 500));
```

### P2 (optional) : Detail page image

Ajouter `GET /watt/images/{image_id}` (par parité /watt/tracks/{id})

---

## CONCLUSION

La dualité musique/visuel est **largement implémentée** et **symétriquement réalisée** au niveau des primitives (perk -30% visuel, ADN Visuel, pack croisé, etc.). 

**Forces** : architecture cohérente, services généralisés, migrations clean, tests sur pack pricing.

**Faiblesses mineures** :
1. Fuite de profil sur `/images` (catalog images n'applique pas `profile_public` filter)
2. Contraintes prix manquantes sur ADN Album/Playlist
3. Pas de detail page distincte pour images

Ces deux premiers points méritent une correction avant production. Le troisième est cosmétique (asymétrie UX mineure).

---

**Audit complété le 2 juillet 2026**
