
# IntelliSense AIoT

## Project Overview
An AIoT-based intelligent sensor fault detection and data recovery system using sensor fusion.

## Features
- Collects temperature and humidity readings from ESP32 sensor nodes.
- Sends sensor readings to a Flask backend over Wi-Fi.
- Stores readings using SQLite.
- Detects suspicious temperature differences.
- Estimates expected readings using historical sensor relationships.
- Displays sensor status and recovery information on a web dashboard.
- Includes a simulator for testing without physical hardware.

## Technology Stack
- ESP32 and DHT11
- C/C++ and PlatformIO
- Python and Flask
- NumPy and SQLite
- HTML, CSS and JavaScript

## Run Locally
1. Install Python.
2. Install dependencies: `pip install -r requirements.txt`
3. Start the backend: `python app.py`
4. Open http://127.0.0.1:5000 in your browser.

## Note
Recovered sensor values are estimates, not guaranteed ground-truth measurements.
