"""Lot G — migrations 0101/0102 face à une base de production réelle.

0102 vide `analytics_events.user_id` puis pose un CHECK (user_id IS NULL).
L'ancienne version de l'application reste en ligne pendant la migration et
écrit encore des événements rattachés à un compte : la table doit être
verrouillée AVANT l'UPDATE, sinon une ligne insérée entre-temps ferait
échouer la validation du CHECK (et donc le déploiement).
"""
import importlib.util
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _charger(nom):
    spec = importlib.util.spec_from_file_location(nom, VERSIONS / f"{nom}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _OpEnregistreur:
    def __init__(self):
        self.appels = []

    def execute(self, sql):
        self.appels.append(("execute", str(sql)))

    def add_column(self, table, col):
        self.appels.append(("add_column", table))

    def create_check_constraint(self, nom, table, expr):
        self.appels.append(("check", nom))


def test_0102_verrouille_la_mesure_avant_de_la_nettoyer(monkeypatch):
    m = _charger("0102_lot_d_conformite")
    op = _OpEnregistreur()
    monkeypatch.setattr(m, "op", op)
    m.upgrade()
    ordre = [a for a in op.appels if a[0] in ("execute", "check")]
    i_lock = next(i for i, a in enumerate(ordre) if "LOCK TABLE analytics_events" in a[1])
    i_update = next(i for i, a in enumerate(ordre) if "UPDATE analytics_events" in a[1])
    i_check = next(i for i, a in enumerate(ordre) if a == ("check", "ck_analytics_events_sans_compte"))
    assert i_lock < i_update < i_check


def test_0101_et_0102_ne_posent_aucune_contrainte_sur_l_existant():
    """Colonnes neuves toutes NULL-ables ; seul CHECK ajouté : celui de 0102,
    rendu vrai par l'UPDATE qui le précède (sous verrou)."""
    for nom in ("0101_parcours_v1", "0102_lot_d_conformite"):
        src = (VERSIONS / f"{nom}.py").read_text(encoding="utf-8")
        assert "nullable=False" not in src, nom
        assert "server_default" not in src, nom
