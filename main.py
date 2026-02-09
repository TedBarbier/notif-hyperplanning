import os
import json
import time
import requests
import logging
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9 if needed, though requirements check should ensure it works
    from backports.zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration du logging avec Timezone
LOG_TIMEZONE = os.getenv("LOG_TIMEZONE", "Europe/Paris")

def timetz(*args):
    return datetime.now(ZoneInfo(LOG_TIMEZONE)).timetuple()

logging.Formatter.converter = timetz

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

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
                logging.info("Création du fichier auth_state.json à partir de la variable d'environnement...")
                try:
                    with open(AUTH_FILE, "w", encoding="utf-8") as f:
                        f.write(auth_env)
                except Exception as e:
                    logging.error(f"Erreur lors de l'écriture du fichier auth : {e}")
            else:
                logging.warning("Attention : Pas de fichier auth_state.json ni de variable AUTH_STATE_JSON.")

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
            logging.error(f"Erreur sauvegarde historique: {e}")

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
            logging.error(f"Erreur calcul couleur: {e}")
            color = 3066993

        embed = {
            "title": "Nouvelle Note Détectée ! 🎓",
            "color": color,
            "fields": [
                {"name": "Matière", "value": grade_info['subject'], "inline": False},
                {"name": "Note", "value": f"**{grade_info['grade']}**", "inline": True},
                {"name": "Moyenne Promo", "value": grade_info.get('class_avg', 'N/A'), "inline": True},
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
            logging.info(f"Notification envoyée pour {grade_info['subject']}")
        except Exception as e:
            logging.error(f"Erreur lors de l'envoi Discord : {e}")

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
        # On ne bloque plus si le fichier n'existe pas, car on a l'auto-login.

        with sync_playwright() as p:
            logging.info(f"Lancement navigateur (Headless: {HEADLESS_MODE})...")
            browser = p.chromium.launch(headless=HEADLESS_MODE)
            try:
                # Force une résolution Desktop pour éviter le menu mobile
                if os.path.exists(AUTH_FILE):
                    logging.info(f"Chargement de la session depuis {AUTH_FILE}")
                    context = browser.new_context(storage_state=AUTH_FILE, viewport={'width': 1920, 'height': 1080})
                else:
                    logging.info("Pas de session existante. Démarrage d'une nouvelle session.")
                    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
            except Exception as e:
                msg = f"Erreur chargement session: {e}"
                logging.error(msg)
                self.send_error_notification(msg)
                browser.close()
                return

            page = context.new_page()
            
            logging.info("Connexion à Hyperplanning...")
            try:
                page.goto(HP_URL, timeout=60000)
                

                
                # --- AUTO-LOGIN LOGIC ---
                if "login" in page.url or "cas" in page.url or page.locator("input[type='password']").count() > 0:
                    logging.info("Session expirée. Tentative de reconnexion automatique au CAS...")
                    
                    username = os.getenv("HP_USERNAME")
                    password = os.getenv("HP_PASSWORD")
                    
                    if not username or not password:
                        raise Exception("HP_USERNAME ou HP_PASSWORD manquant pour la reconnexion automatique.")
                    
                    try:
                        logging.info("Remplissage du formulaire...")
                        page.fill("input[name='username'], input[name='user'], #username", username)
                        page.fill("input[name='password'], input[name='pass'], #password", password)
                        page.click("input[type='submit'], button[type='submit'], .btn-submit")
                        
                        logging.info("Validation du formulaire...")
                        try:
                            # Wait for navigation
                            page.wait_for_load_state('domcontentloaded', timeout=10000)
                            time.sleep(3) 
                        except:
                            pass
                    except Exception as e_login:
                        raise Exception(f"Echec du login CAS: {e_login}")

                    if "login" in page.url or "cas" in page.url:
                         raise Exception("La connexion semble avoir échoué (toujours sur la page de login).")
                    
                    logging.info("Reconnexion réussie ! Mise à jour de la session.")
                    context.storage_state(path=AUTH_FILE)
                # ------------------------

                # --- NAVIGATION & PARSING ---
                logging.info("Navigation vers 'Résultats'...")
                try:
                    # Clic sur l'onglet Résultats
                    page.get_by_text("Résultats").first.click()
                    page.wait_for_load_state('domcontentloaded', timeout=30000)
                    time.sleep(2) # Petite pause pour le rendu JS
                    
                    # --- Multi-Semester Loop ---
                    logging.info("Début du scan multi-périodes...")
                    
                    # On ouvre le dropdown pour compter les options
                    # (Il faut le faire au moins une fois pour charger le DOM si c'est du lazy loading, 
                    # mais surtout pour avoir le count)
                    try:
                        combobox = page.get_by_role("combobox", name="Sélectionnez une période")
                        if combobox.count() > 0:
                            combobox.click()
                            time.sleep(1)
                            page.wait_for_selector(".as-li", state="attached", timeout=5000)
                    except:
                        pass # Peut-être déjà ouvert ou autre structure

                    # On récupère le nombre d'options
                    options_count = page.locator(".as-li").count()
                    logging.info(f"{options_count} périodes trouvées.")
                    
                    parsed_grades = []
                    
                    for i in range(options_count):
                        try:
                            # Re-sélection du combobox à chaque itération car le DOM peut changer
                            combobox = page.get_by_role("combobox", name="Sélectionnez une période")
                            if combobox.count() > 0:
                                # On clique pour ouvrir (si fermé)
                                # L'état est difficile à traquer, donc on clique. 
                                # Si ça ferme, on ré-ouvrira. Mais locator(".as-li") doit être visible.
                                # Le plus simple est de cliquer, check si options visibles.
                                combobox.click()
                                time.sleep(1)
                            
                            # On clique sur l'option i
                            option = page.locator(".as-li").nth(i)
                            opt_text = option.inner_text().strip().replace('\n', ' ')
                            logging.info(f"Scan de la période [{i+1}/{options_count}] : {opt_text}")
                            
                            option.click()
                            time.sleep(3) # Attente chargement
                            page.wait_for_load_state('domcontentloaded')
                            
                            # --- Parsing des notes de cette période ---
                            current_subject = "Inconnu"
                            rows = page.locator("div[role='treeitem']").all()
                            
                            for row in rows:
                                try:
                                    level = row.get_attribute("aria-level")
                                    if level == "1":
                                        subject_el = row.locator(".titre-principal")
                                        if subject_el.count() > 0:
                                            current_subject = subject_el.inner_text().strip()
                                            
                                    elif level == "2":
                                        date_el = row.locator(".date-contain")
                                        grade_el = row.locator(".zone-complementaire")
                                        
                                        if date_el.count() > 0 and grade_el.count() > 0:
                                            date_text = date_el.inner_text().strip()
                                            
                                            aria_label = grade_el.get_attribute("aria-label") or ""
                                            if "Note étudiant :" in aria_label:
                                                grade_text = aria_label.split("Note étudiant :")[1].strip()
                                            else:
                                                grade_text = grade_el.inner_text().strip().replace('\n', '')
                                            
                                            class_avg = "N/A"
                                            try:
                                                infos_el = row.locator(".infos-supp .ie-sous-titre")
                                                for k in range(infos_el.count()):
                                                    txt = infos_el.nth(k).inner_text()
                                                    if "Moyenne promotion" in txt:
                                                        class_avg = txt.split(":")[1].strip() if ":" in txt else txt.strip()
                                                        break
                                            except:
                                                pass
    
                                            grade_obj = {
                                                "subject": current_subject,
                                                "date": date_text,
                                                "grade": grade_text,
                                                "class_avg": class_avg
                                            }
                                            parsed_grades.append(grade_obj)
                                except:
                                    pass
                        except Exception as e_loop:
                             logging.error(f"Erreur lors du scan de l'option {i}: {e_loop}")
                    
                    logging.info(f"Extraction terminée : {len(parsed_grades)} notes trouvées.")
                    
                    # Traitement des nouvelles notes
                    new_grades_count = 0
                    self.seen_grades = self.load_history()

                    for grade in reversed(parsed_grades):
                        is_known = False
                        for known in self.seen_grades:
                            # Comparaison stricte
                            if known['subject'].strip() == grade['subject'].strip() and \
                               known['date'].strip() == grade['date'].strip() and \
                               known['grade'].strip() == grade['grade'].strip():
                                is_known = True
                                break
                        
                        if not is_known:
                            logging.info(f"Nouvelle note détectée : {grade['subject']} -> {grade['grade']}")
                            self.send_discord_notification(grade)
                            self.seen_grades.append(grade)
                            new_grades_count += 1
                    
                    if new_grades_count > 0:
                        self.save_history()
                        logging.info(f"{new_grades_count} nouvelles notes enregistrées.")
                    else:
                        logging.info("Aucune nouvelle note à signaler.")
                        
                except Exception as e_nav:
                    logging.error(f"Erreur lors de la navigation/parsing : {e_nav}")
                    # On notifie quand même pour débugger au début
                    # self.send_error_notification(f"Erreur parsing: {e_nav}")

            except Exception as e:
                msg = f"Erreur critique navigation: {e}"
                logging.error(msg)
                self.send_error_notification(msg)
            finally:
                browser.close()

if __name__ == "__main__":
    if not HP_URL or not DISCORD_WEBHOOK_URL:
        logging.error("ERREUR: HP_URL ou DISCORD_WEBHOOK_URL manquant.")
    else:
        bot = HyperplanningBot()
        logging.info(f"Démarrage du bot RPi (Intervalle: {CHECK_INTERVAL_SECONDS}s)")
        
        while True:
            try:
                bot.run()
            except Exception as e:
                msg = f"Erreur critique lors de l'exécution : {e}"
                logging.error(msg)
                try:
                    bot.send_error_notification(msg)
                except:
                    pass
            
            logging.info(f"Mise en veille pour {CHECK_INTERVAL_SECONDS} secondes...")
            time.sleep(CHECK_INTERVAL_SECONDS)
