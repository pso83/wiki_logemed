# Utilisation de l'image officielle Python
FROM python:3.11-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Copier les fichiers du projet dans le conteneur
COPY . .

# Installer les dépendances nécessaires
RUN pip install --no-cache-dir -r requirements.txt

# Exposer le port 8080 (Render utilise ce port par défaut)
EXPOSE 8080

# Définir la commande pour exécuter l'application Flask
CMD ["python", "Wiki.py"]
