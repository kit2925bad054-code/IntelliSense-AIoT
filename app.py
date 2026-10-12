from flask import Flask, request, jsonify, render_template
import sqlite3
import numpy as np

app = Flask(__name__)

DB_NAME = "sensor_data.db"

# Difference above this value is considered abnormal
ANOMALY_THRESHOLD = 5.0


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():

    conn = get_db_connection()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # SENSOR READINGS TABLE
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT NOT NULL,
            temperature REAL NOT NULL,
            humidity REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --------------------------------------------------------
    # CHECK OLD RECOVERY EVENTS TABLE
    # --------------------------------------------------------

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name='recovery_events'
    """)

    recovery_table_exists = cursor.fetchone() is not None

    rebuild_recovery_table = False

    if recovery_table_exists:

        cursor.execute("PRAGMA table_info(recovery_events)")
        columns = [row["name"] for row in cursor.fetchall()]

        # Old version does not contain sensor_reading_id
        if "sensor_reading_id" not in columns:
            rebuild_recovery_table = True

    else:
        rebuild_recovery_table = True

    # --------------------------------------------------------
    # REMOVE OLD RECOVERY TABLE ONLY WHEN NECESSARY
    # --------------------------------------------------------

    if rebuild_recovery_table:

        cursor.execute("DROP TABLE IF EXISTS recovery_events")

        cursor.execute("""
            CREATE TABLE recovery_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                sensor_reading_id INTEGER NOT NULL UNIQUE,

                sensor_id TEXT NOT NULL,

                original_temperature REAL NOT NULL,

                expected_temperature REAL NOT NULL,

                recovered_temperature REAL NOT NULL,

                difference REAL NOT NULL,

                status TEXT NOT NULL,

                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

    else:

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                sensor_reading_id INTEGER NOT NULL UNIQUE,

                sensor_id TEXT NOT NULL,

                original_temperature REAL NOT NULL,

                expected_temperature REAL NOT NULL,

                recovered_temperature REAL NOT NULL,

                difference REAL NOT NULL,

                status TEXT NOT NULL,

                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # Extra protection against duplicate source readings
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_recovery_source_reading
        ON recovery_events(sensor_reading_id)
    """)

    conn.commit()
    conn.close()

    # --------------------------------------------------------
    # REBUILD RECOVERY EVENTS FROM EXISTING SENSOR HISTORY
    # --------------------------------------------------------

    if rebuild_recovery_table:
        backfill_recovery_events()


# ============================================================
# GET HISTORICAL SENSOR PAIRS
# ============================================================

def get_historical_pairs_with_ids():

    conn = get_db_connection()

    rows = conn.execute("""
        SELECT
            id,
            sensor_id,
            temperature,
            timestamp
        FROM sensor_readings
        WHERE sensor_id IN ('S1', 'S2')
        ORDER BY id ASC
    """).fetchall()

    conn.close()

    s1_data = []
    s2_data = []

    for row in rows:

        if row["sensor_id"] == "S1":

            s1_data.append({
                "id": row["id"],
                "temperature": row["temperature"],
                "timestamp": row["timestamp"]
            })

        elif row["sensor_id"] == "S2":

            s2_data.append({
                "id": row["id"],
                "temperature": row["temperature"],
                "timestamp": row["timestamp"]
            })

    pair_count = min(len(s1_data), len(s2_data))

    pairs = []

    for i in range(pair_count):

        pairs.append({
            "s1_id": s1_data[i]["id"],
            "s1_temperature": s1_data[i]["temperature"],
            "s1_timestamp": s1_data[i]["timestamp"],

            "s2_id": s2_data[i]["id"],
            "s2_temperature": s2_data[i]["temperature"],
            "s2_timestamp": s2_data[i]["timestamp"]
        })

    return pairs


# ============================================================
# LEARN SENSOR RELATIONSHIP
# ============================================================

def learn_sensor_relationship():

    pairs = get_historical_pairs_with_ids()

    if len(pairs) < 3:

        return {
            "success": False,
            "message": "Not enough historical data"
        }

    normal_pairs = []

    for pair in pairs:

        s1_temperature = pair["s1_temperature"]
        s2_temperature = pair["s2_temperature"]

        difference = abs(s2_temperature - s1_temperature)

        if difference <= ANOMALY_THRESHOLD:

            normal_pairs.append(
                (s1_temperature, s2_temperature)
            )

    if len(normal_pairs) < 3:

        return {
            "success": False,
            "message": "Not enough normal historical data"
        }

    x = np.array(
        [pair[0] for pair in normal_pairs],
        dtype=float
    )

    y = np.array(
        [pair[1] for pair in normal_pairs],
        dtype=float
    )

    try:

        slope, intercept = np.polyfit(x, y, 1)

    except Exception as error:

        return {
            "success": False,
            "message": str(error)
        }

    return {
        "success": True,
        "slope": float(slope),
        "intercept": float(intercept),
        "training_samples": len(normal_pairs)
    }


# ============================================================
# SAVE RECOVERY EVENT
# ============================================================

def save_recovery_event(
    sensor_reading_id,
    sensor_id,
    original_temperature,
    expected_temperature,
    recovered_temperature,
    difference,
    status,
    timestamp
):

    conn = get_db_connection()

    conn.execute("""
        INSERT OR IGNORE INTO recovery_events (
            sensor_reading_id,
            sensor_id,
            original_temperature,
            expected_temperature,
            recovered_temperature,
            difference,
            status,
            timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sensor_reading_id,
        sensor_id,
        original_temperature,
        expected_temperature,
        recovered_temperature,
        difference,
        status,
        timestamp
    ))

    conn.commit()
    conn.close()


