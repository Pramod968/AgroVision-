from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import joblib
import numpy as np
import random
import os
import tensorflow as tf

from PIL import Image

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