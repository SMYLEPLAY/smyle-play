"""redenomination_x10 — l'unité Smyle est multipliée par 10 (décision du 9/10/2026)

Revision ID: 0100_redenomination_x10
Revises: 0099_reclasse_gagnes_promo
Create Date: 2026-10-09

POURQUOI. Aucun euro réel n'est encore entré (paiement par carte éteint, seuls
des Smyles de bêta circulent). On change l'unité maintenant pour qu'un produit
coûte 1 à 3 € avec une commission exacte en nombres entiers : 1 ancien Smyle
vaut désormais 10 Smyles. Les prix en euros des packs ne changent pas
(100 / 500 / 2000 Smyles pour 8 / 35 / 120 €) et la valeur de retrait d'un
Smyle gagné passe de 50 à 5 centimes : la valeur en euros détenue par chacun
est STRICTEMENT inchangée.

CE QUI EST MULTIPLIÉ PAR 10 (toutes les colonnes exprimées en Smyles) :
  users            credits_balance, smyles_achetes, smyles_gagnes,
                   smyles_promo, smyles_gagnes_bloque, smyles_promo_gagnes,
                   credits_earned_total
  transactions     credits_amount, platform_fee, artist_revenue, promo_paid,
                   promo_non_retirable + montants dans metadata_json
                   (base_price, seller_cut, listed_price, remise_oeuvre,
                   fee_floor, promo.vendeur, promo.artiste)
  adns / visual_adns           price_credits, adn_reserve_credits
  albums / playlists           adn_price, adn_reserve_credits
  voices_for_sale              price_credits
  tracks                       pack_price_credits
  trade_offers                 amount_credits, credit_supplement,
                               offered_price_at_trade, requested_price_at_trade
  unlocked_prompts             resale_price
  referrals                    reward_credits
  achievements                 credit_reward, et le seuil de l'axe « artist »
                               (exprimé en Smyles gagnés), sauf le seuil 1
                               (« première vente »)
  stripe_payments              credits, smyles_recovered, shortfall
                               (amount_cents en euros : inchangé) ; pack_id
                               renommé pack_10/50/200 → pack_100/500/2000
  notifications                metadata_json.amount (montant affiché)
Les bornes CHECK en Smyles suivent (ADN ≥ 300, ADN visuel 300..5000, voix
500..50000, ADN de collection 1..1 000 000).

PRIX DES RECETTES, IMAGES ET ŒUVRES (table prompts) — nouvelle règle : prix
libre entre 10 et 150 Smyles. L'existant (tous comptes) est ramené dans la
fourchette conseillée de 1 à 3 € (décision de Tom : recettes accessibles) :
  - ancien prix ≤ 30 → 15 (≈ 1 €) ;
  - ancien prix 31–60 → 30 (≈ 2 €) ;
  - ancien prix > 60 → 45 (≈ 3 €).
Un simple ×10 aurait mis presque tout le catalogue de la bêta (25–80) au
plafond de 150 (≈ 10 €). Chaque vendeur peut ensuite changer son prix depuis
« Mes Œuvres ». (Il n'existe pas de notion de « mise en vitrine » par
produit : la règle « vitrine → 30 » n'a rien à cibler.) Chaque prix qui ne vaut pas exactement
ancien × 10 est tracé dans admin_journal (action 'redenomination_prix', état
AVANT) : le downgrade s'en sert pour restaurer le prix exact.

REGISTRE APPEND-ONLY. Le registre `transactions` est protégé par deux
déclencheurs qui refusent toute modification d'un montant
(trg_transactions_immutable, enforce_transaction_immutability). Pour CETTE
mise à l'échelle unique, ils sont désactivés le temps des UPDATE, DANS la
transaction de la migration, puis réactivés immédiatement : si quoi que ce
soit échoue, Postgres annule tout, déclencheurs compris. Choix : multiplier
l'historique plutôt qu'écrire une ligne d'ajustement par compte — une ligne
d'ajustement aurait laissé tout l'historique dans l'ancienne unité (prix,
commissions, ventes affichées « 3 Smyles » au lieu de 30), faussé les
tableaux de bord et le calcul de maturation des gains, et cassé la
réconciliation « masse créée − commission = soldes ». La multiplication
préserve tous les invariants : somme des réserves = solde (chaque terme ×10),
partage artiste + commission = montant, promo_non_retirable ≤ promo_paid ≤
montant, et réconciliation registre ↔ soldes. Une ligne de synthèse est
écrite dans admin_journal (action 'redenomination_x10').

DOWNGRADE : division par 10. Exacte tant qu'aucune activité n'a eu lieu après
la migration ; sinon arrondi à l'inférieur, en gardant tous les invariants
(chaque solde est recalculé comme la somme de ses réserves). Les prix
modifiés de façon non proportionnelle sont restaurés depuis admin_journal.
"""
from alembic import op

