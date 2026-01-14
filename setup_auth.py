import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

HP_URL = os.getenv("HP_URL")
AUTH_FILE = "auth_state.json"

def save_auth_state():
    if not HP_URL:
        print("Erreur : HP_URL n'est pas défini dans le fichier .env")
        return

    with sync_playwright() as p:
        # Lancer le navigateur avec une interface visible (headless=False)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"Ouverture de {HP_URL}...")
        page.goto(HP_URL)

        print("\n=== ACTION REQUISE ===")
        print("Veuillez vous connecter manuellement dans la fenêtre du navigateur qui vient de s'ouvrir.")
        print("Une fois connecté et arrivé sur la page d'accueil d'Hyperplanning, appuyez sur ENTRÉE ici pour sauvegarder la session.")
        input("Appuyez sur ENTRÉE une fois connecté >> ")

        # Sauvegarder l'état (cookies, localStorage, etc.)
        context.storage_state(path=AUTH_FILE)
        print(f"Session sauvegardée dans {AUTH_FILE} !")
        print("Vous n'aurez plus besoin de vous connecter manuellement pour les prochaines exécutions.")

        browser.close()

if __name__ == "__main__":
    save_auth_state()
