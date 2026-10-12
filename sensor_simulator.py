import requests
import time
import random

API_URL = "http://127.0.0.1:5000/sensor-data"


def send_sensor(sensor_id, temperature, humidity):
    response = requests.post(
        API_URL,
        json={
            "sensor_id": sensor_id,
            "temperature": temperature,
            "humidity": humidity
        }
    )

    print(
        sensor_id,
        "→",
        temperature,
        "°C |",
        response.status_code
    )


print("\n====================================")
print("   IntelliSense AIoT Simulator")
print("====================================\n")


# ==========================================
# PHASE 1 — NORMAL OPERATION
# ==========================================

print("PHASE 1: NORMAL SENSOR OPERATION\n")

for i in range(5):

    s1 = round(
        random.uniform(29.3, 29.8),
        2
    )

    s2 = round(
        s1 + random.uniform(0.4, 0.6),
        2
    )

    send_sensor(
        "S1",
        s1,
        65
    )

    send_sensor(
        "S2",
        s2,
        64
    )

    time.sleep(5)


# ==========================================
# PHASE 2 — SENSOR FAULT
# ==========================================

print("\n====================================")
print("PHASE 2: SENSOR S2 FAULT")
print("====================================\n")

fault_readings = [
    (29.60, 80.0),
    (29.55, 79.5),
    (29.70, 81.0),
    (29.62, 80.5),
    (29.58, 79.8)
]

for s1, s2 in fault_readings:

    send_sensor("S1", s1, 65)
    send_sensor("S2", s2, 65)

    print(
        f"⚠️ S2 abnormal value: {s2}°C"
    )

    time.sleep(2)

print("\n⚠️ Phase 2 fault simulation completed.")


# ==========================================
# PHASE 3 — SENSOR RETURNS TO NORMAL
# ==========================================

print("\n====================================")
print("PHASE 3: SENSOR RETURNS TO NORMAL")
print("====================================\n")

for i in range(5):

    s1 = round(
        random.uniform(29.3, 29.8),
        2
    )

    s2 = round(
        s1 + random.uniform(0.4, 0.6),
        2
    )

    send_sensor(
        "S1",
        s1,
        65
    )

    send_sensor(
        "S2",
        s2,
        64
    )

    time.sleep(5)


print("\n====================================")
print("Simulation completed.")
print("====================================")