revision = "0100_redenomination_x10"
down_revision = "0099_reclasse_gagnes_promo"
branch_labels = None
depends_on = None

FACTEUR = 10
PRIX_MIN = 10
PRIX_MAX = 150

ACTION_SYNTHESE = "redenomination_x10"
ACTION_PRIX = "redenomination_prix"

# Déclencheurs d'immuabilité du registre (0009 + 0070).
_TRIGGERS_REGISTRE = ("trg_transactions_immutable", "enforce_transaction_immutability")

# Colonnes en Smyles multipliées/divisées simplement (table, colonne).
_COLONNES_SIMPLES = [
    ("adns", "price_credits"),
    ("adns", "adn_reserve_credits"),
    ("visual_adns", "price_credits"),
    ("visual_adns", "adn_reserve_credits"),
    ("albums", "adn_price"),
    ("albums", "adn_reserve_credits"),
    ("playlists", "adn_price"),
    ("playlists", "adn_reserve_credits"),
    ("voices_for_sale", "price_credits"),
    ("tracks", "pack_price_credits"),
    ("trade_offers", "amount_credits"),
    ("trade_offers", "credit_supplement"),
    ("trade_offers", "offered_price_at_trade"),
    ("trade_offers", "requested_price_at_trade"),
    ("unlocked_prompts", "resale_price"),
    ("referrals", "reward_credits"),
    ("achievements", "credit_reward"),
    ("stripe_payments", "credits"),
    ("stripe_payments", "smyles_recovered"),
    ("stripe_payments", "shortfall"),
]

# Montants en Smyles rangés dans transactions.metadata_json (clés de 1er niveau).
_META_CLES = ("base_price", "seller_cut", "listed_price", "remise_oeuvre", "fee_floor")
# Sous-objet metadata_json.promo = {"vendeur": n, "artiste": n} (revente).
_META_PROMO_CLES = ("vendeur", "artiste")

_PACKS = (("pack_10", "pack_100"), ("pack_50", "pack_500"), ("pack_200", "pack_2000"))

# Libellés des trophées de l'axe « artist » (seuil en Smyles gagnés).
_TROPHEES_ARTISTE = (
    ("artist_10_credits", "10 crédits gagnés", "100 Smyles gagnés"),
    ("artist_100_credits", "100 crédits gagnés", "1000 Smyles gagnés"),
    ("artist_1000_credits", "1000 crédits gagnés", "10000 Smyles gagnés"),
)

# Bornes CHECK en Smyles : (table, nom, avant, après).
_CHECKS = [
    ("adns", "ck_adns_price_credits_min",
     "price_credits >= 30", "price_credits >= 300"),
    ("visual_adns", "ck_visual_adns_price_credits_range",
     "price_credits >= 30 AND price_credits <= 500",
     "price_credits >= 300 AND price_credits <= 5000"),
    ("voices_for_sale", "ck_voices_price_credits_range",
     "price_credits >= 50 AND price_credits <= 5000",
     "price_credits >= 500 AND price_credits <= 50000"),
    ("playlists", "ck_playlists_adn_price_bounds",
     "adn_price IS NULL OR (adn_price >= 1 AND adn_price <= 100000)",
     "adn_price IS NULL OR (adn_price >= 1 AND adn_price <= 1000000)"),
    ("albums", "ck_albums_adn_price_bounds",
     "adn_price IS NULL OR (adn_price >= 1 AND adn_price <= 100000)",
     "adn_price IS NULL OR (adn_price >= 1 AND adn_price <= 1000000)"),
]
_CK_PROMPTS_AVANT = ("ck_prompts_price_credits_min", "price_credits >= 3")
_CK_PROMPTS_APRES = (
    "ck_prompts_price_credits_range",
    f"price_credits >= {PRIX_MIN} AND price_credits <= {PRIX_MAX}",
)


