from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, abort, \
    send_from_directory, flash, Response, render_template_string
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

logging.getLogger('MARKDOWN').setLevel(logging.WARNING)

# backend avec integration docker
app = Flask(__name__)

# ? Activer le logging pour voir les routes disponibles
# logging.basicConfig(level=logging.DEBUG)

# ? Afficher toutes les routes enregistrées dans Flask
for rule in app.url_map.iter_rules():
    logging.debug(f"Route disponible: {rule}")

# Configuration du dossier des images
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ? Vérifie que l'extension du fichier est autorisée
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app.secret_key = 'your_secret_key'  # Nécessaire pour gérer les sessions

# Configuration de la base de données
DB_HOST = '192.168.110.14'
DB_USER = 'asoulat'
DB_PASSWORD = '123@log'
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
        cursorclass = MySQLdb.cursors.DictCursor,  # ? Correction ici
        ssl={'ca': 'certif/DEV-14.pem'}
    )

# Fonction pour formater les blocs de code
def format_code_blocks(text):
    return re.sub(r'\[\s*([\s\S]*?)\s*\]', r'<pre><code>\1</code></pre>', text, flags=re.MULTILINE)


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

# ✅ convertisseur markdown sans suppression des <p>
def convertir_markdown(texte):
    if texte:
        # 🔸 Bloc SQL multi-lignes
        texte = re.sub(r'\[SQL\](.*?)\[/SQL\]', r'<pre class="language-sql"><code>\1</code></pre>', texte, flags=re.DOTALL)

        # 🔸 Bloc WinDev multi-lignes
        texte = re.sub(r'\[WinDev\](.*?)\[/WinDev\]', r'<pre class="language-windev"><code>\1</code></pre>', texte, flags=re.DOTALL)

        # 🔸 Bloc générique multi-lignes entre [ ]
        texte = re.sub(r'\[\s*([\s\S]*?)\s*\]', r'<pre class="language-generic"><code>\1</code></pre>', texte, flags=re.DOTALL)

        # 🔸 Markdown général (conserve les paragraphes)
        texte_html = markdown.markdown(texte, extensions=["extra", "nl2br", "sane_lists"])

        return Markup(texte_html)
    return ""

# ? Ajout du filtre Jinja
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

