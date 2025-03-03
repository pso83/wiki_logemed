from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, abort, \
    send_from_directory, flash, Response
import MySQLdb
import uuid
import os
import re
import markdown
import logging
from ftplib import FTP
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from markupsafe import Markup
import MySQLdb.cursors

# backend
app = Flask(__name__)

# ✅ Activer le logging pour voir les routes disponibles
logging.basicConfig(level=logging.DEBUG)

# ✅ Afficher toutes les routes enregistrées dans Flask
for rule in app.url_map.iter_rules():
    logging.debug(f"Route disponible: {rule}")

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
        charset='utf8mb4',
        cursorclass = MySQLdb.cursors.DictCursor  # ✅ Correction ici
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


# ✅ Fonction améliorée pour reconnaître le code SQL et WinDev entre []
def convertir_markdown(texte):
    if texte:
        # ✅ Détection des blocs de code SQL et WinDev avec balises `[SQL]...[/SQL]` et `[WinDev]...[/WinDev]`
        texte = re.sub(r'\[SQL\](.*?)\[/SQL\]', r'<pre class="language-sql"><code>\1</code></pre>', texte, flags=re.DOTALL)
        texte = re.sub(r'\[WinDev\](.*?)\[/WinDev\]', r'<pre class="language-windev"><code>\1</code></pre>', texte, flags=re.DOTALL)

        # ✅ Détection des blocs de code génériques entre [ ]
        texte = re.sub(r'\[(.*?)\]', r'<pre class="language-generic"><code>\1</code></pre>', texte)

        # ✅ Application du Markdown pour le reste du contenu
        texte_html = markdown.markdown(texte, extensions=["extra", "nl2br", "sane_lists"])

        return Markup(texte_html)  # ✅ Markup permet d'afficher du HTML sécurisé dans Jinja
    return ""

