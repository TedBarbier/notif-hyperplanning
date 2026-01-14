# Utiliser l'image officielle Playwright qui contient déjà les navigateurs et dépendances système
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

# Copier les requirements et installer les dépendances Python supplémentaires
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Définir les variables d'environnement par défaut
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV HEADLESS_MODE=True

# Commande de démarrage
CMD ["python", "main.py"]