def _sql_meta(op_sql: str) -> str:
    """UPDATE des montants de transactions.metadata_json. `op_sql` est
    l'expression appliquée à `v` (la valeur numérique d'origine)."""
    stmts = []
    for k in _META_CLES:
        v = f"(metadata_json->>'{k}')::bigint"
        stmts.append(
            "UPDATE transactions SET metadata_json = jsonb_set(metadata_json, "
            f"'{{{k}}}', to_jsonb({op_sql.format(v=v)})) "
            f"WHERE jsonb_typeof(metadata_json->'{k}') = 'number'"
        )
    for k in _META_PROMO_CLES:
        v = f"(metadata_json->'promo'->>'{k}')::bigint"
        stmts.append(
            "UPDATE transactions SET metadata_json = jsonb_set(metadata_json, "
            f"'{{promo,{k}}}', to_jsonb({op_sql.format(v=v)})) "
            f"WHERE jsonb_typeof(metadata_json->'promo'->'{k}') = 'number'"
        )
    return stmts


def _registre(enable: bool) -> list[str]:
    mot = "ENABLE" if enable else "DISABLE"
    return [f"ALTER TABLE transactions {mot} TRIGGER {t}" for t in _TRIGGERS_REGISTRE]


# ─── UPGRADE ────────────────────────────────────────────────────────────────

UPGRADE_SQL: list[str] = []

# 0. Synthèse AVANT (masse en circulation, nombre de comptes).
UPGRADE_SQL.append(
    "INSERT INTO admin_journal (id, admin_id, action, cible_type, cible_id, motif, details) "
    f"SELECT gen_random_uuid(), NULL, '{ACTION_SYNTHESE}', 'plateforme', '0100', "
    "'Redénomination : 1 ancien Smyle = 10 Smyles (décision du 9/10/2026).', "
    "jsonb_build_object('comptes', count(*), "
    "  'masse_avant', COALESCE(sum(credits_balance), 0), "
    "  'transactions', (SELECT count(*) FROM transactions)) "
    "FROM users"
)

# 1. Les bornes qui bloqueraient la mise à l'échelle sont retirées d'abord.
for _t, _n, _avant, _apres in _CHECKS:
    UPGRADE_SQL.append(f"ALTER TABLE {_t} DROP CONSTRAINT IF EXISTS {_n}")
UPGRADE_SQL.append(f"ALTER TABLE prompts DROP CONSTRAINT IF EXISTS {_CK_PROMPTS_AVANT[0]}")

# 2. Soldes : les sept compteurs d'une ligne passent ensemble (le CHECK de
#    somme est évalué sur la ligne finale).
UPGRADE_SQL.append(
    "UPDATE users SET "
    f"credits_balance = credits_balance * {FACTEUR}, "
    f"smyles_achetes = smyles_achetes * {FACTEUR}, "
    f"smyles_gagnes = smyles_gagnes * {FACTEUR}, "
    f"smyles_promo = smyles_promo * {FACTEUR}, "
    f"smyles_gagnes_bloque = smyles_gagnes_bloque * {FACTEUR}, "
    f"smyles_promo_gagnes = smyles_promo_gagnes * {FACTEUR}, "
    f"credits_earned_total = credits_earned_total * {FACTEUR}"
)

# 3. Registre : déclencheurs coupés UNIQUEMENT pendant ces UPDATE.
UPGRADE_SQL += _registre(False)
UPGRADE_SQL.append(
    "UPDATE transactions SET "
    f"credits_amount = credits_amount * {FACTEUR}, "
    f"platform_fee = platform_fee * {FACTEUR}, "
    f"artist_revenue = artist_revenue * {FACTEUR}, "
    f"promo_paid = promo_paid * {FACTEUR}, "
    f"promo_non_retirable = promo_non_retirable * {FACTEUR}"
)
UPGRADE_SQL += _sql_meta("{v} * " + str(FACTEUR))
UPGRADE_SQL += _registre(True)

# 4. Prix et compteurs en Smyles des autres tables.
for _t, _c in _COLONNES_SIMPLES:
    UPGRADE_SQL.append(
        f"UPDATE {_t} SET {_c} = {_c} * {FACTEUR} WHERE {_c} IS NOT NULL"
    )
UPGRADE_SQL.append(
    f"UPDATE achievements SET threshold = threshold * {FACTEUR} "
    "WHERE axis = 'artist' AND threshold > 1"
)
for _code, _avant, _apres in _TROPHEES_ARTISTE:
    UPGRADE_SQL.append(
        f"UPDATE achievements SET description = '{_apres}' WHERE code = '{_code}'"
    )
for _ancien, _nouveau in _PACKS:
    UPGRADE_SQL.append(
        f"UPDATE stripe_payments SET pack_id = '{_nouveau}' WHERE pack_id = '{_ancien}'"
    )
