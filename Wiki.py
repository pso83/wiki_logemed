from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import MySQLdb
import os
import re

app = Flask(__name__)

# Configuration de la base de données
DB_HOST = '194.164.60.164'
DB_USER = 'devlog'
DB_PASSWORD = '123456Sou_log'
DB_NAME = 'wiki_db'

# Configuration pour les pièces jointes
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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

@app.route('/')
def home():
    query = request.args.get('query')
    app_filter = request.args.get('application_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    base_query = """
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, a.nom, COALESCE(a.couleur, '#5D5D5D')
        FROM procedures p
        LEFT JOIN applications a ON p.application_id = a.id
    """

    filters = []
    params = []

    if query:
        keywords = query.split('#')
        keywords = [kw.strip() for kw in keywords if kw.strip()]
        search_query = " OR ".join(["p.mots_cles LIKE %s" for _ in keywords])
        filters.append(f"({search_query})")
        params.extend([f'%#{kw}%' for kw in keywords])

    if app_filter and app_filter.isdigit():
        filters.append("p.application_id = %s")
        params.append(int(app_filter))

    if filters:
        base_query += " WHERE " + " AND ".join(filters)

    cursor.execute(base_query, tuple(params))
    procedures = cursor.fetchall()

    cursor.execute("SELECT id, nom FROM applications")
    applications = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('home.html', procedures=procedures, applications=applications)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/add', methods=['GET', 'POST'])
def add_procedure():
    if request.method == 'POST':
        mots_cles = request.form.get('mots_cles', '')
        titre = request.form.get('titre', '')
        description = request.form.get('description', '')
        protocole_resolution = request.form.get('protocole_resolution', '')
        protocole_verification = request.form.get('protocole_verification', '')
        acteur = request.form.get('acteur', '')
        verificateur = request.form.get('verificateur', '')
        reference_ticket = request.form.get('reference_ticket', '')
        utilisateur = request.form.get('utilisateur', '')

        application_id_str = request.form.get('application_id', '').strip()
        application_id = int(application_id_str) if application_id_str.isdigit() else None

        uploaded_files = request.files.getlist('pieces_jointes')
        pieces_jointes_links = []

        for file in uploaded_files:
            if file and file.filename:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                file.save(filepath)
                link = url_for('uploaded_file', filename=file.filename)
                pieces_jointes_links.append(link)

        pieces_jointes_str = ','.join(pieces_jointes_links)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO procedures (mots_cles, titre, description, protocole_resolution, protocole_verification, acteur, verificateur, application_id, reference_ticket, piece_jointe, utilisateur)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                          (mots_cles, titre, description, protocole_resolution, protocole_verification, acteur, verificateur, application_id, reference_ticket, pieces_jointes_str, utilisateur))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications")
    applications = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('add_procedure.html', applications=applications, title="Nouvelle Procédure")

@app.route('/view/<int:id>')
def view_procedure(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.mots_cles, p.titre, p.description, p.protocole_resolution, 
               p.protocole_verification, p.acteur, p.verificateur, p.application_id, 
               p.reference_ticket, p.piece_jointe, p.utilisateur, a.nom, COALESCE(a.couleur, '#5D5D5D')
        FROM procedures p
        LEFT JOIN applications a ON p.application_id = a.id
        WHERE p.id = %s
    ''', (id,))
    procedure = cursor.fetchone()
    cursor.close()
    conn.close()

    pieces_jointes = procedure[10].split(',') if procedure[10] else []

    formatted_description = format_code_blocks(procedure[3])
    formatted_resolution = format_code_blocks(procedure[4])
    formatted_verification = format_code_blocks(procedure[5])

    return render_template('view_procedure.html', procedure=procedure, pieces_jointes=pieces_jointes,
                           formatted_description=formatted_description,
                           formatted_resolution=formatted_resolution,
                           formatted_verification=formatted_verification,
                           title=procedure[2])

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_procedure(id):
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
        reference_ticket = request.form.get('reference_ticket', '')
        utilisateur = request.form.get('utilisateur', '')

        application_id_str = request.form.get('application_id', '').strip()
        application_id = int(application_id_str) if application_id_str.isdigit() else None

        uploaded_files = request.files.getlist('pieces_jointes')
        pieces_jointes_links = []

        for file in uploaded_files:
            if file and file.filename:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                file.save(filepath)
                link = url_for('uploaded_file', filename=file.filename)
                pieces_jointes_links.append(link)

        pieces_jointes_str = ','.join(pieces_jointes_links)

        cursor.execute('''UPDATE procedures SET mots_cles=%s, titre=%s, description=%s, protocole_resolution=%s, protocole_verification=%s, acteur=%s, verificateur=%s, application_id=%s, reference_ticket=%s, piece_jointe=%s, utilisateur=%s WHERE id=%s''',
                          (mots_cles, titre, description, protocole_resolution, protocole_verification, acteur, verificateur, application_id, reference_ticket, pieces_jointes_str, utilisateur, id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('home'))

    cursor.execute("SELECT * FROM procedures WHERE id = %s", (id,))
    procedure = cursor.fetchone()
    cursor.execute("SELECT * FROM applications")
    applications = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('add_procedure.html', procedure=procedure, applications=applications, title=procedure[2])

@app.route('/delete/<int:id>', methods=['POST'])
def delete_procedure(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM procedures WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
