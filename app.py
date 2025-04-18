from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
import logging
from dotenv import load_dotenv
import os
import requests
from datetime import timedelta


load_dotenv()
gemini_api_key = os.getenv("GEMINI_API_KEY")
db_password = os.getenv("DB_PASSWORD")
app_secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

if not gemini_api_key:
    print("Error: GEMINI_API_KEY not found. Please add it to your .env file.")
else:
    print("Gemini API Key Loaded Successfully")

app = Flask(__name__, static_url_path='/static')
app.secret_key = app_secret_key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
logging.basicConfig(filename='error.log', level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s')

def get_db_connection():
    try:
        return mysql.connector.connect(
            host='127.0.0.1',
            port=3306,  
            user='root',
            password='Bhoomi31',
            database='legal_guidance'
        )
    except mysql.connector.Error as e:
        logging.error(f"Database connection failed: {e}")
        return None

def ask_gemini(prompt):
    api_key = gemini_api_key
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [
            {
                "parts": [
                    {"text": f"You are LawXpert, an AI-powered legal assistant. {prompt}"}
                ]
            }
        ]
    }
    try:
        response = requests.post(f"{url}?key={api_key}", json=data, headers=headers)
        if response.status_code != 200:
            logging.error(f"API Error: {response.status_code} - {response.text}")
            return "Sorry, there was an issue with the AI service."
        
        response_data = response.json()
        return response_data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        logging.error(f"Gemini API Error: {e}")
        return "Sorry, I couldn't process your request at the moment."


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        connection = get_db_connection()
        if connection is None:
            return "Database connection failed."

        try:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO Users (name, email, password, role) VALUES (%s, %s, %s, %s)", 
                           (name, email, password, role))
            connection.commit()
            cursor.close()
            connection.close()
            return redirect(url_for('login'))
        except Exception as e:
            logging.error(f"Registration Error: {e}")
            return "Error during registration. Please try again."

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        connection = get_db_connection()
        if connection is None:
            return "Database connection failed."

        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Users WHERE email=%s AND password=%s", (email, password))
            user = cursor.fetchone()
            cursor.close()
            connection.close()

            if user:
                session['user_id'] = user.get('user_id')
                session['role'] = user.get('role')
                session.permanent = True
                return redirect(url_for('dashboard'))
            else:
                return "Invalid email or password. Please try again."
        except Exception as e:
            logging.error(f"Login Error: {e}")
            return "An error occurred. Please try again."

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        return render_template('dashboard.html', role=session.get('role'))
    else:
        return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', user_id=session['user_id'])


@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_message = request.form.get('message')
    if not user_message:
        return jsonify({"error": "Message cannot be empty"}), 400

    ai_response = ask_gemini(user_message)
    return jsonify({"user_message": user_message, "ai_response": ai_response})


@app.route('/connect_lawyer', methods=['POST'])
def connect_lawyer():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    lawyer_type = request.form.get('lawyer_type')

    connection = get_db_connection()
    if connection is None:
        return "Database connection failed."

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Lawyers WHERE specialization = %s", (lawyer_type,))
        lawyer = cursor.fetchone()
        cursor.close()
        connection.close()

        if lawyer:
            return f"Successfully connected! Lawyer Name: {lawyer['name']}, Contact: {lawyer['contact']}"
        else:
            return "No lawyer found for your selected category."
    except Exception as e:
        logging.error(f"Lawyer Connection Error: {e}")
        return "An error occurred. Please try again later."

@app.errorhandler(Exception)
def handle_exception(e):
    logging.error(f"Unhandled Error: {e}")
    return "An unexpected error occurred. Please try again later.", 500

@app.route('/community')
def community():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('community.html', user_id=session['user_id'])    

@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == '__main__':
    app.run(debug=True)