UPGRADE_SQL.append(
    "UPDATE notifications SET metadata_json = jsonb_set(metadata_json, '{amount}', "
    f"to_jsonb((metadata_json->>'amount')::bigint * {FACTEUR})) "
    "WHERE jsonb_typeof(metadata_json->'amount') = 'number'"
)

# 5. Prix des recettes / images / Œuvres. D'abord la trace des prix qui ne
#    suivent pas exactement ×10 (état AVANT), puis la nouvelle valeur.
_NOUVEAU_PRIX = (
    "CASE "
    "  WHEN p.price_credits <= 30 THEN 15 "
    "  WHEN p.price_credits <= 60 THEN 30 "
    "  ELSE 45 "
    "END"
)
UPGRADE_SQL.append(
    "INSERT INTO admin_journal (id, admin_id, action, cible_type, cible_id, motif, details) "
    f"SELECT gen_random_uuid(), NULL, '{ACTION_PRIX}', 'prompt', CAST(p.id AS text), "
    "'Redénomination : prix ramené dans la fourchette 10–150 Smyles.', "
    f"jsonb_build_object('avant', p.price_credits, 'apres', {_NOUVEAU_PRIX}) "
    "FROM prompts p "
    f"WHERE {_NOUVEAU_PRIX} <> p.price_credits * {FACTEUR}"
)
UPGRADE_SQL.append(f"UPDATE prompts p SET price_credits = {_NOUVEAU_PRIX}")

# 6. Nouvelles bornes.
for _t, _n, _avant, _apres in _CHECKS:
    UPGRADE_SQL.append(f"ALTER TABLE {_t} ADD CONSTRAINT {_n} CHECK ({_apres})")
UPGRADE_SQL.append(
    f"ALTER TABLE prompts ADD CONSTRAINT {_CK_PROMPTS_APRES[0]} CHECK ({_CK_PROMPTS_APRES[1]})"
)


# ─── DOWNGRADE ──────────────────────────────────────────────────────────────

DOWNGRADE_SQL: list[str] = []

for _t, _n, _avant, _apres in _CHECKS:
    DOWNGRADE_SQL.append(f"ALTER TABLE {_t} DROP CONSTRAINT IF EXISTS {_n}")
DOWNGRADE_SQL.append(f"ALTER TABLE prompts DROP CONSTRAINT IF EXISTS {_CK_PROMPTS_APRES[0]}")

# Prix : restauration exacte depuis le journal quand il existe, sinon ÷10.
DOWNGRADE_SQL.append(
    f"UPDATE prompts SET price_credits = GREATEST(3, price_credits / {FACTEUR}) "
    "WHERE CAST(id AS text) NOT IN (SELECT cible_id FROM admin_journal "
    f"  WHERE action = '{ACTION_PRIX}')"
)
DOWNGRADE_SQL.append(
    "UPDATE prompts p SET price_credits = (j.details->>'avant')::int "
    "FROM (SELECT DISTINCT ON (cible_id) cible_id, details FROM admin_journal "
    f"      WHERE action = '{ACTION_PRIX}' ORDER BY cible_id, created_at DESC) j "
    "WHERE CAST(p.id AS text) = j.cible_id"
)
DOWNGRADE_SQL.append(f"DELETE FROM admin_journal WHERE action = '{ACTION_PRIX}'")

DOWNGRADE_SQL.append(
    "UPDATE notifications SET metadata_json = jsonb_set(metadata_json, '{amount}', "
    f"to_jsonb((metadata_json->>'amount')::bigint / {FACTEUR})) "
    "WHERE jsonb_typeof(metadata_json->'amount') = 'number'"
)
for _ancien, _nouveau in _PACKS:
    DOWNGRADE_SQL.append(
        f"UPDATE stripe_payments SET pack_id = '{_ancien}' WHERE pack_id = '{_nouveau}'"
    )
for _code, _avant, _apres in _TROPHEES_ARTISTE:
    DOWNGRADE_SQL.append(
        f"UPDATE achievements SET description = '{_avant}' WHERE code = '{_code}'"
    )
