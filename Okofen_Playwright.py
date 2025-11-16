import os
import sys
import json
import time
from playwright.sync_api import Playwright, sync_playwright, expect
from dotenv import load_dotenv

# Chargement des variables d'environnement depuis .env (si présent)
load_dotenv()

OKOFEN_URL = os.getenv("OKOFEN_URL")
OKOFEN_USER = os.getenv("OKOFEN_USER")
OKOFEN_PASSWORD = os.getenv("OKOFEN_PASSWORD")


def set_mode(page, target: str):
    """
    target = "off"  -> Auto -> Arrêt
    target = "on"   -> Arrêt -> Auto

    Retourne un tuple:
        (changed, status_before, status_after)

        changed:
            True  si un changement de mode a été demandé (popup OK présente)
            False si aucun changement n'a été effectué

        status_before / status_after:
            "on" | "off" | "unknown"
    """

    print("[TRACE] [set_mode] --- DEBUT set_mode ---")
    # Textes de mode (en haut de page)
    mode_auto = page.get_by_text("ModeAuto")
    mode_arret = page.get_by_text("ModeArrêt")

    # On regarde ce qu'on voit actuellement
    print("[TRACE] [set_mode] Lecture de l'état des modes visibles")
    has_auto = mode_auto.count() > 0
    has_arret = mode_arret.count() > 0

    # Déduction de l'état actuel
    if has_auto and not has_arret:
        status_before = "on"
    elif has_arret and not has_auto:
        status_before = "off"
    else:
        status_before = "unknown"

    print(f"[DEBUG] [set_mode] a. Mode scan: has_auto={has_auto}, has_arret={has_arret}, target={target}")
    changed = False
    status_after = status_before

    if target == "off":
        print("[TRACE] [set_mode] Debut branche target=off")
        # Si on voit déjà "ModeArrêt" sans "ModeAuto", on considère qu'on est déjà à l'arrêt
        if has_arret and not has_auto:
            print("[DEBUG] [set_mode] b. Mode déjà en Arrêt (aucune action)")
            changed = False
            status_after = "off"
            return changed, status_before, status_after

        # Si on voit "ModeAuto", on peut basculer vers Arrêt
        if has_auto:
            print("[TRACE] [set_mode] Click pour passer de Auto à Arrêt")
            expect(mode_auto).to_be_visible(timeout=30000)
            mode_auto.click()
            page.get_by_role("button", name="Arrêt", exact=True).click()
            print("[DEBUG] [set_mode] d. Passage en mode Arrêt demandé")
            changed = True
            status_after = "off"
            return changed, status_before, status_after

        # Cas indéterminé
        print("[DEBUG] [set_mode] e. Impossible de déterminer le mode actuel (target=off), aucune action")
        changed = False
        status_after = "unknown"
        return changed, status_before, status_after

    elif target == "on":
        print("[TRACE] [set_mode] Debut branche target=on")
        # Si on voit déjà "ModeAuto" sans "ModeArrêt", on considère que c'est déjà allumé
        if has_auto and not has_arret:
            print("[DEBUG] [set_mode] f. Mode déjà en Auto (aucune action)")
            changed = False
            status_after = "on"
            return changed, status_before, status_after

        # Si on voit "ModeArrêt", on peut basculer vers Auto
        if has_arret:
            print("[TRACE] [set_mode] Click pour passer de Arrêt à Auto")
            expect(mode_arret).to_be_visible(timeout=30000)
            mode_arret.click()
            page.get_by_role("button", name="Auto").click()
            print("[DEBUG] [set_mode] h. Passage en mode Auto demandé")
            changed = True
            status_after = "on"
            return changed, status_before, status_after

        # Cas indéterminé
        print("[DEBUG] [set_mode] i. Impossible de déterminer le mode actuel (target=on), aucune action")
        changed = False
        status_after = "unknown"
        return changed, status_before, status_after

    else:
        raise ValueError(f"Mode inconnu : {target}")


