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

# Fonction pour obtenir une connexion MySQL
def get_db_connection():
    return MySQLdb.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PASSWORD,
        db=DB_NAME,
        charset='utf8mb4'
    )

# Configuration pour les pièces jointes
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def format_code_blocks(text):
    # Remplace les blocs entre crochets par des balises de code avec coloration syntaxique
    return re.sub(r'\[(.*?)\]', r'<pre><code class="sql">\1</code></pre>', text, flags=re.DOTALL)

@app.route('/')
def home():
    query = request.args.get('query')
    app_filter = request.args.get('application_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    base_query = """
        SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, a.nom, a.couleur
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

        # Vérification et conversion de l'application_id
        application_id_str = request.form.get('application_id', '').strip()
        application_id = int(application_id_str) if application_id_str.isdigit() else None

        # Gestion des pièces jointes
        pieces_jointes = request.files.getlist('pieces_jointes')
        pieces_jointes_filenames = []
        for piece in pieces_jointes:
            if piece and piece.filename:
                filename = piece.filename[:255]
                piece.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                pieces_jointes_filenames.append(filename)
        pieces_jointes_str = ','.join(pieces_jointes_filenames)

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
    return render_template('add_procedure.html', applications=applications)

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

        cursor.execute('''UPDATE procedures 
                          SET mots_cles=%s, titre=%s, description=%s, protocole_resolution=%s, protocole_verification=%s, acteur=%s, verificateur=%s, reference_ticket=%s, application_id=%s, utilisateur=%s
                          WHERE id=%s''',
                          (mots_cles, titre, description, protocole_resolution, protocole_verification, acteur, verificateur, reference_ticket, application_id, utilisateur, id))
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
    return render_template('edit_procedure.html', procedure=procedure, applications=applications)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_procedure(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM procedures WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('home'))

@app.route('/view/<int:id>')
def view_procedure(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, a.nom, a.couleur 
        FROM procedures p
        LEFT JOIN applications a ON p.application_id = a.id
        WHERE p.id = %s
    ''', (id,))
    procedure = cursor.fetchone()
    cursor.close()
    conn.close()

    pieces_jointes = procedure[10].split(',') if procedure[10] else []

    # Application de la mise en forme aux champs contenant du code
    formatted_description = format_code_blocks(procedure[3])
    formatted_resolution = format_code_blocks(procedure[4])
    formatted_verification = format_code_blocks(procedure[5])

    return render_template('view_procedure.html', procedure=procedure, pieces_jointes=pieces_jointes,
                           formatted_description=formatted_description, formatted_resolution=formatted_resolution,
                           formatted_verification=formatted_verification)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
