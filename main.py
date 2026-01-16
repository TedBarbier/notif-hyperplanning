import os
import json
import time
import requests
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Définition des chemins persistants
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True) # Créer le dossier data s'il n'existe pas

HP_URL = os.getenv("HP_URL")
HP_USERNAME = os.getenv("HP_USERNAME") # Ajout pour reconnexion auto
HP_PASSWORD = os.getenv("HP_PASSWORD") # Ajout pour reconnexion auto
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
HISTORY_FILE = os.path.join(DATA_DIR, "grades_history.json")
AUTH_FILE = os.path.join(DATA_DIR, "auth_state.json")
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 3600))
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "True").lower() == "true"

class HyperplanningBot:
    def __init__(self):
        self.ensure_auth_file()
        self.seen_grades = self.load_history()

    def ensure_auth_file(self):
        auth_env = os.getenv("AUTH_STATE_JSON")
        
        if not os.path.exists(AUTH_FILE):
            if auth_env:
                print("Création du fichier auth_state.json à partir de la variable d'environnement...")
                try:
                    with open(AUTH_FILE, "w", encoding="utf-8") as f:
                        f.write(auth_env)
                except Exception as e:
                    print(f"Erreur lors de l'écriture du fichier auth : {e}")
            else:
                print("Attention : Pas de fichier auth_state.json ni de variable AUTH_STATE_JSON.")

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.seen_grades, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Erreur sauvegarde historique: {e}")

    def send_discord_notification(self, grade_info):
        try:
            grade_str = grade_info['grade'].replace(',', '.')
            if '/' in grade_str:
                numerator, denominator = grade_str.split('/')
                val = (float(numerator) / float(denominator)) * 20
            else:
                val = float(grade_str)
            
            GREEN = 3066993
            ORANGE = 15105570
            RED = 15158332
            
            if val >= 10:
                color = GREEN
            elif val >= 8:
                color = ORANGE
            else:
                color = RED
        except Exception as e:
            print(f"Erreur calcul couleur: {e}")
            color = 3066993

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

    def send_error_notification(self, error_message):
        embed = {
            "title": "Erreur Critique - Bot Hyperplanning ⚠️",
            "description": f"Une erreur est survenue lors de l'exécution :\n```{error_message}```",
            "color": 15158332, # Rouge
            "footer": {"text": "Veuillez vérifier les logs sur Portainer"}
        }
        data = {
            "username": "HyperPlanning Bot (Erreur)",
            "embeds": [embed]
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=data)
        except:
            pass

    def run(self):
        if not os.path.exists(AUTH_FILE):
            msg = "Erreur: Fichier d'authentification introuvable. Configurez AUTH_STATE_JSON."
            print(msg)
            self.send_error_notification(msg)
            return

        with sync_playwright() as p:
            print(f"Lancement navigateur (Headless: {HEADLESS_MODE})...")
            browser = p.chromium.launch(headless=HEADLESS_MODE)
            try:
                context = browser.new_context(storage_state=AUTH_FILE)
            except Exception as e:
                msg = f"Erreur chargement session: {e}"
                print(msg)
                self.send_error_notification(msg)
                browser.close()
                return

            page = context.new_page()
            
            print("Connexion à Hyperplanning...")
            print("Connexion à Hyperplanning...")
            try:
                page.goto(HP_URL, timeout=60000)
                
                # Vérification si on est redirigé vers le CAS (page de login)
                # On regarde si on n'est PAS sur l'URL d'Hyperplanning ou si un formulaire de login est présent
                if "login" in page.url or "cas" in page.url or page.locator("input[type='password']").count() > 0:
                    print("Session expirée. Tentative de reconnexion automatique au CAS...")
                    
                    username = os.getenv("HP_USERNAME")
                    password = os.getenv("HP_PASSWORD")
                    
                    if not username or not password:
                        raise Exception("HP_USERNAME ou HP_PASSWORD manquant pour la reconnexion automatique.")
                    
                    # Tentative de remplissage du formulaire CAS standard
                    # Sélecteurs génériques souvent utilisés par les CAS
                    try:
                        print("Remplissage du formulaire...")
                        page.fill("input[name='username'], input[name='user'], #username", username)
                        page.fill("input[name='password'], input[name='pass'], #password", password)
                        
                        # Click sur le bouton de soumission (souvent type='submit' ou name='submit')
                        page.click("input[type='submit'], button[type='submit'], .btn-submit")
                        
                        print("Validation du formulaire...")
                        page.wait_for_load_state('networkidle')
                    except Exception as e_login:
                         # Si on n'arrive pas à se loguer, on capture le HTML pour debug
                        raise Exception(f"Echec du remplissage du login CAS: {e_login}")

                    # Vérification post-login
                    if "login" in page.url or "cas" in page.url:
                         raise Exception("La connexion semble avoir échoué (toujours sur la page de login). Vérifiez vos identifiants.")
                    
                    print("Reconnexion réussie ! Mise à jour de la session.")
                    context.storage_state(path=AUTH_FILE)

                try:
                    page.wait_for_selector('section.notes', timeout=30000)
                    print("Widget 'Dernières notes' détecté.")
                except:
                    print("Timeout: Widget non trouvé.")
                
                parsed_grades = []
                # ... (rest of logic) ...
                try:
                    items = page.locator("section.notes ul.liste-clickable li").all()
                except:
                    items = []
                
                print(f"Extraction : {len(items)} notes trouvées.")
                
                for item in items:
                    try:
                        subject = item.locator("h3 span").inner_text().strip()
                        date = item.locator(".date").inner_text().strip()
                        grade_locator = item.locator(".as-info.fixed")
                        grade_text = grade_locator.inner_text().strip().replace('\n', '')
                        
                        grade_obj = {
                            "subject": subject,
                            "date": date,
                            "grade": grade_text
                        }
                        parsed_grades.append(grade_obj)
                    except Exception as e:
                        pass # Ignorer erreurs de parsing individuelles

                new_grades_count = 0
                self.seen_grades = self.load_history()

                for grade in reversed(parsed_grades):
                    is_known = False
                    for known in self.seen_grades:
                        if known['subject'].strip() == grade['subject'].strip() and \
                           known['date'].strip() == grade['date'].strip() and \
                           known['grade'].strip() == grade['grade'].strip():
                            is_known = True
                            break
                    
                    if not is_known:
                        print(f"Nouvelle note : {grade['subject']} ({grade['grade']})")
                        self.send_discord_notification(grade)
                        self.seen_grades.append(grade)
                        new_grades_count += 1
                
                if new_grades_count > 0:
                    self.save_history()
                    print(f"{new_grades_count} notifications envoyées.")
                else:
                    print("Aucune nouvelle note.")

            except Exception as e:
                msg = f"Erreur pendant la navigation: {e}"
                print(msg)
                self.send_error_notification(msg)
            finally:
                browser.close()

if __name__ == "__main__":
    if not HP_URL or not DISCORD_WEBHOOK_URL:
        print("ERREUR: HP_URL ou DISCORD_WEBHOOK_URL manquant.")
    else:
        bot = HyperplanningBot()
        print(f"Démarrage du bot RPi (Intervalle: {CHECK_INTERVAL_SECONDS}s)")
        
        while True:
            try:
                bot.run()
            except Exception as e:
                msg = f"Erreur critique lors de l'exécution : {e}"
                print(msg)
                try:
                    bot.send_error_notification(msg)
                except:
                    pass
            
            print(f"Mise en veille pour {CHECK_INTERVAL_SECONDS} secondes...")
            time.sleep(CHECK_INTERVAL_SECONDS)