# ============================================================
# ANALYZE A NEW S2 READING
# ============================================================

def analyze_s2_reading(reading_id, temperature):

    conn = get_db_connection()

    # Find the most recent S1 reading before this S2 reading
    s1_row = conn.execute("""
        SELECT
            id,
            temperature,
            timestamp
        FROM sensor_readings
        WHERE sensor_id = 'S1'
        AND id < ?
        ORDER BY id DESC
        LIMIT 1
    """, (reading_id,)).fetchone()

    # Get the S2 timestamp
    s2_row = conn.execute("""
        SELECT timestamp
        FROM sensor_readings
        WHERE id = ?
    """, (reading_id,)).fetchone()

    conn.close()

    if s1_row is None:

        return {
            "status": "normal",
            "message": "No matching S1 reading found"
        }

    model = learn_sensor_relationship()

    if not model["success"]:

        return {
            "status": "normal",
            "message": model["message"]
        }

    s1_temperature = float(s1_row["temperature"])

    slope = model["slope"]
    intercept = model["intercept"]

    expected_temperature = (
        slope * s1_temperature
        + intercept
    )

    difference = abs(
        temperature - expected_temperature
    )

    # --------------------------------------------------------
    # NORMAL
    # --------------------------------------------------------

    if difference <= ANOMALY_THRESHOLD:

        return {
            "status": "normal",
            "sensor_id": "S2",
            "original_temperature": temperature,
            "expected_temperature": round(
                expected_temperature, 2
            ),
            "difference": round(
                difference, 2
            )
        }

    # --------------------------------------------------------
    # FAULT DETECTED
    # --------------------------------------------------------

    recovered_temperature = expected_temperature

    save_recovery_event(
        sensor_reading_id=reading_id,
        sensor_id="S2",
        original_temperature=temperature,
        expected_temperature=recovered_temperature,
        recovered_temperature=recovered_temperature,
        difference=difference,
        status="RECOVERED",
        timestamp=s2_row["timestamp"]
    )

    return {
        "status": "recovered",

        "sensor_id": "S2",

        "faulty_sensor": "S2",

        "original_temperature": round(
            temperature, 2
        ),

        "expected_temperature": round(
            expected_temperature, 2
        ),

        "recovered_temperature": round(
            recovered_temperature, 2
        ),

        "difference": round(
            difference, 2
        ),

        "method": "Linear Regression + Sensor Fusion",

        "slope": round(
            slope, 4
        ),

        "intercept": round(
            intercept, 4
        ),

        "training_samples":
            model["training_samples"]
    }


# ============================================================
# BACKFILL OLD SENSOR HISTORY
# ============================================================