@app.route('/view/<int:id>')
def view_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Incrémentation du nombre de vues
    try:
        cursor.execute("UPDATE procedures SET vues = vues + 1 WHERE id = %s", (id,))
        conn.commit()
    except Exception as e:
        print(f"❌ ERREUR lors de l'incrémentation des vues : {e}")

    # ✅ Récupération des données de la procédure
    cursor.execute("""
        SELECT p.*, 
               COALESCE(GROUP_CONCAT(DISTINCT a.nom ORDER BY a.id SEPARATOR ', '), 'Aucune application') AS applications,
               COALESCE(GROUP_CONCAT(DISTINCT a.couleur ORDER BY a.id SEPARATOR ', '), '#5D5D5D') AS couleurs
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
        return "Procédure non trouvée", 404

    return render_template('view_procedure.html', procedure=procedure)

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🔸 Récupérer les procédures (avec recherche si présente)
    search_keywords = request.args.get('search_keywords', '').strip()
    search_application = request.args.get('search_application', '')
    search_statut = request.args.get('search_statut', '')
    order_by = request.args.get('order_by', 'desc')

    filters = []
    params = []

    if search_keywords:
        search_words = search_keywords.strip().split()
        motscles_keywords = [kw[1:].lower() for kw in search_words if kw.startswith("#")]
        global_keywords = [kw.lower() for kw in search_words if not kw.startswith("#")]

        if motscles_keywords:
            motscles_conditions = " OR ".join(["LOWER(p.mots_cles) LIKE %s" for _ in motscles_keywords])
            filters.append(f"({motscles_conditions})")
            params.extend([f"%{kw}%" for kw in motscles_keywords])

        if global_keywords:
            global_conditions = []
            for kw in global_keywords:
                global_conditions.append("(" + " OR ".join([
                    "LOWER(p.mots_cles) LIKE %s",
                    "LOWER(p.titre) LIKE %s",
                    "LOWER(p.description) LIKE %s",
                    "LOWER(p.protocole_resolution) LIKE %s",
                    "LOWER(p.protocole_verification) LIKE %s"
                ]) + ")")
                params.extend([f"%{kw}%"] * 5)
            filters.append(" AND ".join(global_conditions))

    if search_application:
        filters.append("a.id = %s")
        params.append(search_application)

    if search_statut:
        filters.append("p.statut = %s")
        params.append(search_statut)

    where_clause = "WHERE (p.est_supprime IS NULL OR p.est_supprime = 0)"
    if filters:
        where_clause += " AND " + " AND ".join(filters)

    query = f'''
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket,
               COALESCE(CAST(GROUP_CONCAT(a.nom SEPARATOR ', ') AS CHAR), '') AS applications,
               COALESCE(CAST(GROUP_CONCAT(a.couleur SEPARATOR ', ') AS CHAR), '') AS couleurs,
               p.statut, p.utilisateur, p.vues, p.verificateur,
               LENGTH(p.pieces_jointes) > 0 AS a_des_pj,
               (SELECT COUNT(*) FROM votes v WHERE v.procedure_id = p.id AND v.vote_type = 'like') AS likes,
               (SELECT COUNT(*) FROM votes v WHERE v.procedure_id = p.id AND v.vote_type = 'dislike') AS dislikes,
               CASE WHEN EXISTS (
                    SELECT 1 FROM motif_rejet WHERE procedure_id = p.id
               ) THEN 1 ELSE 0 END AS a_un_motif
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        {where_clause}
        GROUP BY p.id, p.titre, p.description, p.mots_cles, p.reference_ticket,
                 p.statut, p.utilisateur, p.vues, p.verificateur
        ORDER BY p.id {order_by.upper()}
    '''

    cursor.execute(query, tuple(params))
    procedures = cursor.fetchall()

    cursor.execute("SELECT id, nom FROM applications")
    applications = cursor.fetchall()

    # ? Appliquer la mise en forme aux descriptions et protocoles
    for procedure in procedures:
        cursor.execute("SELECT COUNT(*) as nb FROM motif_rejet WHERE procedure_id = %s", (procedure['id'],))
        motif_count = cursor.fetchone()
        procedure['a_un_motif'] = motif_count['nb'] > 0
        procedure['description'] = format_code_blocks(procedure['description']) if 'description' in procedure and \
                                                                                   procedure['description'] else ''
        procedure['protocole_resolution'] = format_code_blocks(
            procedure['protocole_resolution']) if 'protocole_resolution' in procedure and procedure[
            'protocole_resolution'] else ''
        procedure['protocole_verification'] = format_code_blocks(
            procedure['protocole_verification']) if 'protocole_verification' in procedure and procedure[
            'protocole_verification'] else ''

    cursor.execute("SELECT COUNT(*) as nb FROM procedures WHERE verificateur = %s AND statut = 'À vérifier'", (session['username'],))
    row = cursor.fetchone()
    procedures_a_verifier = int(row['nb']) if row and row['nb'] is not None else 0

    cursor.execute("SELECT COUNT(*) FROM procedures WHERE utilisateur = %s AND statut = 'Rejetée'", (session['username'],))
    procedures_a_corriger = cursor.fetchone()['COUNT(*)']

    cursor.execute(
        "SELECT COUNT(*) as nb FROM procedures WHERE statut = 'À valider' AND (est_supprime IS NULL OR est_supprime = 0)")
    row = cursor.fetchone()

    cursor.execute("SELECT procedure_id, vote_type FROM votes WHERE utilisateur = %s", (session['username'],))
    votes_utilisateur = cursor.fetchall()

    # On crée un dictionnaire : { procedure_id : 'like' ou 'dislike' }
    votes_user_map = {row['procedure_id']: row['vote_type'] for row in votes_utilisateur}

    procedures_a_valider = int(row['nb']) if row and row['nb'] is not None else 0

    conn.close()

    return render_template('home.html',
                           procedures=procedures,
                           search_keywords=search_keywords,
                           search_application=search_application,
                           search_statut=search_statut,
                           order_by=order_by,
                           applications=applications,
                           procedures_a_verifier=procedures_a_verifier,
                           procedures_a_corriger=procedures_a_corriger,
                           procedures_a_valider=procedures_a_valider,
                           votes_user_map=votes_user_map)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, est_admin, est_moderateur FROM utilisateurs WHERE utilisateur = %s AND password = %s",
                       (username, password))
        user = cursor.fetchone()  # ? Récupère l'utilisateur
        cursor.close()
        conn.close()

        if user:  # ? Vérifie que user n'est pas None
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

    # ✅ Récupérer la procédure
    cursor.execute("""
        SELECT id, titre, mots_cles, description, reference_ticket, base_donnees,
               protocole_resolution, protocole_verification,
               acteur, verificateur, utilisateur, pieces_jointes, statut
        FROM procedures WHERE id = %s
    """, (id,))
    procedure = cursor.fetchone()

    if not procedure:
        flash("❌ Procédure introuvable.", "danger")
        return redirect(url_for('home'))

    if request.method == 'POST':
        titre = request.form['titre']
        mots_cles = request.form['mots_cles']
        description = request.form['description']
        reference_ticket = request.form['reference_ticket']
        base_donnees = request.form['base_donnees']
        protocole_resolution = request.form['protocole_resolution']
        protocole_verification = request.form['protocole_verification']
        verificateur = request.form['verificateur']
        acteur = request.form['acteur']
        applications = request.form.getlist('application_id[]')

        ancien_statut = procedure['statut'] if procedure['statut'] else "À valider"
        nouveau_statut = "À valider" if ancien_statut in ["Rejetée", "Validée", "À vérifier", None] else ancien_statut

        # ✅ Gestion des nouvelles pièces jointes
        fichiers_nouveaux = []
        if 'pieces_jointes' in request.files:
            for file in request.files.getlist('pieces_jointes'):
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = str(uuid.uuid4()) + '_' + filename
                    upload_file_to_ftp(file.stream, unique_filename)
                    fichiers_nouveaux.append(unique_filename)

        ancien_pj = procedure['pieces_jointes'] if procedure['pieces_jointes'] else ''
        ancienne_liste = ancien_pj.split(";") if ancien_pj else []
        nouvelle_liste = ancienne_liste + fichiers_nouveaux
        pieces_jointes_str = ';'.join(filter(None, nouvelle_liste))

        cursor.execute("""
            UPDATE procedures
            SET titre=%s, mots_cles=%s, description=%s, reference_ticket=%s, base_donnees=%s,
                protocole_resolution=%s, protocole_verification=%s, verificateur=%s, acteur=%s,
                statut=%s, pieces_jointes=%s
            WHERE id=%s
        """, (
            titre, mots_cles, description, reference_ticket, base_donnees,
            protocole_resolution, protocole_verification, verificateur, acteur,
            nouveau_statut, pieces_jointes_str, id
        ))

        # ✅ Mise à jour des applications liées
        cursor.execute("DELETE FROM procedure_applications WHERE procedure_id = %s", (id,))
        for app_id in applications:
            if app_id.strip():
                cursor.execute("INSERT INTO procedure_applications (procedure_id, application_id) VALUES (%s, %s)", (id, app_id.strip()))

        conn.commit()
        cursor.close()
        conn.close()
        flash("✅ Procédure modifiée avec succès.", "success")
        return redirect(url_for('home'))

    # ✅ Charger les données pour affichage dans le formulaire
    cursor.execute("SELECT id, nom, couleur FROM applications")
    applications = cursor.fetchall()

    cursor.execute("""
        SELECT a.id, a.nom, a.couleur
        FROM procedure_applications pa
        JOIN applications a ON pa.application_id = a.id
        WHERE pa.procedure_id = %s
    """, (id,))
    applications_associees = cursor.fetchall()

    # ✅ Charger la liste des vérificateurs dynamiquement
    cursor.execute("""
        SELECT u.utilisateur FROM utilisateurs u
        JOIN services s ON u.service_id = s.id
        WHERE s.nom = 'direction' OR s.id = (SELECT service_id FROM utilisateurs WHERE id = %s)
    """, (session['user_id'],))
    verificateurs = cursor.fetchall()

    cursor.close()
    conn.close()

    couleurs_dict = {str(app['id']): app['couleur'] for app in applications}

    return render_template('edit_procedure.html',
                           procedure=procedure,
                           applications=applications,
                           applications_associees=applications_associees,
                           couleurs_dict=couleurs_dict,
                           verificateurs=verificateurs)

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
        protocole_resolution = request.form.get('protocole_resolution', '')
        protocole_verification = request.form.get('protocole_verification', '')
        acteur = request.form.get('acteur', '')
        verificateur = request.form.get('verificateur', '')
        base_donnees = request.form.get('base_donnees', '')
        reference_ticket = request.form.get('reference_ticket', '')
        utilisateur = session.get('username')

        # Dates de validation et expiration automatiques
        date_validation = datetime.now()
        date_expiration = date_validation + timedelta(days=90)

        # Gestion des pièces jointes
        fichiers_noms = []
        if 'pieces_jointes[]' in request.files:
            for file in request.files.getlist('pieces_jointes[]'):
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = str(uuid.uuid4()) + '_' + filename
                    upload_file_to_ftp(file.stream, unique_filename)
                    fichiers_noms.append(unique_filename)

        pieces_jointes_str = ';'.join(fichiers_noms) if fichiers_noms else ''
        # ajout pour pouvoir comit
        # Insertion de la procédure complète
        cursor.execute("""
            INSERT INTO procedures (
                mots_cles, titre, description, protocole_resolution, protocole_verification,
                acteur, verificateur, base_donnees, reference_ticket,
                utilisateur, date_validation, date_expiration, pieces_jointes, statut
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            mots_cles, titre, description, protocole_resolution, protocole_verification,
            acteur, verificateur, base_donnees, reference_ticket,
            utilisateur, date_validation, date_expiration, pieces_jointes_str, "À vérifier"
        ))

        procedure_id = cursor.lastrowid

        # Applications impactées
        application_ids = request.form.getlist('application_id[]')
        for app_id in application_ids:
            cursor.execute("INSERT INTO procedure_applications (procedure_id, application_id) VALUES (%s, %s)", (procedure_id, app_id))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('home'))

    # GET → chargement du formulaire
    cursor.execute("SELECT id, nom, couleur FROM applications")
    applications = cursor.fetchall()

    cursor.execute("""
        SELECT u.utilisateur FROM utilisateurs u
        JOIN services s ON u.service_id = s.id
        WHERE s.nom = 'direction' OR s.id = (SELECT service_id FROM utilisateurs WHERE id = %s)
    """, (session['user_id'],))
    verificateurs = cursor.fetchall()

    cursor.close()
    conn.close()

    couleurs_dict = {str(app['id']): app['couleur'] for app in applications}

    return render_template('add_procedure.html',
                               applications=applications,
                               couleurs_dict=couleurs_dict,
                               verificateurs=verificateurs
                           )

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
    if 'upload' not in request.files:
        return jsonify({'uploaded': False, 'error': {'message': 'Aucun fichier envoyé'}})

    file = request.files['upload']
    if file.filename == '':
        return jsonify({'uploaded': False, 'error': {'message': 'Nom de fichier invalide'}})

    if not allowed_file(file.filename):
        return jsonify({'uploaded': False, 'error': {'message': 'Extension non autorisée'}})

    filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        file.save(file_path)
        file_url = url_for('serve_uploaded_images', filename=filename, _external=True)
        return jsonify({
            "uploaded": True,
            "url": file_url
        })
    except Exception as e:
        return jsonify({'uploaded': False, 'error': {'message': str(e)}})


