-- ─────────────────────────────────────────────────────────────────────────
-- Fixture CI « configuration jour J » (workflow e2e.yml, variante jour-j).
-- NE S'APPLIQUE QU'À LA BASE ÉPHÉMÈRE DE LA CI — jamais à la production.
--
-- Le 1er novembre, REQUIRE_EMAIL_VERIFIED=true : un compte doit confirmer son
-- email (lien reçu par Resend) avant de se connecter. La CI n'a pas de boîte
-- mail ; ce déclencheur marque donc comme vérifiés, À LA CRÉATION, les comptes
-- de test des smokes (e2e-…@smyleplay.example). Les comptes
-- « e2e-nonverifie-… » restent NON vérifiés : smoke-jour-j.spec.js s'en sert
-- pour prouver que la connexion est bien refusée.
-- ─────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e2e_jour_j_email_verifie() RETURNS trigger AS $$
BEGIN
  IF NEW.email LIKE 'e2e-%@smyleplay.example'
     AND NEW.email NOT LIKE 'e2e-nonverifie-%' THEN
    NEW.email_verified := true;
  END IF;
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS e2e_jour_j_email_verifie ON users;
CREATE TRIGGER e2e_jour_j_email_verifie
  BEFORE INSERT ON users
  FOR EACH ROW EXECUTE FUNCTION e2e_jour_j_email_verifie();
