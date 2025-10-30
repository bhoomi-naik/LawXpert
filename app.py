from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
import logging
from dotenv import load_dotenv
import os
import requests
from datetime import timedelta
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
import pandas as pd
import traceback
from sklearn.metrics.pairwise import cosine_similarity
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

print("Loading free Legal QA model...")
tokenizer = AutoTokenizer.from_pretrained("TheGod-2003/legal_QA_model")
model = AutoModelForSeq2SeqLM.from_pretrained("TheGod-2003/legal_QA_model")
print("Legal QA model loaded successfully.")


ipc_df = pd.read_csv(r"C:\Users\Bhoomi\OneDrive\Documents\Lawdata\ipc_clean_sections.csv")
ipc_vectorizer = TfidfVectorizer(stop_words="english")
ipc_X = ipc_vectorizer.fit_transform(ipc_df["content"])

db_password = os.getenv("DB_PASSWORD")
app_secret_key = os.getenv("FLASK_SECRET_KEY")

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'super_secret_key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
logging.basicConfig(filename='error.log', level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s')


try:
    category_model = pickle.load(open('category_model.pkl', 'rb'))
    category_vectorizer = pickle.load(open('vectorizer.pkl', 'rb'))
except:
    data = {
        "Query": [
            "My landlord is not returning my deposit",
            "I am being harassed by police",
            "Company refusing refund for broken product",
            "Husband refuses to pay alimony",
            "Visa got rejected unfairly",
            "Neighbour threatening me",
            "Manager is not paying my salary",
            "Received divorce notice",
            "Caught in fake fraud case",
            "Struggling to get Indian citizenship",
        ],
        "Category": [
            "Civil", "Criminal", "Consumer", "Family", "Immigration",
            "Criminal", "Civil", "Family", "Criminal", "Immigration"
        ]
    }
    df = pd.DataFrame(data)
    X = df['Query']
    y = df['Category']
    category_vectorizer = TfidfVectorizer()
    X_vec = category_vectorizer.fit_transform(X)
    category_model = MultinomialNB()
    category_model.fit(X_vec, y)
    pickle.dump(category_model, open('category_model.pkl', 'wb'))
    pickle.dump(category_vectorizer, open('vectorizer.pkl', 'wb'))
def get_db_connection():
    try:
        return mysql.connector.connect(
            host='127.0.0.1',
            port=3306,
            user='root',
            password=db_password,
            database='legal_guidance'
        )
    except mysql.connector.Error as e:
        logging.error(f"Database connection failed: {e}")
        return None


def search_ipc(query, top_n=3, max_chars=500):
 #casual queries 
    casual_keywords = ["hello", "hi", "how are you", "thanks", "bye", "who are you", "your name", "what can you do"]
    query_lower = query.lower().strip()

    for word in casual_keywords:
        if word in query_lower:
            return pd.DataFrame([{
                "section": "🤖",
                "title": "I'm LawXpert, your legal assistant!",
                "preview": "Ask me any legal query — like 'what is IPC 302' or 'punishment for theft'. I’ll search IPC for you!"
            }])
    
   
    try:
        query_vec = ipc_vectorizer.transform([query])
        sim_scores = cosine_similarity(query_vec, ipc_X).flatten()
        top_indices = sim_scores.argsort()[-top_n:][::-1]
        results = ipc_df.iloc[top_indices].copy()

        results["preview"] = results["content"].apply(
            lambda x: x[:max_chars] + "..." if len(x) > max_chars else x
        )
        return results[["section", "title", "preview"]]
    except Exception as e:
        logging.error(f"IPC Search Error: {e}")
        return pd.DataFrame()


@app.route('/')
def index():
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
                return "Invalid email or password."
        except Exception as e:
            logging.error(f"Login Error: {e}")
            return "An error occurred. Please try again."

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        return render_template('dashboard.html', role=session.get('role'))
    return redirect(url_for('login'))

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

    try:
        results = search_ipc(user_message)

        if results.empty:
            return jsonify({"user_message": user_message, "ai_response": "Sorry, I couldn't find anything relevant."})

        response = ""
        for _, row in results.iterrows():
            response += f"\n\n🔹 **{row['section']}: {row['title']}**\n{row['preview']}"

        return jsonify({"user_message": user_message, "ai_response": response.strip()})
    except Exception as e:
        logging.error(f"Chat Error: {e}\n{traceback.format_exc()}")
        return jsonify({"user_message": user_message, "ai_response": "An internal error occurred while processing your query."})

@app.route('/send_chat', methods=['POST'])
def send_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    receiver_id = request.form['receiver_id']
    message = request.form['message']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO Messages (sender_id, receiver_id, message, timestamp) VALUES (%s, %s, %s, NOW())",
        (session['user_id'], receiver_id, message)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})
