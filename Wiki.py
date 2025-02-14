from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, abort
import MySQLdb
import os
import re
import markdown
from ftplib import FTP

# Code pour le backend
app = Flask(__name__)
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

@app.route('/view/<int:id>')
def view_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, COALESCE(a.nom, 'Non spécifiée') AS application_name, COALESCE(a.couleur, '#5D5D5D') AS application_color
        FROM procedures p
        LEFT JOIN applications a ON p.application_id = a.id
        WHERE p.id = %s
    """, (id,))
    procedure = cursor.fetchone()
    cursor.close()
    conn.close()

    pieces_jointes_links = procedure[10].split(',') if procedure[10] else []

    # Convertir les champs Markdown en HTML
    formatted_description = markdown.markdown(format_code_blocks(procedure[3]))
    formatted_resolution = markdown.markdown(format_code_blocks(procedure[4]))
    formatted_verification = markdown.markdown(format_code_blocks(procedure[5]))

    return render_template('view_procedure.html', procedure=procedure,
                           pieces_jointes_links=pieces_jointes_links,
                           formatted_description=formatted_description,
                           formatted_resolution=formatted_resolution,
                           formatted_verification=formatted_verification,
                           application_color=procedure[-1],  # Couleur de l'application
                           title=procedure[2])


@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Récupérer toutes les applications pour le filtre
    cursor.execute("SELECT id, nom FROM applications")
    applications = cursor.fetchall()

    # Récupérer les filtres
    search_keywords = request.args.get('search_keywords', '').strip()
    search_application = request.args.get('search_application', '')

    query = """
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, COALESCE(a.nom, 'Non spécifiée') AS application_name, COALESCE(a.couleur, '#5D5D5D') AS application_color
        FROM procedures p
        LEFT JOIN applications a ON p.application_id = a.id
        WHERE 1=1
    """
    params = []

    if search_keywords:
        query += " AND (p.titre LIKE %s OR p.description LIKE %s OR p.mots_cles LIKE %s)"
        params.extend([f"%{search_keywords}%", f"%{search_keywords}%", f"%{search_keywords}%"])

    if search_application:
        query += " AND p.application_id = %s"
        params.append(search_application)

    cursor.execute(query, params)
    procedures = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('home.html', procedures=procedures, applications=applications)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM utilisateurs WHERE utilisateur = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['username'] = username
            return redirect(url_for('home'))
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


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_procedure(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        titre = request.form['titre']
        description = request.form['description']
        protocole_resolution = request.form['protocole_resolution']
        protocole_verification = request.form['protocole_verification']
        application_id = request.form.get('application_id')

        cursor.execute(
            "UPDATE procedures SET titre=%s, description=%s, protocole_resolution=%s, protocole_verification=%s, application_id=%s WHERE id=%s",
            (titre, description, protocole_resolution, protocole_verification, application_id, id))
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('home'))

    cursor.execute("SELECT * FROM procedures WHERE id = %s", (id,))
    procedure = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('edit_procedure.html', procedure=procedure)

@app.route('/add', methods=['GET', 'POST'])
def add_procedure():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        titre = request.form['titre']
        description = request.form['description']
        protocole_resolution = request.form['protocole_resolution']
        protocole_verification = request.form['protocole_verification']
        application_id = request.form.get('application_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO procedures (titre, description, protocole_resolution, protocole_verification, application_id) VALUES (%s, %s, %s, %s, %s)",
                       (titre, description, protocole_resolution, protocole_verification, application_id))
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('home'))

    return render_template('add_procedure.html')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