def run(playwright: Playwright, target_mode: str):
    """
    Exécute la séquence Playwright pour atteindre le mode demandé.

    Retourne:
        (status_before, status_after, changed)
    """
    print(f"[TRACE] [run] === DEBUT run() pour target_mode={target_mode} ===")
    print("[TRACE] [run] Vérification des credentials en environnement")
    if not OKOFEN_USER or not OKOFEN_PASSWORD:
        raise RuntimeError(
            "Les variables d'environnement OKOFEN_USER et OKOFEN_PASSWORD "
            "doivent être définies (voir fichier .env)."
        )

    print("[TRACE] [run] Lancement du navigateur Playwright Chromium")
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        locale="fr-FR",
        timezone_id="Europe/Paris",
        extra_http_headers={
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"
        },
    )
    page = context.new_page()

    print("[TRACE] [run] Set des timeouts par défaut")
    # Timeouts généraux
    page.set_default_timeout(30000)              # 30 s pour clics / fill / goto...
    page.set_default_navigation_timeout(60000)   # 60 s pour les navigations

    # Page de login
    print("[TRACE] [run] Navigation vers la page de login")
    page.goto(f"{OKOFEN_URL}/login.cgi", wait_until="domcontentloaded")

    # On attend tranquillement la ligne "Francais"
    print("[TRACE] [run] Attente de la ligne de choix de langue 'Francais'\n")
    expect(page.get_by_role("row", name="Francais")).to_be_visible(timeout=30000)

    print("[TRACE] [run] Remplissage des identifiants utilisateur")
    page.get_by_role("textbox", name="Identifiant:").fill(OKOFEN_USER)
    page.get_by_role("textbox", name="Mot de passe:").fill(OKOFEN_PASSWORD)
    print("[TRACE] [run] Clic sur le bouton 'Accès'")
    page.get_by_role("button", name="Accès").click()

    print("[TRACE] [run] Attente du réseau après login (networkidle)")
    page.wait_for_load_state("networkidle")

    # Accueil / page principale
    print("[TRACE] [run] Navigation vers la page d'accueil")
    page.goto(f"{OKOFEN_URL}/", wait_until="domcontentloaded")
    print("[TRACE] [run] Attente de networkidle sur la page d'accueil")
    page.wait_for_load_state("networkidle")

    # Lien "Chf1 Chauffage" avec timeout étendu
    print("[TRACE] [run] Recherche et clic sur le lien 'Chf1 Chauffage'")
    chf_link = page.get_by_role("link", name="Chf1 Chauffage")
    expect(chf_link).to_be_visible(timeout=30000)
    chf_link.click()

    # Attendre la page mode chauffage
    print("[TRACE] [run] Attente de la page de configuration de circuit chauffage")
    expect(page.get_by_text("Nom du circuitChauffage")).to_be_visible(timeout=30000)

    print("[TRACE] [run] APPEL à set_mode")
    changed, status_before, status_after = set_mode(page, target_mode)

    # Valider uniquement si on a vraiment demandé un changement
    if changed:
        print("[TRACE] [run] Validation changement de mode (clic sur OK)")
        expect(page.get_by_role("button", name="OK")).to_be_visible(timeout=30000)
        page.get_by_role("button", name="OK").click()
    else:
        print("[TRACE] [run] Aucun changement de mode demandé, pas de clic sur OK")

    # Retour éventuel à Home si dispo
    try:
        print("[TRACE] [run] Vérification du lien Home et retour éventuel")
        home_link = page.get_by_role("link", name="Home")
        if home_link.count() > 0:
            home_link.click()
            print("[TRACE] [run] Retour Home effectué")
    except Exception as e:
        print(f"[DEBUG] [run] Impossible de cliquer sur Home : {e}")

    print("[TRACE] [run] Fermeture du contexte et du navigateur")
    context.close()
    browser.close()

    return status_before, status_after, changed


if __name__ == "__main__":
    start = time.time()
    mode = "off"
    ok = False
    error_msg = ""
    status_before = "unknown"
    status_after = "unknown"
    changed = None

    print("[TRACE] [main] DEBUT main, parsing des arguments éventuels")
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("off", "arrete", "arrêt", "eteindre", "éteindre", "stop", "0"):
            mode = "off"
        elif arg in ("on", "allume", "allumer", "auto", "start", "1"):
            mode = "on"
        else:
            print("Usage : python Okofen_Playwright.py [on|off]")
            sys.exit(1)

    try:
        print(f"[TRACE] [main] Lancement de run() avec mode={mode}")
        with sync_playwright() as playwright:
            status_before, status_after, changed = run(playwright, mode)
        ok = True
    except Exception as e:
        ok = False
        error_msg = str(e)
        print(f"[ERROR] [main] Exception: {e}")

    duration_ms = int((time.time() - start) * 1000)

    summary = {
        "ok": ok,
        "action": mode,
        "status_before": status_before,
        "status_after": status_after,
        "changed": changed,
        "duration_ms": duration_ms,
    }

    if not ok:
        summary["error"] = error_msg
        summary["message"] = "Une erreur est survenue pendant le pilotage de la chaudière."
    else:
        if changed:
            if mode == "on":
                summary["message"] = "Chaudière allumée avec succès."
            else:
                summary["message"] = "Chaudière arrêtée avec succès."
        else:
            if mode == "on":
                summary["message"] = "La chaudière était déjà allumée."
            else:
                summary["message"] = "La chaudière était déjà à l'arrêt."

    # Ligne spéciale pour l'API HTTP (app.py)
    print("OKOFEN_SUMMARY:" + json.dumps(summary, ensure_ascii=False))

    sys.exit(0 if ok else 1)