@app.route('/send_user_message', methods=['POST'])
def send_user_message():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    sender_id = session['user_id']
    receiver_id = request.form.get('receiver_id')
    message = request.form.get('message')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Messages (sender_id, receiver_id, content) VALUES (%s, %s, %s)", 
                       (sender_id, receiver_id, message))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'status': 'Message sent'})
    except Exception as e:
        logging.error(f"Send Message Error: {e}")
        return jsonify({'error': 'Failed to send message'}), 500
@app.route('/get_messages', methods=['GET'])
def get_messages():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    chat_with = request.args.get('chat_with')  

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM Messages
            WHERE (sender_id = %s AND receiver_id = %s)
               OR (sender_id = %s AND receiver_id = %s)
            ORDER BY timestamp ASC
        """, (user_id, chat_with, chat_with, user_id))
        messages = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({'messages': messages})
    except Exception as e:
        logging.error(f"Fetch Messages Error: {e}")
        return jsonify({'error': 'Failed to fetch messages'}), 500

@app.route('/get_messages/<int:chat_with_id>')
def get_chat_messages():  
    ...

    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM Messages 
        WHERE (sender_id = %s AND receiver_id = %s) 
           OR (sender_id = %s AND receiver_id = %s)
        ORDER BY timestamp ASC
    """, (session['user_id'], chat_with_id, chat_with_id, session['user_id']))
    messages = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(messages)


@app.route('/predict_category', methods=['POST'])
def predict_category():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_query = request.form.get('query')
    if not user_query:
        return jsonify({"error": "Query cannot be empty"}), 400

    try:
        query_vec = category_vectorizer.transform([user_query])
        predicted_category = category_model.predict(query_vec)[0]
        return jsonify({"predicted_category": predicted_category})
    except Exception as e:
        logging.error(f"Prediction Error: {e}")
        return jsonify({"error": "Internal prediction error"}), 500

def get_legal_response(user_query):
    try:
        input_text = f"question: {user_query}"
        inputs = tokenizer(input_text, return_tensors="pt", max_length=512, truncation=True)
        outputs = model.generate(**inputs, max_length=200)
        answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return answer
    except Exception as e:
        return f"Error generating response: {e}"
  
@app.route('/connect_lawyer', methods=['POST'])
def connect_lawyer():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    lawyer_type = request.form.get('lawyesr_type', '').strip()
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "Database connection failed."})

    try:
        cursor = connection.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT * FROM Lawyers 
            WHERE specialization=%s AND is_online=TRUE
            LIMIT 1
        """, (lawyer_type,))
        lawyer = cursor.fetchone()
        cursor.close()
        connection.close()

        if lawyer:
            
            session['chat_lawyer_id'] = lawyer['lawyer_id']
            return jsonify({
                "message": f"👩‍⚖️ Connected to {lawyer['name']} ({lawyer['specialization']})",
                "lawyer_id": lawyer['lawyer_id']
            })
        else:
            return jsonify({"message": "No online lawyer available. Please try later."})

    except Exception as e:
        logging.error(f"Connect Lawyer Error: {e}")
        return jsonify({"error": "Failed to connect to a lawyer."})


@app.route('/community')
def community():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('community.html', user_id=session['user_id'])

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.errorhandler(Exception)
def handle_exception(e):
    logging.error(f"Unhandled Error: {e}")
    return "An unexpected error occurred. Please try again later.", 500

if __name__ == '__main__':
    app.run(debug=True)
