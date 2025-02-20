from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, abort, send_from_directory, flash
import MySQLdb
import uuid
import os
import re
import markdown
import logging
from ftplib import FTP
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

# backend
app = Flask(__name__)

# Configuration du dossier des images
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ✅ Vérifie que l'extension du fichier est autorisée
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app.secret_key = 'your_secret_key'  # Nécessaire pour gérer les sessions

# Configuration de la base de données
DB_HOST = '194.164.60.164'
DB_USER = 'devlog'
DB_PASSWORD = '123456Sou_log'
DB_NAME = 'wiki_db'

# Configuration FTP
FTP_HOST = '194.164.60.164'
FTP_USER = 'devlog'
FTP_PASSWORD = 'xdI8dUqg'
FTP_UPLOAD_DIR = '/home/devlog/FichiersWiki/'

# Fonction pour obtenir une connexion MySQL
def get_db_connection():
    return MySQLdb.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PASSWORD,
        db=DB_NAME,
        charset='utf8mb4'
    )

# Fonction pour formater les blocs de code
def format_code_blocks(text):
    return re.sub(r'\[(.*?)\]', r'<pre><code class="sql">\1</code></pre>', text, flags=re.DOTALL)

# Fonction pour téléverser un fichier sur le serveur FTP
def upload_file_to_ftp(file, filename):
    with FTP(FTP_HOST) as ftp:
        ftp.login(FTP_USER, FTP_PASSWORD)
        ftp.cwd(FTP_UPLOAD_DIR)
        ftp.storbinary(f'STOR {filename}', file)

# Fonction pour télécharger un fichier depuis le serveur FTP
def download_file_from_ftp(filename):
    with FTP(FTP_HOST) as ftp:
        ftp.login(FTP_USER, FTP_PASSWORD)
        ftp.cwd(FTP_UPLOAD_DIR)
        with open(filename, 'wb') as f:
            ftp.retrbinary(f'RETR {filename}', f.write)
    return filename

def is_admin():
    return session.get("est_admin", False) == True

def is_moderateur():
    return session.get("est_moderateur", False) == True

@app.route('/preview/<path:filename>')
def preview_file(filename):
    try:
        local_filepath = download_file_from_ftp(filename)
        with open(local_filepath, 'rb') as f:
            file_content = f.read()
        return Response(file_content, mimetype='application/vnd.oasis.opendocument.text')
    except Exception as e:
        print(f"Erreur lors de l'affichage du fichier : {e}")
        abort(404)

