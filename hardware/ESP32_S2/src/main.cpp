#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// ==========================================
// IntelliSense AIoT
// ESP32 Sensor S2
// ==========================================

// ---------- Wi-Fi ----------
const char* WIFI_SSID = "REDACTED";
const char* WIFI_PASSWORD = "REDACTED";

// ---------- Flask Backend ----------
const char* SERVER_URL =
    "http://10.14.172.171:5000/sensor-data";

// ---------- Sensor ----------
#define DHT_PIN 4
#define DHT_TYPE DHT11

DHT dht(DHT_PIN, DHT_TYPE);

// Send data every 5 seconds
const unsigned long SEND_INTERVAL = 5000;

unsigned long lastSendTime = 0;


// ==========================================
// Connect to Wi-Fi
// ==========================================
void connectWiFi() {

    Serial.println();
    Serial.println("Connecting to Wi-Fi...");
    Serial.print("SSID: ");
    Serial.println(WIFI_SSID);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;

    while (WiFi.status() != WL_CONNECTED && attempts < 30) {

        delay(500);
        Serial.print(".");

        attempts++;
    }

    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {

        Serial.println("Wi-Fi connected!");

        Serial.print("ESP32 IP Address: ");
        Serial.println(WiFi.localIP());

    } else {

        Serial.println("Wi-Fi connection failed!");
    }
}


// ==========================================
// Send sensor data to Flask
// ==========================================
void sendSensorData(float temperature, float humidity) {

    if (WiFi.status() != WL_CONNECTED) {

        Serial.println("Wi-Fi disconnected.");
        connectWiFi();

        if (WiFi.status() != WL_CONNECTED) {
            return;
        }
    }

    HTTPClient http;

    http.begin(SERVER_URL);

    http.addHeader("Content-Type", "application/json");

    String jsonData = "{";
    jsonData += "\"sensor_id\":\"S2\",";
    jsonData += "\"temperature\":" + String(temperature, 2) + ",";
    jsonData += "\"humidity\":" + String(humidity, 2);
    jsonData += "}";

    Serial.println();
    Serial.println("Sending S2 data...");
    Serial.println(jsonData);

    int responseCode = http.POST(jsonData);

    Serial.print("HTTP Response Code: ");
    Serial.println(responseCode);

    if (responseCode > 0) {

        String response = http.getString();

        Serial.println("Flask Response:");
        Serial.println(response);

    } else {

        Serial.print("HTTP Error: ");
        Serial.println(http.errorToString(responseCode));
    }

    http.end();
}


// ==========================================
// SETUP
// ==========================================
void setup() {

    Serial.begin(115200);

    delay(1000);

    Serial.println();
    Serial.println("======================================");
    Serial.println("     IntelliSense AIoT - SENSOR S2");
    Serial.println("======================================");

    // Start DHT11
    dht.begin();

    Serial.println("DHT11 initialized.");

    // Connect Wi-Fi
    connectWiFi();
}


// ==========================================
// LOOP
// ==========================================
void loop() {

    unsigned long currentTime = millis();

    if (currentTime - lastSendTime >= SEND_INTERVAL) {

        lastSendTime = currentTime;

        float humidity = dht.readHumidity();
        float temperature = dht.readTemperature();

        // Check DHT11 reading
        if (isnan(humidity) || isnan(temperature)) {

            Serial.println();
            Serial.println("ERROR: Failed to read DHT11.");

            return;
        }

        // Display sensor data
        Serial.println();
        Serial.println("--------------------------------------");
        Serial.println("SENSOR S2 READING");
        Serial.println("--------------------------------------");

        Serial.print("Temperature: ");
        Serial.print(temperature);
        Serial.println(" °C");

        Serial.print("Humidity: ");
        Serial.print(humidity);
        Serial.println(" %");

        // Send data to Flask
        sendSensorData(temperature, humidity);
    }
}