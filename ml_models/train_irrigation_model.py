import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import joblib

# Generate fake dataset
data = []

for i in range(5000):

    moisture = np.random.randint(10, 100)
    temperature = np.random.randint(20, 40)
    humidity = np.random.randint(30, 90)

    irrigate = 1 if moisture < 35 else 0

    data.append([
        moisture,
        temperature,
        humidity,
        irrigate
    ])

df = pd.DataFrame(data, columns=[
    "moisture",
    "temperature",
    "humidity",
    "irrigate"
])

X = df[["moisture", "temperature", "humidity"]]
y = df["irrigate"]

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

model = RandomForestClassifier()
model.fit(X_scaled, y)

joblib.dump(model, "ml_models/irrigation_rf_model.pkl")
joblib.dump(scaler, "ml_models/scaler.pkl")

print("MODEL TRAINED SUCCESSFULLY")