@app.route('/serve_image/<path:filename>')
def serve_uploaded_images(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/configuration', methods=['GET', 'POST'])
def configuration():
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.url))  # Redirige vers login et garde l'URL en mémoire

    if not is_admin():
        flash("⚠️ Accès refusé : Vous devez être administrateur pour accéder à cette page.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Traitement de l'ajout d'une application
    if request.method == 'POST' and request.form.get("app_name"):
        app_name = request.form.get("app_name")
        app_color = request.form.get("app_color", "#000000")

        cursor.execute("INSERT INTO applications (nom, couleur) VALUES (%s, %s)", (app_name, app_color))
        conn.commit()
        flash("✅ Application ajoutée avec succès.", "success")
        return redirect(url_for('configuration'))

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

    # 🔍 Vérifier si un utilisateur existe déjà avec le même nom et service
    cursor.execute("""
        SELECT COUNT(*) FROM utilisateurs 
        WHERE utilisateur = %s AND service_id = %s
    """, (username, service_id))
    existing_user = cursor.fetchone()['COUNT(*)']

    if existing_user > 0:
        flash("⚠️ Un utilisateur avec ce nom et ce service existe déjà.", "warning")
    else:
        cursor.execute("""
            INSERT INTO utilisateurs (utilisateur, password, service_id) 
            VALUES (%s, %s, %s)
        """, (username, password, service_id if service_id else None))
        conn.commit()
        flash("✅ Utilisateur ajouté avec succès.", "success")

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
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET statut = 'Validée' WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("✅ La procédure a été validée.", "success")
    return redirect(request.referrer or url_for('home'))

@app.route('/soft_delete/<int:id>', methods=['POST'])
def soft_delete(id):
    if 'user_id' not in session or not is_admin():
        flash("⚠️ Accès refusé : Vous devez être administrateur pour supprimer une procédure.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET est_supprime = TRUE, supprime_par = %s WHERE id = %s", (session['username'], id))
    conn.commit()
    cursor.close()
    conn.close()

    flash("✅ Procédure marquée comme supprimée.", "info")
    return redirect(url_for('home'))

@app.route('/restore_procedure/<int:id>', methods=['POST'])
def restore_procedure(id):
    if 'user_id' not in session or not is_admin():
        flash("⚠️ Accès refusé : Vous devez être administrateur pour restaurer une procédure.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET est_supprime = FALSE, supprime_par = NULL WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("✅ Procédure restaurée avec succès.", "success")
    return redirect(url_for('deleted_procedures'))

@app.route('/gestion_a_verifier')
def gestion_a_verifier():
    if 'user_id' not in session or not session.get("est_moderateur"):
        logging.debug("Accès refusé : utilisateur non connecté ou non modérateur")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket,
           COALESCE(CAST(GROUP_CONCAT(a.nom SEPARATOR ', ') AS CHAR), '') AS applications,
           COALESCE(CAST(GROUP_CONCAT(a.couleur SEPARATOR ', ') AS CHAR), '') AS couleurs,
           p.statut, p.utilisateur, p.verificateur
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        WHERE p.statut = 'À vérifier'
          AND p.verificateur = %s
          AND (p.est_supprime = 0 OR p.est_supprime IS NULL)
        GROUP BY p.id, p.titre, p.description, p.mots_cles, p.reference_ticket,
                 p.statut, p.utilisateur, p.verificateur
    """
    cursor.execute(query, (session['username'],))

    procedures = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('gestion_a_verifier.html', procedures=procedures)


@app.route('/reject_procedure/<int:id>', methods=['POST'])
def reject_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET statut = 'Rejetée' WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("❌ La procédure a été rejetée.", "danger")
    return redirect(request.referrer or url_for('home'))

@app.route('/correct_procedure/<int:id>', methods=['POST'])
def correct_procedure(id):
    if 'user_id' not in session:
        flash("? Accès refusé.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Vérifier si l'utilisateur est bien l'auteur de la procédure
    cursor.execute("UPDATE procedures SET statut = 'À vérifier' WHERE id = %s", (id,))
    utilisateur = cursor.fetchone()

    if utilisateur and utilisateur[0] == session.get("username"):
        # ? Mettre la procédure à "À valider"
        cursor.execute("UPDATE procedures SET statut = 'À valider' WHERE id = %s", (id,))
        conn.commit()

    cursor.close()
    conn.close()

    flash("?? La procédure a été corrigée et est de nouveau en attente de validation.", "info")
    return redirect(url_for('home'))

@app.route('/deleted_procedures')
def deleted_procedures():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ? Récupérer uniquement les procédures supprimées
    cursor.execute("""
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, 
           GROUP_CONCAT(a.nom SEPARATOR ', ') AS applications, 
           p.supprime_par
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

@app.route('/gestion_a_valider')
def gestion_a_valider():
    if 'user_id' not in session or not (session.get("est_admin") or session.get("service") == "direction"):
        flash("⛔ Accès réservé aux administrateurs ou au service direction", "danger")
        return redirect(url_for('home'))

    filtre = request.args.get('filtre', 'toutes')  # par défaut, afficher tout

    conn = get_db_connection()
    cursor = conn.cursor()

    base_query = '''
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket,
               COALESCE(CAST(GROUP_CONCAT(a.nom SEPARATOR ', ') AS CHAR), '') AS applications,
               COALESCE(CAST(GROUP_CONCAT(a.couleur SEPARATOR ', ') AS CHAR), '') AS couleurs,
               p.statut, p.utilisateur
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        LEFT JOIN utilisateurs u ON u.utilisateur = p.utilisateur
        LEFT JOIN services s ON s.id = u.service_id
        WHERE p.statut = 'À valider'
          AND (p.est_supprime IS NULL OR p.est_supprime = 0)
    '''

    if filtre == 'mes':
        base_query += " AND (s.id = %s OR s.nom = 'direction')"
        params = (session.get('service_id'),)
    else:
        params = ()

    base_query += '''
        GROUP BY p.id, p.titre, p.description, p.mots_cles, p.reference_ticket,
                 p.statut, p.utilisateur
    '''

    cursor.execute(base_query, params)
    procedures = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('gestion_a_valider.html', procedures=procedures, filtre=filtre)

@app.route('/like/<int:id>', methods=['POST'])
def like_procedure(id):
    if 'username' not in session:
        return redirect(url_for('login'))  # ? Rediriger si non connecté

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ? Vérifier si l'utilisateur a déjà voté
        cursor.execute(
            "SELECT * FROM votes WHERE procedure_id = %s AND utilisateur = %s",
            (id, session['username'])
        )
        existing_vote = cursor.fetchone()

        if existing_vote:
            print(f"?? DEBUG - Vote déjà existant pour ID: {id} par {session['username']}")
        else:
            # ? Ajouter le vote si pas encore voté
            cursor.execute(
                "INSERT INTO votes (procedure_id, vote_type, utilisateur) VALUES (%s, 'like', %s)",
                (id, session['username'])
            )
            conn.commit()
    except MySQLdb.IntegrityError as e:
        print(f"? ERREUR SQL - {e}")  # ? Debug si erreur
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('home'))

@app.route('/dislike/<int:id>', methods=['POST'])
def dislike_procedure(id):
    if 'username' not in session:
        return redirect(url_for('login'))  # ? Rediriger si non connecté

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ? Vérifier si l'utilisateur a déjà voté
        cursor.execute(
            "SELECT * FROM votes WHERE procedure_id = %s AND utilisateur = %s",
            (id, session['username'])
        )
        existing_vote = cursor.fetchone()

        if existing_vote:
            print(f"?? DEBUG - Vote déjà existant pour ID: {id} par {session['username']}")
        else:
            # ? Ajouter le vote si pas encore voté
            cursor.execute(
                "INSERT INTO votes (procedure_id, vote_type, utilisateur) VALUES (%s, 'dislike', %s)",
                (id, session['username'])
            )
            conn.commit()
            print(f"? DEBUG - Dislike ajouté pour ID: {id} par {session['username']}")

    except MySQLdb.IntegrityError as e:
        print(f"? ERREUR SQL - {e}")  # ? Debug si erreur
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
                # ? Si l'utilisateur clique à nouveau sur le même vote ? Supprimer le vote
                cursor.execute(
                    "DELETE FROM votes WHERE procedure_id = %s AND utilisateur = %s",
                    (id, session['username'])
                )
                conn.commit()
                message = f"? Vote supprimé pour ID: {id} ({vote_type})"
                vote_status = None
            else:
                # ? Si l'utilisateur change de vote ? Mettre à jour le vote
                cursor.execute(
                    "UPDATE votes SET vote_type = %s WHERE procedure_id = %s AND utilisateur = %s",
                    (vote_type, id, session['username'])
                )
                conn.commit()
                message = f"? Vote mis à jour pour ID: {id} ({vote_type})"
                vote_status = vote_type
        else:
            # ? Si l'utilisateur n'a jamais voté ? Ajouter un vote
            cursor.execute(
                "INSERT INTO votes (procedure_id, vote_type, utilisateur) VALUES (%s, %s, %s)",
                (id, vote_type, session['username'])
            )
            conn.commit()
            message = f"? Vote ajouté pour ID: {id} ({vote_type})"
            vote_status = vote_type

        print(message)

        # ? Récupérer le nombre de likes/dislikes après l'opération
        cursor.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM votes WHERE procedure_id = %s AND vote_type = 'like') AS likes, "
            "(SELECT COUNT(*) FROM votes WHERE procedure_id = %s AND vote_type = 'dislike') AS dislikes",
            (id, id)
        )
        result = cursor.fetchone()

        return jsonify({'success': True, 'likes': result['likes'], 'dislikes': result['dislikes'], 'vote_status': vote_status})

    except MySQLdb.IntegrityError as e:
        print(f"? ERREUR SQL - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/delete_application/<int:app_id>', methods=['POST'])
def delete_application(app_id):
    if 'user_id' not in session or not is_admin():
        flash("⚠️ Accès refusé : vous devez être administrateur.", "danger")
        return redirect(url_for('configuration'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications WHERE id = %s", (app_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("✅ Application supprimée avec succès.", "success")
    return redirect(url_for('configuration'))

import csv
from io import StringIO

@app.route('/export_deleted_procedures')
def export_deleted_procedures():
    if 'user_id' not in session or not is_admin():
        flash("⚠️ Accès refusé", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.titre, p.mots_cles, p.description, p.reference_ticket, 
               GROUP_CONCAT(a.nom SEPARATOR ', ') AS applications,
               p.supprime_par
        FROM procedures p
        LEFT JOIN procedure_applications pa ON p.id = pa.procedure_id
        LEFT JOIN applications a ON pa.application_id = a.id
        WHERE p.est_supprime = 1
        GROUP BY p.id
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Création du fichier CSV en mémoire
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Titre", "Mots-Clés", "Description", "Ticket", "Applications", "Supprimé par"])
    for row in rows:
        writer.writerow([
            row["titre"],
            row["mots_cles"],
            row["description"],
            row["reference_ticket"],
            row["applications"],
            row["supprime_par"]
        ])

    output.seek(0)

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=procedures_supprimees.csv"}
    )

@app.route('/verify_procedure/<int:id>', methods=['POST'])
def verify_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Vérifier que l'utilisateur est bien le vérificateur
    cursor.execute("SELECT verificateur FROM procedures WHERE id = %s", (id,))
    result = cursor.fetchone()
    if result and result['verificateur'] == session['username']:
        cursor.execute("UPDATE procedures SET statut = 'À valider' WHERE id = %s", (id,))
        conn.commit()

    cursor.close()
    conn.close()
    flash("? Procédure vérifiée. En attente de validation par l'administrateur.", "success")
    return redirect(url_for('home'))

@app.route('/reject_procedure_verificateur/<int:id>', methods=['POST'])
def reject_procedure_verificateur(id):
    motif = request.form.get('motif_rejet', '')
    if not motif:
        flash("?? Veuillez indiquer un motif de rejet.", "danger")
        return redirect(url_for('gestion_a_verifier'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE procedures SET statut = 'Rejetée' WHERE id = %s", (id,))
    cursor.execute("INSERT INTO motif_rejet (procedure_id, auteur_rejet, motif, niveau) VALUES (%s, %s, %s, 'verificateur')",
                   (id, session['username'], motif))
    conn.commit()
    cursor.close()
    conn.close()
    flash("? Procédure rejetée avec motif.", "danger")
    return redirect(request.referrer or url_for('home'))

@app.route('/admin_validate_procedure/<int:id>', methods=['POST'])
def admin_validate_procedure(id):
    if not is_admin():
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE procedures SET statut = 'Validée' WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("? Procédure validée.", "success")
    return redirect(url_for('gestion_a_valider'))

@app.route('/reject_procedure_admin/<int:id>', methods=['POST'])
def reject_procedure_admin(id):
    motif = request.form.get('motif_rejet', '')
    if not motif:
        flash("?? Veuillez indiquer un motif de rejet.", "danger")
        return redirect(url_for('gestion_a_valider'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE procedures SET statut = 'Rejetée' WHERE id = %s", (id,))
    cursor.execute("INSERT INTO motif_rejet (procedure_id, auteur_rejet, motif, niveau) VALUES (%s, %s, %s, 'admin')",
                   (id, session['username'], motif))
    conn.commit()
    cursor.close()
    conn.close()
    flash("? Procédure rejetée avec motif.", "danger")
    return redirect(request.referrer or url_for('home'))

@app.route('/motif_rejet/<int:procedure_id>')
def motif_rejet(procedure_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT motif, auteur_rejet, niveau, date_rejet FROM motif_rejet WHERE procedure_id = %s ORDER BY date_rejet DESC", (procedure_id,))
    motifs = cursor.fetchall()
    cursor.close()
    conn.close()

    # Peut aussi être rendu dans une modale
    return render_template_string("""
    <ul>
    {% for m in motifs %}
        <li><strong>{{ m['niveau']|capitalize }}</strong> ({{ m['auteur_rejet'] }}) le {{ m['date_rejet'] }} :<br>{{ m['motif'] }}</li>
    {% endfor %}
    </ul>
    """, motifs=motifs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