@app.before_request
def update_procedures_status():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE procedures 
        SET statut = 'À vérifier' 
        WHERE statut = 'Validée' AND date_expiration <= NOW()
    """)
    conn.commit()

    cursor.close()
    conn.close()

import re
import markdown

# ✅ Fonction pour convertir les blocs de code [texte] en <pre><code>texte</code></pre>
def format_code_blocks(text):
    if text:
        text = re.sub(r'\[(.*?)\]', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
        return markdown.markdown(text)
    return ""

@app.route('/view/<int:id>')
def view_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Récupérer toutes les informations de la procédure
    cursor.execute("""
        SELECT p.id, p.titre, p.mots_cles, p.description, p.base_donnees, 
               p.protocole_resolution, p.protocole_verification, 
               p.acteur, p.verificateur, p.utilisateur, COALESCE(p.pieces_jointes, '') AS pieces_jointes,
               GROUP_CONCAT(a.nom SEPARATOR ', ') AS applications,
               GROUP_CONCAT(a.couleur SEPARATOR ', ') AS couleurs
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        WHERE p.id = %s
        GROUP BY p.id
    """, (id,))
    procedure = cursor.fetchone()

    cursor.close()
    conn.close()

    # ✅ Appliquer la conversion Markdown et la mise en forme des blocs de code
    formatted_description = format_code_blocks(procedure[3])
    formatted_resolution = format_code_blocks(procedure[5])
    formatted_verification = format_code_blocks(procedure[6])

    return render_template('view_procedure.html', procedure=procedure,
                           formatted_description=formatted_description,
                           formatted_resolution=formatted_resolution,
                           formatted_verification=formatted_verification)


@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    search_keywords = request.args.get('search_keywords', '').strip()
    search_application = request.args.get('search_application', '').strip()

    query = """
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, 
               GROUP_CONCAT(a.nom SEPARATOR ', ') AS applications, 
               p.statut, p.est_supprime, p.utilisateur,
               GROUP_CONCAT(a.couleur SEPARATOR ', ') AS couleurs  
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        WHERE (p.est_supprime = 0 OR p.est_supprime IS NULL)
    """

    params = []

    # ✅ Vérification du type de recherche (avec "#" uniquement sur mots-clés, sans "#" sur tous les champs)
    if search_keywords:
        keywords = [kw.strip() for kw in search_keywords.split("#") if kw.strip()]

        if search_keywords.startswith("#"):  # ✅ Recherche uniquement sur "mots_cles"
            keyword_conditions = " OR ".join(["p.mots_cles LIKE %s" for _ in keywords])
            query += f" AND ({keyword_conditions})"
            params.extend([f"%{kw}%" for kw in keywords])
        else:  # ✅ Recherche sur "titre", "description", "mots_cles" et "reference_ticket"
            keyword_conditions = " OR ".join([
                "p.titre LIKE %s",
                "p.description LIKE %s",
                "p.mots_cles LIKE %s",
                "p.reference_ticket LIKE %s"
            ])
            query += f" AND ({keyword_conditions})"
            params.extend([f"%{search_keywords}%" for _ in range(4)])  # ✅ Applique à tous les champs

    # ✅ Filtrage par application
    if search_application:
        query += " AND p.id IN (SELECT pa2.procedure_id FROM procedure_applications pa2 WHERE pa2.application_id = %s)"
        params.append(search_application)

    query += " GROUP BY p.id"

    cursor.execute(query, params)
    procedures = cursor.fetchall()

    cursor.execute("SELECT id, nom FROM applications")
    applications = cursor.fetchall()

    # ✅ Récupérer le nombre de procédures "À valider" pour les modérateurs
    cursor.execute("SELECT COUNT(*) FROM procedures WHERE statut = 'À valider'")
    procedures_a_valider = cursor.fetchone()[0]

    # ✅ Récupérer le nombre de procédures "Rejetées" pour l'utilisateur connecté
    cursor.execute("SELECT COUNT(*) FROM procedures WHERE statut = 'Rejetée' AND utilisateur = %s",
                   (session['username'],))
    procedures_a_corriger = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return render_template('home.html',
                           procedures=procedures,
                           applications=applications,
                           search_keywords=search_keywords,
                           search_application=search_application,
                           procedures_a_valider=procedures_a_valider,
                           procedures_a_corriger=procedures_a_corriger)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, est_admin, est_moderateur FROM utilisateurs WHERE utilisateur = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['username'] = username
            session['est_admin'] = bool(user[1])
            session['est_moderateur'] = bool(user[2])  # ✅ Stocke si l'utilisateur est modérateur

            next_page = request.args.get("next")
            return redirect(next_page if next_page else url_for('home'))
        else:
            return render_template('login.html', error="Nom d'utilisateur ou mot de passe incorrect.")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/delete/<int:id>', methods=['POST'])
def delete_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM procedures WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('home'))


import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Récupérer la procédure avec les bonnes colonnes
    cursor.execute("""
        SELECT id, titre, mots_cles, description, reference_ticket, base_donnees, 
               protocole_resolution, protocole_verification, 
               acteur, verificateur, utilisateur, pieces_jointes, statut
        FROM procedures WHERE id = %s
    """, (id,))
    procedure = cursor.fetchone()

    if request.method == 'POST':
        titre = request.form['titre']
        mots_cles = request.form['mots_cles']
        description = request.form['description']
        reference_ticket = request.form['reference_ticket']
        base_donnees = request.form['base_donnees']
        protocole_resolution = request.form['protocole_resolution']
        protocole_verification = request.form['protocole_verification']
        applications = request.form.get('application_id', '')

        # ✅ S'assurer que le statut est toujours défini et ne peut pas être NULL
        ancien_statut = procedure[11] if procedure[11] else "À valider"
        nouveau_statut = "À valider" if ancien_statut in ["Rejetée", "Validée", "À vérifier", None] else ancien_statut

        cursor.execute("""
            UPDATE procedures 
            SET titre=%s, mots_cles=%s, description=%s, reference_ticket=%s, base_donnees=%s, 
                protocole_resolution=%s, protocole_verification=%s, statut=%s
            WHERE id=%s
        """, (titre, mots_cles, description, reference_ticket, base_donnees, protocole_resolution, protocole_verification, nouveau_statut, id))

        # ✅ Vérification et insertion des applications sélectionnées
        cursor.execute("SELECT application_id FROM procedure_applications WHERE procedure_id = %s", (id,))
        current_applications = {str(row[0]) for row in cursor.fetchall()}  # Convertir en set

        if applications:
            applications_list = set(applications.split(","))  # Convertir en set pour éviter les doublons

            # ✅ Ajouter uniquement les nouvelles applications
            new_applications = applications_list - current_applications
            for app_id in new_applications:
                if app_id.strip():  # Vérifier que l’ID n'est pas vide
                    cursor.execute("INSERT INTO procedure_applications (procedure_id, application_id) VALUES (%s, %s)", (id, app_id.strip()))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('home'))

    cursor.execute("SELECT id, nom, couleur FROM applications")
    applications = cursor.fetchall()

    cursor.execute("""
        SELECT a.id, a.nom, a.couleur
        FROM procedure_applications pa
        JOIN applications a ON pa.application_id = a.id
        WHERE pa.procedure_id = %s
    """, (id,))
    applications_associees = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('edit_procedure.html',
                           procedure=procedure,
                           applications=applications,
                           applications_associees=applications_associees)

@app.route('/add', methods=['GET', 'POST'])
def add_procedure():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        mots_cles = request.form.get('mots_cles', '')
        titre = request.form.get('titre', '')
        description = request.form.get('description', '')
        base_donnees = request.form.get('base_donnees', '')
        utilisateur = session.get('username')
        applications = request.form.get('application_id', '')  # ✅ Récupérer les applications sélectionnées

        # Insérer la procédure
        cursor.execute("""
            INSERT INTO procedures (mots_cles, titre, description, base_donnees, utilisateur) 
            VALUES (%s, %s, %s, %s, %s)
        """, (mots_cles, titre, description, base_donnees, utilisateur))
        procedure_id = cursor.lastrowid

        # Associer les applications sélectionnées à la procédure
        if applications:
            for app_id in applications.split(","):
                cursor.execute("INSERT INTO procedure_applications (procedure_id, application_id) VALUES (%s, %s)",
                               (procedure_id, app_id))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('home'))

    cursor.execute("SELECT * FROM applications")
    applications = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('add_procedure.html', applications=applications)

@app.route('/home/devlog/FichiersWiki/<path:filename>')
def download_file(filename):
    try:
        local_filepath = download_file_from_ftp(filename)
        return send_file(local_filepath, as_attachment=True)
    except Exception as e:
        print(f"Erreur lors du téléchargement du fichier : {e}")
        abort(404)

@app.route('/open_file/<path:file_path>')
def open_file(file_path):
    return redirect(f'ftp://{FTP_HOST}{FTP_UPLOAD_DIR}/{file_path}')


import uuid
from flask import request, url_for, jsonify
import os


@app.route('/upload_image', methods=['POST'])
def upload_image():
    print("🔄 Requête reçue pour l'upload d'image...")

    if 'upload' not in request.files:
        print("❌ Aucun fichier reçu !")
        return jsonify({'success': False, 'error': 'Aucun fichier envoyé'})

    file = request.files['upload']

    if file.filename == '':
        print("❌ Nom de fichier invalide !")
        return jsonify({'success': False, 'error': 'Nom de fichier invalide'})

    filename = str(uuid.uuid4()) + "_" + file.filename
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(file_path)

    file_url = url_for('serve_uploaded_images', filename=filename, _external=True)

    print(f"✅ Image enregistrée et servie à : {file_url}")

    return jsonify({"success": True, "url": file_url})


@app.route('/serve_image/<path:filename>')
def serve_uploaded_images(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/configuration', methods=['GET', 'POST'])
def configuration():
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.url))  # Redirige vers login et garde l'URL en mémoire

    if not is_admin():
        flash("❌ Accès refusé : Vous devez être administrateur pour accéder à cette page.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Récupérer applications, services et utilisateurs
    cursor.execute("SELECT id, nom, couleur FROM applications")
    applications = cursor.fetchall()

    cursor.execute("SELECT id, nom FROM services")
    services = cursor.fetchall()

    cursor.execute("""
        SELECT u.id, u.utilisateur, COALESCE(s.nom, 'Non défini') AS service, u.est_admin
        FROM utilisateurs u
        LEFT JOIN services s ON u.service_id = s.id
    """)
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('configuration.html', applications=applications, services=services, users=users)


@app.route('/update_application/<int:app_id>', methods=['POST'])
def update_application(app_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    new_color = request.form.get('new_color')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET couleur = %s WHERE id = %s", (new_color, app_id))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('configuration'))

@app.route('/add_user', methods=['POST'])
def add_user():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    username = request.form.get('username')
    password = request.form.get('password')
    service_id = request.form.get('service')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO utilisateurs (utilisateur, password, service_id) VALUES (%s, %s, %s)", (username, password, service_id if service_id else None))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('configuration'))

@app.route('/update_user_service/<int:user_id>', methods=['POST'])
def update_user_service(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    new_service_id = request.form.get('service')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE utilisateurs SET service_id = %s WHERE id = %s", (new_service_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('configuration'))


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM utilisateurs WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('configuration'))

@app.route('/add_service', methods=['POST'])
def add_service():
    if 'user_id' not in session or not is_admin():
        return redirect(url_for('login'))

    service_name = request.form.get('service_name')

    if service_name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO services (nom) VALUES (%s)", (service_name,))
        conn.commit()
        cursor.close()
        conn.close()

    return redirect(url_for('configuration'))


@app.route('/update_service/<int:service_id>', methods=['POST'])
def update_service(service_id):
    if 'user_id' not in session or not is_admin():
        return redirect(url_for('login'))

    new_name = request.form.get('new_name')

    if new_name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE services SET nom = %s WHERE id = %s", (new_name, service_id))
        conn.commit()
        cursor.close()
        conn.close()

    return redirect(url_for('configuration'))


@app.route('/delete_service/<int:service_id>', methods=['POST'])
def delete_service(service_id):
    if 'user_id' not in session or not is_admin():
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM services WHERE id = %s", (service_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('configuration'))

@app.route('/update_user_admin/<int:user_id>', methods=['POST'])
def update_user_admin(user_id):
    if 'user_id' not in session or not is_admin():
        return redirect(url_for('login'))

    new_status = request.form.get('is_admin') == "True"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE utilisateurs SET est_admin = %s WHERE id = %s", (new_status, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('configuration'))


@app.route('/validate_procedure/<int:id>', methods=['POST'])
def validate_procedure(id):
    if 'user_id' not in session or not session.get("est_moderateur"):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET statut = 'Validée' WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("La procédure a été validée avec succès.", "success")
    return redirect(url_for('home'))  # ✅ Retourner à `home` au lieu de `gestion_a_verifier`

@app.route('/soft_delete/<int:id>', methods=['POST'])
def soft_delete(id):
    if 'user_id' not in session or not is_admin():
        flash("❌ Accès refusé : Vous devez être administrateur pour supprimer une procédure.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET est_supprime = TRUE WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("🚮 Procédure supprimée (marquée comme rayée).", "info")
    return redirect(url_for('home'))

logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s - %(message)s')

# ✅ Activer les logs pour voir toutes les routes disponibles
for rule in app.url_map.iter_rules():
    logging.debug(f"Route disponible: {rule}")

import logging


@app.route('/gestion_a_verifier')
def gestion_a_verifier():
    logging.debug("DEBUG - La route /gestion_a_verifier a été appelée")  # ❌ Supprime flush=True

    if 'user_id' not in session or not session.get("est_moderateur"):
        logging.debug("Accès refusé : utilisateur non connecté ou non modérateur")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.id, 
               p.titre, 
               p.description, 
               p.mots_cles, 
               p.reference_ticket, 
               COALESCE(CAST(GROUP_CONCAT(a.nom SEPARATOR ', ') AS CHAR), '') AS applications, 
               COALESCE(CAST(GROUP_CONCAT(a.couleur SEPARATOR ', ') AS CHAR), '') AS couleurs, 
               p.statut, 
               p.utilisateur
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        WHERE p.statut IN ('À vérifier', 'À valider')
        GROUP BY p.id
    """)
    procedures = cursor.fetchall()

    logging.debug(f"DEBUG - Procedures récupérées ({len(procedures)} lignes): {procedures}")

    cursor.close()
    conn.close()

    return render_template('gestion_a_verifier.html', procedures=procedures)


