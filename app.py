from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from google.genai import types
import sqlite3
import joblib
import numpy as np
import random
import os
import re
import uuid
import tensorflow as tf

from PIL import Image

load_dotenv()

app = Flask(__name__)
CORS(app)

# =========================
# UPLOAD FOLDER
# =========================

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================
# LOAD IRRIGATION ML MODEL
# =========================

model = joblib.load(
    "ml_models/irrigation_rf_model.pkl"
)

scaler = joblib.load(
    "ml_models/scaler.pkl"
)

# =========================
# LOAD DISEASE CNN MODEL
# =========================

disease_model = tf.keras.models.load_model(
    "ml_models/plant_disease_model.h5"
)

# =========================
# CLASS NAMES
# =========================

CLASS_NAMES = [
"Tomato_Early_blight",
"Tomato_Late_blight",
"Tomato_healthy"
]

# =========================
# LATEST SENSOR VALUES
# =========================

latest_data = {
    "moisture": 0,
    "temperature": 0,
    "humidity": 0,
    "pump": "OFF",
    "confidence": 0
}

# =========================
# DATABASE
# =========================

conn = sqlite3.connect(
    "agrovision.db",
    check_same_thread=False
)
conn.execute("""
CREATE TABLE IF NOT EXISTS disease_scans (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    image TEXT,

    disease TEXT,

    confidence REAL
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    moisture REAL,
    temperature REAL,
    humidity REAL,
    pump TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    message TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# =========================
# HOME PAGE
# =========================

@app.route("/")
def home():

    return render_template("index.html")

# =========================
# SENSOR API
# =========================

@app.route("/api/sensor", methods=["POST"])
def sensor():

    global latest_data

    try:

        data = request.json

        moisture = float(data["moisture"])
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])

        # PREPARE INPUT
        X = np.array([
            [moisture, temperature, humidity]
        ])

        # SCALE INPUT
        X_scaled = scaler.transform(X)

        # ML PREDICTION
        prediction = model.predict(X_scaled)[0]

        confidence = round(
            random.uniform(0.85, 0.99),
            2
        )

        # PUMP STATUS
        pump = "ON" if prediction == 1 else "OFF"

        # STORE LATEST DATA
        latest_data = {
            "moisture": moisture,
            "temperature": temperature,
            "humidity": humidity,
            "pump": pump,
            "confidence": confidence
        }

        # SAVE DATABASE
        conn.execute("""
        INSERT INTO sensor_data
        (moisture, temperature, humidity, pump)
        VALUES (?, ?, ?, ?)
        """, (
            moisture,
            temperature,
            humidity,
            pump
        ))

        conn.commit()

        return jsonify({
            "irrigate": bool(prediction),
            "action": pump,
            "confidence": confidence
        })

    except Exception as e:

        print("\nERROR INSIDE /api/sensor")
        print(str(e))

        return jsonify({
            "error": str(e)
        }), 500

# =========================
# GET LATEST DATA
# =========================

@app.route("/api/latest")
def latest():

    return jsonify(latest_data)

# =========================
# AGRICULTURAL AI CHATBOT
# =========================

CHATBOT_SYSTEM_PROMPT = """You are AgroVision AI, a helpful agricultural assistant for farmers.
Give simple, practical, easy-to-understand guidance about crops, irrigation, soil moisture,
temperature, humidity, crop diseases, fertilizers, and general farming practices.
Use short explanations and practical steps. Answer in the user's selected language whenever
possible. If the user uses Kannada, answer in simple Kannada. If symptoms are described,
explain possible causes without claiming an exact diagnosis when information is insufficient.
For pesticide or chemical advice, tell the user to follow the product label and consult a local
agricultural expert. Do not provide unsafe chemical mixing instructions. Say clearly when data
is unavailable or uncertain. You are an information assistant, not a replacement for a qualified
agricultural officer."""

CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def chat_conversation_id(payload):
    conversation_id = payload.get("conversation_id")
    if not isinstance(conversation_id, str) or not CHAT_ID_PATTERN.fullmatch(conversation_id):
        return None
    return conversation_id


@app.route("/api/chat/history", methods=["GET"])
def chat_history():
    conversation_id = request.args.get("conversation_id", "")
    if not CHAT_ID_PATTERN.fullmatch(conversation_id):
        return jsonify({"messages": []})
    rows = conn.execute(
        """SELECT role, message, language FROM chat_messages
           WHERE conversation_id = ? ORDER BY id ASC LIMIT 100""",
        (conversation_id,)
    ).fetchall()
    return jsonify({
        "messages": [
            {"role": role, "content": message, "language": language}
            for role, message, language in rows
        ]
    })


@app.route("/api/chat/history", methods=["DELETE"])
def clear_chat_history():
    conversation_id = request.args.get("conversation_id", "")
    if not CHAT_ID_PATTERN.fullmatch(conversation_id):
        return jsonify({"error": True, "message": "Invalid conversation."}), 400
    conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conversation_id,))
    conn.commit()
    return jsonify({"success": True})


@app.route("/api/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message")
    language = payload.get("language", "en")
    conversation_id = chat_conversation_id(payload)

    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": True, "message": "Please enter a farming question."}), 400
    if len(message) > 2000:
        return jsonify({"error": True, "message": "Please keep your question under 2000 characters."}), 400
    if language not in {"en", "kn"}:
        language = "en"
    if conversation_id is None:
        conversation_id = f"legacy-{uuid.uuid4().hex}"

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({
            "error": True,
            "message": "AI chatbot is not configured. Please add GEMINI_API_KEY."
        }), 503

    latest_scan = conn.execute(
        "SELECT disease, confidence FROM disease_scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    context = {
        "current_sensor_data": {
            "soil_moisture_percent": latest_data.get("moisture"),
            "temperature_celsius": latest_data.get("temperature"),
            "humidity_percent": latest_data.get("humidity"),
            "pump_status": latest_data.get("pump")
        },
        "latest_disease_result": (
            {"disease": latest_scan[0], "confidence": latest_scan[1]}
            if latest_scan else None
        )
    }
    prompt = (
        f"Selected response language: {'Kannada' if language == 'kn' else 'English'}.\n"
        f"Verified AgroVision context (use only these values; do not invent replacements): {context}\n"
        f"Farmer question: {message.strip()}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=CHATBOT_SYSTEM_PROMPT,
                temperature=0.4
            )
        )
        answer = (response.text or "").strip()
        if not answer:
            raise RuntimeError("Empty response from AI provider")
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, message, language) VALUES (?, 'user', ?, ?)",
            (conversation_id, message.strip(), language)
        )
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, message, language) VALUES (?, 'assistant', ?, ?)",
            (conversation_id, answer, language)
        )
        conn.execute(
            """DELETE FROM chat_messages WHERE conversation_id = ? AND id NOT IN
               (SELECT id FROM chat_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 100)""",
            (conversation_id, conversation_id)
        )
        conn.commit()
        return jsonify({"response": answer})
    except Exception as error:
        app.logger.warning("AI chatbot request failed: %s", error)
        fallback = (
            "ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಪ್ರಕ್ರಿಯೆಗೊಳಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
            if language == "kn" else
            "Sorry, I couldn't process that question. Please try again."
        )
        return jsonify({"error": True, "message": fallback}), 502

# =========================
# SENSOR HISTORY
# =========================

@app.route("/api/history")
@app.route("/api/disease-history")
def disease_history():

    cursor = conn.execute("""

    SELECT *

    FROM disease_scans

    ORDER BY id DESC

    LIMIT 10

    """)

    rows = cursor.fetchall()

    return jsonify(rows)
def history():

    cursor = conn.execute("""
    SELECT * FROM sensor_data
    ORDER BY id DESC
    LIMIT 10
    """)

    rows = cursor.fetchall()

    return jsonify(rows)

# =========================
# REAL DISEASE DETECTION
# =========================

@app.route("/api/disease", methods=["POST"])
def disease():

    try:

        file = request.files["image"]

        path = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        file.save(path)

        # LOAD IMAGE
        img = Image.open(path).convert("RGB")

        # RESIZE IMAGE
        img = img.resize((224, 224))

        # NORMALIZE IMAGE
        img_array = np.array(img) / 255.0

        # EXPAND DIMS
        img_array = np.expand_dims(
            img_array,
            axis=0
        )

        # PREDICT
        prediction = disease_model.predict(img_array)

        predicted_class = CLASS_NAMES[
            np.argmax(prediction)
        ]

        confidence = float(
            np.max(prediction)
        )
        # SAVE DISEASE SCAN

        conn.execute("""
        INSERT INTO disease_scans
        (image, disease, confidence)
        VALUES (?, ?, ?)
        """, (
            file.filename,
            predicted_class,
            confidence
        ))

        conn.commit()
        return jsonify({
            "disease": predicted_class,
            "confidence": round(confidence, 2),
            "solution": "Apply suitable treatment"
        })

    except Exception as e:

        print("\nERROR INSIDE /api/disease")
        print(str(e))

        return jsonify({
            "error": str(e)
        }), 500

# =========================
# RUN SERVER
# =========================

if __name__ == "__main__":

    app.run(debug=True)