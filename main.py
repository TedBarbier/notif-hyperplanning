import os
import json
import time
import requests
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

HP_URL = os.getenv("HP_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
HISTORY_FILE = "grades_history.json"

class HyperplanningBot:
    def __init__(self):
        self.seen_grades = self.load_history()
        self.ensure_auth_file()

    def ensure_auth_file(self):
        auth_path = "auth_state.json"
        auth_env = os.getenv("AUTH_STATE_JSON")
        
        if not os.path.exists(auth_path):
            if auth_env:
                print("Création du fichier auth_state.json à partir de la variable d'environnement...")
                try:
                    with open(auth_path, "w", encoding="utf-8") as f:
                        f.write(auth_env)
                except Exception as e:
                    print(f"Erreur lors de l'écriture du fichier auth : {e}")
            else:
                print("Attention : Pas de fichier auth_state.json ni de variable AUTH_STATE_JSON.")

    # ... (rest of class) ...

    def run(self):
        auth_path = "auth_state.json"
        
        if not os.path.exists(auth_path):
            print("Erreur: Fichier d'authentification introuvable.")
            print("Configurez la variable d'environnement AUTH_STATE_JSON dans Portainer avec le contenu de votre fichier auth_state.json local.")
            return

        with sync_playwright() as p:
            # ... (continuation)

# ... (Main block) ...
if __name__ == "__main__":
    bot = HyperplanningBot()
    print(f"Démarrage du bot RPi (Intervalle: {CHECK_INTERVAL_SECONDS}s)")
    
    while True:
        try:
            bot.run()
        except Exception as e:
            print(f"Erreur critique lors de l'exécution : {e}")
        
        print(f"Mise en veille pour {CHECK_INTERVAL_SECONDS} secondes...")
        time.sleep(CHECK_INTERVAL_SECONDS)

    def save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.seen_grades, f, ensure_ascii=False, indent=4)

    def send_discord_notification(self, grade_info):
        # Couleur : Vert si >= 10, Orange entre 8 et 10, Rouge < 8
        try:
            # Gestion des notes sur autre chose que 20 (ex: 4,50/5)
            grade_str = grade_info['grade'].replace(',', '.')
            if '/' in grade_str:
                numerator, denominator = grade_str.split('/')
                # On ramène la note sur 20 pour la couleur
                val = (float(numerator) / float(denominator)) * 20
            else:
                val = float(grade_str)
            
            # Codes couleurs Discord (décimal)
            GREEN = 3066993   # 0x2ECC71
            ORANGE = 15105570 # 0xE67E22
            RED = 15158332    # 0xE74C3C
            
            if val >= 10:
                color = GREEN
            elif val >= 8:
                color = ORANGE
            else:
                color = RED
        except Exception as e:
            print(f"Erreur calcul couleur: {e}")
            color = 3066993 # Vert par défaut en cas d'erreur de parsing

        embed = {
            "title": "Nouvelle Note Détectée ! 🎓",
            "color": color,
            "fields": [
                {"name": "Matière", "value": grade_info['subject'], "inline": True},
                {"name": "Note", "value": grade_info['grade'], "inline": True},
                {"name": "Date", "value": grade_info['date'], "inline": True}
            ],
            "footer": {"text": "Hyperplanning Bot - INSA"}
        }
        data = {
            "username": "HyperPlanning Bot",
            "embeds": [embed]
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=data)
            print(f"Notification envoyée pour {grade_info['subject']}")
        except Exception as e:
            print(f"Erreur lors de l'envoi Discord : {e}")

    def run(self):
        auth_path = "auth_state.json"
        
        # Le fichier est censé être créé par __init__ si la variable d'env est présente
        if not os.path.exists(auth_path):
            print("Erreur: Fichier d'authentification introuvable.")
            print("Veuillez configurer la variable AUTH_STATE_JSON dans Portainer.")
            return

        with sync_playwright() as p:
            # Sur Raspberry Pi, il faut parfois forcer l'usage des exécutables installés par playwright
            browser = p.chromium.launch(headless=os.getenv("HEADLESS_MODE", "True").lower() == "true")
            try:
                context = browser.new_context(storage_state=auth_path)
            except Exception as e:
                print(f"Erreur chargement session: {e}.")
                browser.close()
                return

            page = context.new_page()
            
            print("Connexion à Hyperplanning...")
            page.goto(HP_URL)
            
            # Attendre que le widget des notes soit chargé
            try:
                # On attend spécifiquement l'objet "Dernières notes"
                page.wait_for_selector('section.notes', timeout=20000)
                print("Widget 'Dernières notes' détecté.")
            except:
                print("Timeout: Le widget 'Dernières notes' n'a pas été trouvé.")
            
            # Extraction des notes depuis le widget
            parsed_grades = []
            
            # On cherche tous les items de la liste dans le widget
            items = page.locator("section.notes ul.liste-clickable li").all()
            
            print(f"Extraction : {len(items)} notes trouvées dans le widget.")
            
            for item in items:
                try:
                    subject = item.locator("h3 span").inner_text().strip()
                    date = item.locator(".date").inner_text().strip()
                    
                    # La note
                    grade_locator = item.locator(".as-info.fixed")
                    grade_text = grade_locator.inner_text().strip()
                    grade_text = grade_text.replace('\n', '')
                    
                    grade_obj = {
                        "subject": subject,
                        "date": date,
                        "grade": grade_text
                    }
                    parsed_grades.append(grade_obj)
                    # print(f"   -> Trouvé : {subject} : {grade_text} ({date})")
                except Exception as e:
                    print(f"   -> Erreur lors du parsing d'une ligne : {e}")

            # Comparaison et Notification
            new_grades_count = 0
            
            # Rechargement explicite de l'historique pour être sûr (cas où le script tourne en boucle plus tard)
            self.seen_grades = self.load_history()

            for grade in reversed(parsed_grades):
                # Vérification stricte
                is_known = False
                for known in self.seen_grades:
                    # Comparaison propre en ignorant les espaces
                    if known['subject'].strip() == grade['subject'].strip() and \
                       known['date'].strip() == grade['date'].strip() and \
                       known['grade'].strip() == grade['grade'].strip():
                        is_known = True
                        break
                
                if not is_known:
                    print(f"Nouvelle note détectée ! {grade['subject']} ({grade['grade']})")
                    self.send_discord_notification(grade)
                    self.seen_grades.append(grade)
                    new_grades_count += 1
            
            if new_grades_count > 0:
                self.save_history()
                print(f"{new_grades_count} notifications envoyées.")
            else:
                print("Aucune nouvelle note.")

            time.sleep(2)
            browser.close()

# Configuration
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 3600)) # Par défaut 1h
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "True").lower() == "true"

class HyperplanningBot:
    # ... (rest of class remains same, just modifying run method start and main block) ...
    def run(self):
        auth_path = "auth_state.json"
        
        with sync_playwright() as p:
            # Mode headless configurable via variable d'environnement
            browser = p.chromium.launch(headless=HEADLESS_MODE)
            context = browser.new_context(storage_state=auth_path)
            # ...

if __name__ == "__main__":
    bot = HyperplanningBot()
    print(f"Démarrage du bot (Intervalle: {CHECK_INTERVAL_SECONDS}s, Headless: {HEADLESS_MODE})")
    
    while True:
        try:
            bot.run()
        except Exception as e:
            print(f"Erreur critique lors de l'exécution : {e}")
        
        print(f"Mise en veille pour {CHECK_INTERVAL_SECONDS} secondes...")
        time.sleep(CHECK_INTERVAL_SECONDS)
