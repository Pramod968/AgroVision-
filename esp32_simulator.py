import requests
import random
import time

SERVER_URL = "http://127.0.0.1:5000/api/sensor"

print("AGROVISION ESP32 SIMULATION STARTED")

while True:

    moisture = random.randint(20, 90)
    temperature = random.randint(25, 35)
    humidity = random.randint(50, 90)

    payload = {
        "moisture": moisture,
        "temperature": temperature,
        "humidity": humidity
    }

    response = requests.post(SERVER_URL, json=payload)

    result = response.json()

    print("\n------ SENSOR VALUES ------")
    print(f"Moisture: {moisture}")
    print(f"Temperature: {temperature}")
    print(f"Humidity: {humidity}")

    print("\n------ ML RESPONSE ------")
    print(f"Irrigate: {result['irrigate']}")
    print(f"Action: {result['action']}")
    print(f"Confidence: {result['confidence']}")

    time.sleep(5)