DOWNGRADE_SQL.append(
    f"UPDATE achievements SET threshold = GREATEST(2, threshold / {FACTEUR}) "
    "WHERE axis = 'artist' AND threshold > 1"
)
# Colonnes simples : ÷10, en gardant les planchers d'origine (prix ≥ 1,
# minimums d'ADN / voix) pour que les anciennes bornes restent vraies.
_PLANCHERS = {
    ("adns", "price_credits"): 30,
    ("visual_adns", "price_credits"): 30,
    ("voices_for_sale", "price_credits"): 50,
    ("albums", "adn_price"): 1,
    ("playlists", "adn_price"): 1,
    ("tracks", "pack_price_credits"): 1,
    ("trade_offers", "amount_credits"): 1,
    ("unlocked_prompts", "resale_price"): 1,
    ("referrals", "reward_credits"): 1,
    ("stripe_payments", "credits"): 1,
}
for _t, _c in _COLONNES_SIMPLES:
    if _t == "stripe_payments":
        continue  # traité en une instruction ci-dessous (CHECK croisé)
    _p = _PLANCHERS.get((_t, _c))
    _expr = f"{_c} / {FACTEUR}" if _p is None else f"GREATEST({_p}, {_c} / {FACTEUR})"
    DOWNGRADE_SQL.append(f"UPDATE {_t} SET {_c} = {_expr} WHERE {_c} IS NOT NULL")
_CREDITS = f"GREATEST(1, credits / {FACTEUR})"
_RECUP = f"LEAST(smyles_recovered / {FACTEUR}, {_CREDITS})"
DOWNGRADE_SQL.append(
    "UPDATE stripe_payments SET "
    f"credits = {_CREDITS}, "
    f"smyles_recovered = {_RECUP}, "
    f"shortfall = LEAST(shortfall / {FACTEUR}, {_CREDITS} - {_RECUP})"
)

DOWNGRADE_SQL += _registre(False)
# Montant ≥ 1 ; partage recalculé pour que artiste + commission = montant
# (déblocages) ou ≤ montant (autres types) ; parts promo bornées.
# Une seule instruction : les CHECK du registre sont évalués sur la ligne
# finale (toutes les expressions lisent les valeurs d'AVANT).
_MONTANT = f"GREATEST(1, credits_amount / {FACTEUR})"
_ARTISTE = f"LEAST(artist_revenue / {FACTEUR}, {_MONTANT})"
_PROMO = f"LEAST(promo_paid / {FACTEUR}, {_MONTANT})"
DOWNGRADE_SQL.append(
    "UPDATE transactions SET "
    f"credits_amount = {_MONTANT}, "
    f"artist_revenue = {_ARTISTE}, "
    f"platform_fee = CASE WHEN type = 'unlock' THEN {_MONTANT} - {_ARTISTE} "
    f"  ELSE LEAST(platform_fee / {FACTEUR}, {_MONTANT} - {_ARTISTE}) END, "
    f"promo_paid = {_PROMO}, "
    f"promo_non_retirable = LEAST(promo_non_retirable / {FACTEUR}, {_PROMO})"
)
DOWNGRADE_SQL += _sql_meta("{v} / " + str(FACTEUR))
DOWNGRADE_SQL += _registre(True)

# Soldes : chaque réserve ÷10, le solde redevient la somme des réserves.
DOWNGRADE_SQL.append(
    "UPDATE users SET "
    f"smyles_achetes = smyles_achetes / {FACTEUR}, "
    f"smyles_gagnes = smyles_gagnes / {FACTEUR}, "
    f"smyles_promo = smyles_promo / {FACTEUR}, "
    f"smyles_gagnes_bloque = LEAST(smyles_gagnes_bloque / {FACTEUR}, smyles_gagnes / {FACTEUR}), "
    f"smyles_promo_gagnes = LEAST(smyles_promo_gagnes / {FACTEUR}, smyles_promo / {FACTEUR}), "
    f"credits_earned_total = credits_earned_total / {FACTEUR}, "
    f"credits_balance = smyles_achetes / {FACTEUR} + smyles_gagnes / {FACTEUR} "
    f"  + smyles_promo / {FACTEUR}"
)

for _t, _n, _avant, _apres in _CHECKS:
    DOWNGRADE_SQL.append(f"ALTER TABLE {_t} ADD CONSTRAINT {_n} CHECK ({_avant})")
DOWNGRADE_SQL.append(
    f"ALTER TABLE prompts ADD CONSTRAINT {_CK_PROMPTS_AVANT[0]} CHECK ({_CK_PROMPTS_AVANT[1]})"
)
DOWNGRADE_SQL.append(f"DELETE FROM admin_journal WHERE action = '{ACTION_SYNTHESE}'")


def upgrade() -> None:
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in DOWNGRADE_SQL:
        op.execute(sql)
