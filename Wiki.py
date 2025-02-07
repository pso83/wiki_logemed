from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import MySQLdb
import os

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

@app.route('/')
def home():
    query = request.args.get('query')
    conn = get_db_connection()
    cursor = conn.cursor()
    if query:
        cursor.execute("""
            SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, a.nom 
            FROM procedures p
            LEFT JOIN applications a ON p.application_id = a.id
            WHERE p.mots_cles LIKE %s
        """, ('%' + query + '%',))
    else:
        cursor.execute("""
            SELECT p.id, p.titre, p.description, p.mots_cles, p.reference_ticket, a.nom 
            FROM procedures p
            LEFT JOIN applications a ON p.application_id = a.id
        """)
    procedures = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('home.html', procedures=procedures)

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
        piece_jointe = request.files.get('piece_jointe')
        piece_jointe_filename = ''
        if piece_jointe and piece_jointe.filename:
            piece_jointe_filename = piece_jointe.filename[:255]  # Limiter à 255 caractères
            piece_jointe.save(os.path.join(app.config['UPLOAD_FOLDER'], piece_jointe_filename))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO procedures (mots_cles, titre, description, protocole_resolution, protocole_verification, acteur, verificateur, application_id, reference_ticket, piece_jointe, utilisateur) 
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                          (mots_cles, titre, description, protocole_resolution, protocole_verification, acteur, verificateur, application_id, reference_ticket, piece_jointe_filename, utilisateur))
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
                          SET mots_cles=%s, titre=%s, description=%s, protocole_resolution=%s, protocole_verification=%s, acteur=%s, verificateur=%s, application_id=%s, reference_ticket=%s, utilisateur=%s
                          WHERE id=%s''',
                          (mots_cles, titre, description, protocole_resolution, protocole_verification, acteur, verificateur, application_id, reference_ticket, utilisateur, id))
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
    cursor.execute("SELECT * FROM procedures WHERE id = %s", (id,))
    procedure = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('view_procedure.html', procedure=procedure)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