def backfill_recovery_events():

    pairs = get_historical_pairs_with_ids()

    if len(pairs) < 3:
        return

    # --------------------------------------------------------
    # Build model using normal historical readings
    # --------------------------------------------------------

    normal_pairs = []

    for pair in pairs:

        difference = abs(
            pair["s2_temperature"]
            - pair["s1_temperature"]
        )

        if difference <= ANOMALY_THRESHOLD:

            normal_pairs.append(
                (
                    pair["s1_temperature"],
                    pair["s2_temperature"]
                )
            )

    if len(normal_pairs) < 3:
        return

    x = np.array(
        [item[0] for item in normal_pairs],
        dtype=float
    )

    y = np.array(
        [item[1] for item in normal_pairs],
        dtype=float
    )

    try:

        slope, intercept = np.polyfit(x, y, 1)

    except Exception:

        return

    # --------------------------------------------------------
    # Detect old fault readings
    # --------------------------------------------------------

    for pair in pairs:

        expected_temperature = (
            slope * pair["s1_temperature"]
            + intercept
        )

        difference = abs(
            pair["s2_temperature"]
            - expected_temperature
        )

        if difference > ANOMALY_THRESHOLD:

            save_recovery_event(

                sensor_reading_id=pair["s2_id"],

                sensor_id="S2",

                original_temperature=
                    pair["s2_temperature"],

                expected_temperature=
                    expected_temperature,

                recovered_temperature=
                    expected_temperature,

                difference=
                    difference,

                status="RECOVERED",

                timestamp=
                    pair["s2_timestamp"]
            )


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# RECEIVE SENSOR DATA
# ============================================================

@app.route("/sensor-data", methods=["POST"])
def receive_sensor_data():

    try:

        data = request.get_json()

        if not data:

            return jsonify({
                "status": "error",
                "message": "No JSON data received"
            }), 400

        sensor_id = data.get("sensor_id")
        temperature = data.get("temperature")
        humidity = data.get("humidity")

        if sensor_id is None:
            return jsonify({
                "status": "error",
                "message": "sensor_id is required"
            }), 400

        if temperature is None:
            return jsonify({
                "status": "error",
                "message": "temperature is required"
            }), 400

        temperature = float(temperature)

        if humidity is not None:
            humidity = float(humidity)

        # ----------------------------------------------------
        # INSERT SENSOR READING
        # ----------------------------------------------------

        conn = get_db_connection()

        cursor = conn.execute("""
            INSERT INTO sensor_readings (
                sensor_id,
                temperature,
                humidity
            )
            VALUES (?, ?, ?)
        """, (
            sensor_id,
            temperature,
            humidity
        ))

        reading_id = cursor.lastrowid

        # Get timestamp assigned by SQLite
        row = conn.execute("""
            SELECT timestamp
            FROM sensor_readings
            WHERE id = ?
        """, (reading_id,)).fetchone()

        timestamp = row["timestamp"]

        conn.commit()
        conn.close()

        # ----------------------------------------------------
        # IMPORTANT:
        # Analyze ONLY when S2 reading arrives.
        #
        # This prevents dashboard polling from creating
        # duplicate recovery events.
        # ----------------------------------------------------

        recovery_result = None

        if sensor_id == "S2":

            recovery_result = analyze_s2_reading(
                reading_id,
                temperature
            )

        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        response = {
            "status": "success",

            "message": "Sensor data received",

            "reading_id": reading_id,

            "sensor_id": sensor_id,

            "temperature": temperature,

            "humidity": humidity,

            "timestamp": timestamp
        }

        if recovery_result:

            response["recovery"] = recovery_result

        return jsonify(response)

    except Exception as error:

        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


# ============================================================
# DATA RECOVERY API
# ============================================================