# ✅ Ajout du filtre Jinja
app.jinja_env.filters['convertir_markdown'] = convertir_markdown

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

    # ✅ Incrémente le compteur de vues
    cursor.execute("UPDATE procedures SET vues = vues + 1 WHERE id = %s", (id,))
    conn.commit()

    cursor.execute("""
        SELECT p.id, p.titre, p.mots_cles, p.description, p.base_donnees, 
               p.protocole_resolution, p.protocole_verification, 
               p.acteur, p.verificateur, p.utilisateur, 
               COALESCE(p.pieces_jointes, '') AS pieces_jointes,
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

    if not procedure:
        abort(404)  # ✅ Retourner une erreur 404 si aucune procédure n'est trouvée

    # ✅ Accéder aux valeurs par les **clés du dictionnaire** au lieu d'indices numériques
    formatted_description = format_code_blocks(procedure["description"])
    formatted_resolution = format_code_blocks(procedure["protocole_resolution"])
    formatted_verification = format_code_blocks(procedure["protocole_verification"])

    return render_template(
        'view_procedure.html',
        procedure=procedure,
        formatted_description=formatted_description,
        formatted_resolution=formatted_resolution,
        formatted_verification=formatted_verification
    )

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    search_keywords = request.args.get('search_keywords', '').strip()
    search_application = request.args.get('search_application', '').strip()

    # ✅ Assurer une valeur par défaut
    procedures_a_valider = 0
    procedures_a_corriger = 0

    # ✅ Requête principale pour récupérer les procédures
    query = """
        SELECT 
            p.id, 
            p.titre, 
            p.description, 
            p.mots_cles, 
            p.reference_ticket, 
            (SELECT GROUP_CONCAT(DISTINCT a.nom ORDER BY a.id SEPARATOR ', ') 
             FROM procedure_applications pa 
             JOIN applications a ON pa.application_id = a.id 
             WHERE pa.procedure_id = p.id) AS applications,
            p.statut, 
            p.vues,  
            (SELECT COUNT(*) FROM votes v WHERE v.procedure_id = p.id AND v.vote_type = 'like') AS likes,
            (SELECT COUNT(*) FROM votes v WHERE v.procedure_id = p.id AND v.vote_type = 'dislike') AS dislikes,
            (SELECT GROUP_CONCAT(DISTINCT a.couleur ORDER BY a.id SEPARATOR ', ') 
             FROM procedure_applications pa 
             JOIN applications a ON pa.application_id = a.id 
             WHERE pa.procedure_id = p.id) AS couleurs,
            p.utilisateur  
        FROM procedures p
        WHERE p.est_supprime = 0 OR p.est_supprime IS NULL
    """

    params = []

    # ✅ Recherche par mots-clés
    if search_keywords:
        keywords = [kw.strip() for kw in search_keywords.split("#") if kw.strip()]

        if search_keywords.startswith("#"):
            keyword_conditions = " OR ".join(["p.mots_cles LIKE %s" for _ in keywords])
            query += f" AND ({keyword_conditions})"
            params.extend([f"%{kw}%" for kw in keywords])
        else:
            keyword_conditions = " OR ".join([
                "p.titre LIKE %s",
                "p.description LIKE %s",
                "p.mots_cles LIKE %s",
                "p.reference_ticket LIKE %s"
            ])
            query += f" AND ({keyword_conditions})"
            params.extend([f"%{search_keywords}%" for _ in range(4)])

    # ✅ Filtrage par application
    if search_application:
        query += " AND p.id IN (SELECT pa2.procedure_id FROM procedure_applications pa2 WHERE pa2.application_id = %s)"
        params.append(search_application)

    # ✅ Ajouter le GROUP BY pour éviter les erreurs SQL
    query += " GROUP BY p.id"

    try:
        cursor.execute(query, params)
        procedures = cursor.fetchall()
    except Exception as e:
        print(f"🚨 ERREUR SQL : {e}")
        procedures = []

    # ✅ Conversion en dictionnaire pour éviter les erreurs de clé
    procedures_dict = [dict(proc) for proc in procedures]

    # ✅ Récupérer les applications
    cursor.execute("SELECT id, nom FROM applications")
    applications = cursor.fetchall()

    # ✅ Fermeture de la connexion
    cursor.close()
    conn.close()

    return render_template(
        'home.html',
        procedures=procedures_dict,
        applications=applications,
        search_keywords=search_keywords,
        search_application=search_application,
        procedures_a_valider=procedures_a_valider,
        procedures_a_corriger=procedures_a_corriger
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, est_admin, est_moderateur FROM utilisateurs WHERE utilisateur = %s AND password = %s",
                       (username, password))
        user = cursor.fetchone()  # ✅ Récupère l'utilisateur
        print("DEBUG - Résultat de la requête SQL :", user)
        cursor.close()
        conn.close()

        if user:  # ✅ Vérifie que user n'est pas None
            session['user_id'] = user['id']
            session['username'] = username
            session['est_admin'] = bool(user['est_admin'])
            session['est_moderateur'] = bool(user['est_moderateur'])

            next_page = request.args.get("next")
            return redirect(next_page if next_page else url_for('home'))
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect.", "danger")
            return render_template('login.html')
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

@app.route('/gestion_a_verifier')
def gestion_a_verifier():
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
    if 'user_id' not in session or not session.get("est_moderateur"):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, titre, description, statut FROM procedures WHERE statut = 'À valider'")
    procedures_a_valider = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('gestion_procedures_a_valider.html', procedures=procedures_a_valider)


@app.route('/like/<int:id>', methods=['POST'])
def like_procedure(id):
    if 'username' not in session:
        return redirect(url_for('login'))  # ✅ Rediriger si non connecté

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ✅ Vérifier si l'utilisateur a déjà voté
        cursor.execute(
            "SELECT * FROM votes WHERE procedure_id = %s AND utilisateur = %s",
            (id, session['username'])
        )
        existing_vote = cursor.fetchone()

        if existing_vote:
            print(f"⚠️ DEBUG - Vote déjà existant pour ID: {id} par {session['username']}")
        else:
            # ✅ Ajouter le vote si pas encore voté
            cursor.execute(
                "INSERT INTO votes (procedure_id, vote_type, utilisateur) VALUES (%s, 'like', %s)",
                (id, session['username'])
            )
            conn.commit()
            print(f"✅ DEBUG - Like ajouté pour ID: {id} par {session['username']}")

    except MySQLdb.IntegrityError as e:
        print(f"❌ ERREUR SQL - {e}")  # ✅ Debug si erreur
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('home'))


@app.route('/dislike/<int:id>', methods=['POST'])
def dislike_procedure(id):
    if 'username' not in session:
        return redirect(url_for('login'))  # ✅ Rediriger si non connecté

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ✅ Vérifier si l'utilisateur a déjà voté
        cursor.execute(
            "SELECT * FROM votes WHERE procedure_id = %s AND utilisateur = %s",
            (id, session['username'])
        )
        existing_vote = cursor.fetchone()

        if existing_vote:
            print(f"⚠️ DEBUG - Vote déjà existant pour ID: {id} par {session['username']}")
        else:
            # ✅ Ajouter le vote si pas encore voté
            cursor.execute(
                "INSERT INTO votes (procedure_id, vote_type, utilisateur) VALUES (%s, 'dislike', %s)",
                (id, session['username'])
            )
            conn.commit()
            print(f"✅ DEBUG - Dislike ajouté pour ID: {id} par {session['username']}")

    except MySQLdb.IntegrityError as e:
        print(f"❌ ERREUR SQL - {e}")  # ✅ Debug si erreur
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('home'))

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/vote/<int:id>/<string:vote_type>', methods=['POST'])
def vote_procedure(id, vote_type):
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Utilisateur non connecté'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Vérifier si l'utilisateur a déjà voté
        cursor.execute(
            "SELECT vote_type FROM votes WHERE procedure_id = %s AND utilisateur = %s",
            (id, session['username'])
        )
        existing_vote = cursor.fetchone()

        if existing_vote:
            existing_vote_type = existing_vote['vote_type']
            if existing_vote_type == vote_type:
                # ✅ Si l'utilisateur clique à nouveau sur le même vote → Supprimer le vote
                cursor.execute(
                    "DELETE FROM votes WHERE procedure_id = %s AND utilisateur = %s",
                    (id, session['username'])
                )
                conn.commit()
                message = f"✅ Vote supprimé pour ID: {id} ({vote_type})"
                vote_status = None
            else:
                # ✅ Si l'utilisateur change de vote → Mettre à jour le vote
                cursor.execute(
                    "UPDATE votes SET vote_type = %s WHERE procedure_id = %s AND utilisateur = %s",
                    (vote_type, id, session['username'])
                )
                conn.commit()
                message = f"✅ Vote mis à jour pour ID: {id} ({vote_type})"
                vote_status = vote_type
        else:
            # ✅ Si l'utilisateur n'a jamais voté → Ajouter un vote
            cursor.execute(
                "INSERT INTO votes (procedure_id, vote_type, utilisateur) VALUES (%s, %s, %s)",
                (id, vote_type, session['username'])
            )
            conn.commit()
            message = f"✅ Vote ajouté pour ID: {id} ({vote_type})"
            vote_status = vote_type

        print(message)

        # ✅ Récupérer le nombre de likes/dislikes après l'opération
        cursor.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM votes WHERE procedure_id = %s AND vote_type = 'like') AS likes, "
            "(SELECT COUNT(*) FROM votes WHERE procedure_id = %s AND vote_type = 'dislike') AS dislikes",
            (id, id)
        )
        result = cursor.fetchone()

        return jsonify({'success': True, 'likes': result['likes'], 'dislikes': result['dislikes'], 'vote_status': vote_status})

    except MySQLdb.IntegrityError as e:
        print(f"❌ ERREUR SQL - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)