@app.route('/reject_procedure/<int:id>', methods=['POST'])
def reject_procedure(id):
    if 'user_id' not in session or not session.get("est_moderateur"):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET statut = 'Rejetée' WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("La procédure a été rejetée.", "danger")
    return redirect(url_for('home'))  # ✅ Retourner à `home` au lieu de `gestion_a_verifier`

@app.route('/correct_procedure/<int:id>', methods=['POST'])
def correct_procedure(id):
    if 'user_id' not in session:
        flash("❌ Accès refusé.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Vérifier si l'utilisateur est bien l'auteur de la procédure
    cursor.execute("SELECT utilisateur FROM procedures WHERE id = %s", (id,))
    utilisateur = cursor.fetchone()

    if utilisateur and utilisateur[0] == session.get("username"):
        # ✅ Mettre la procédure à "À valider"
        cursor.execute("UPDATE procedures SET statut = 'À valider' WHERE id = %s", (id,))
        conn.commit()

    cursor.close()
    conn.close()

    flash("🔄 La procédure a été corrigée et est de nouveau en attente de validation.", "info")
    return redirect(url_for('home'))

@app.route('/deleted_procedures')
def deleted_procedures():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Récupérer uniquement les procédures supprimées
    cursor.execute("""
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, 
               GROUP_CONCAT(a.nom SEPARATOR ', ') AS applications, 
               p.statut, p.utilisateur
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        WHERE p.est_supprime = 1
        GROUP BY p.id
    """)
    procedures = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('deleted_procedures.html', procedures=procedures)

@app.route('/gestion_procedures_a_valider')
def gestion_procedures_a_valider():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Récupérer les procédures "À valider"
    cursor.execute("SELECT * FROM procedures WHERE statut = 'À valider'")
    procedures_a_valider = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('gestion_a_verifier.html', procedures=procedures_a_valider)

# ✅ Vérifier toutes les routes définies dans Flask
for rule in app.url_map.iter_rules():
    logging.debug(f"Route disponible : {rule}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)