@app.route("/api/data-recovery", methods=["GET"])
def data_recovery():

    try:

        conn = get_db_connection()

        s1 = conn.execute("""
            SELECT
                id,
                temperature,
                timestamp
            FROM sensor_readings
            WHERE sensor_id = 'S1'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        s2 = conn.execute("""
            SELECT
                id,
                temperature,
                timestamp
            FROM sensor_readings
            WHERE sensor_id = 'S2'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        conn.close()

        if s1 is None or s2 is None:

            return jsonify({
                "status": "waiting",
                "message": "Waiting for sensor data"
            })

        model = learn_sensor_relationship()

        if not model["success"]:

            return jsonify({
                "status": "waiting",
                "message": model["message"]
            })

        slope = model["slope"]
        intercept = model["intercept"]

        expected_temperature = (
            slope * s1["temperature"]
            + intercept
        )

        difference = abs(
            s2["temperature"]
            - expected_temperature
        )

        # ----------------------------------------------------
        # NORMAL
        # ----------------------------------------------------

        if difference <= ANOMALY_THRESHOLD:

            return jsonify({

                "status": "normal",

                "sensor_id": "S2",

                "original_temperature":
                    round(s2["temperature"], 2),

                "expected_temperature":
                    round(expected_temperature, 2),

                "recovered_temperature":
                    None,

                "difference":
                    round(difference, 2),

                "method":
                    "Linear Regression + Sensor Fusion",

                "training_samples":
                    model["training_samples"],

                "slope":
                    round(slope, 4),

                "intercept":
                    round(intercept, 4)
            })

        # ----------------------------------------------------
        # FAULT / RECOVERY
        # ----------------------------------------------------

        return jsonify({

            "status": "recovered",

            "faulty_sensor": "S2",

            "sensor_id": "S2",

            "original_temperature":
                round(s2["temperature"], 2),

            "expected_temperature":
                round(expected_temperature, 2),

            "recovered_temperature":
                round(expected_temperature, 2),

            "difference":
                round(difference, 2),

            "method":
                "Linear Regression + Sensor Fusion",

            "training_samples":
                model["training_samples"],

            "slope":
                round(slope, 4),

            "intercept":
                round(intercept, 4)
        })

    except Exception as error:

        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


# ============================================================
# LATEST SENSOR DATA
# ============================================================

@app.route("/api/latest", methods=["GET"])
def latest_data():

    try:

        conn = get_db_connection()

        sensors = {}

        rows = conn.execute("""
            SELECT
                sensor_id,
                temperature,
                humidity,
                timestamp
            FROM sensor_readings
            WHERE id IN (
                SELECT MAX(id)
                FROM sensor_readings
                GROUP BY sensor_id
            )
        """).fetchall()

        conn.close()

        for row in rows:

            sensors[row["sensor_id"]] = {
                "temperature":
                    row["temperature"],

                "humidity":
                    row["humidity"],

                "timestamp":
                    row["timestamp"]
            }

        return jsonify({
            "status": "success",
            "sensors": sensors
        })

    except Exception as error:

        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


# ============================================================
# SENSOR HISTORY API
# ============================================================

@app.route("/api/history", methods=["GET"])
def history():

    try:

        limit = request.args.get(
            "limit",
            default=50,
            type=int
        )

        if limit <= 0:
            limit = 50

        if limit > 500:
            limit = 500

        conn = get_db_connection()

        rows = conn.execute("""
            SELECT
                id,
                sensor_id,
                temperature,
                humidity,
                timestamp
            FROM sensor_readings
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        conn.close()

        history_data = []

        for row in reversed(rows):

            history_data.append({

                "id":
                    row["id"],

                "sensor_id":
                    row["sensor_id"],

                "temperature":
                    row["temperature"],

                "humidity":
                    row["humidity"],

                "timestamp":
                    row["timestamp"]
            })

        return jsonify({

            "status": "success",

            "count":
                len(history_data),

            "data":
                history_data
        })

    except Exception as error:

        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


# ============================================================
# RECOVERY HISTORY API
# ============================================================

@app.route("/api/recovery-history", methods=["GET"])
def recovery_history():

    try:

        limit = request.args.get(
            "limit",
            default=50,
            type=int
        )

        if limit <= 0:
            limit = 50

        if limit > 500:
            limit = 500

        conn = get_db_connection()

        rows = conn.execute("""
            SELECT
                id,
                sensor_reading_id,
                sensor_id,
                original_temperature,
                expected_temperature,
                recovered_temperature,
                difference,
                status,
                timestamp
            FROM recovery_events
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        conn.close()

        events = []

        for row in rows:

            events.append({

                "id":
                    row["id"],

                "sensor_reading_id":
                    row["sensor_reading_id"],

                "sensor_id":
                    row["sensor_id"],

                "original_temperature":
                    round(
                        row["original_temperature"],
                        2
                    ),

                "expected_temperature":
                    round(
                        row["expected_temperature"],
                        2
                    ),

                "recovered_temperature":
                    round(
                        row["recovered_temperature"],
                        2
                    ),

                "difference":
                    round(
                        row["difference"],
                        2
                    ),

                "status":
                    row["status"],

                "timestamp":
                    row["timestamp"]
            })

        return jsonify({

            "status": "success",

            "count":
                len(events),

            "events":
                events
        })

    except Exception as error:

        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    initialize_database()

    print("")
    print("==============================================")
    print("       IntelliSense AIoT")
    print("==============================================")
    print("AIoT-Based Intelligent Sensor Fault Detection")
    print("and Data Recovery Using Sensor Fusion")
    print("==============================================")
    print("")
    print("Server running at:")
    print("http://127.0.0.1:5000")
    print("")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )