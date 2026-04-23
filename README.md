 Realtime Sensor Dashboard

A Python-based realtime dashboard for streaming, visualizing, and logging data from:

- **Polar sensor** for heart rate and accelerometer data
- **Flexible1** and **Flexible2** BLE sensors for acceleration, gyroscope, bend/stretch, and 2-axis angle data

The app uses **FastAPI**, **WebSocket**, **Bleak**, and a browser-based dashboard rendered from a built-in HTML page.

---

## Features

- Connects to **3 BLE data sources** at the same time
- Streams live data through **WebSocket**
- Shows realtime metrics for:
  - Polar accelerometer
  - Flexible1 accelerometer, gyroscope, angle, gesture
  - Flexible2 accelerometer, gyroscope, angle, gesture
- Detects gestures such as:
  - `UP`, `DOWN`, `LEFT`, `RIGHT`
  - `UP-LEFT`, `UP-RIGHT`, `DOWN-LEFT`, `DOWN-RIGHT`
  - `CENTER`
- Saves synchronized sensor rows to **CSV**
- Keeps short rolling history for live charts
- Retries BLE reconnection automatically when a device disconnects

---

## Tech Stack

- Python
- FastAPI
- WebSocket
- Bleak
- Uvicorn
- HTML + CSS + Vanilla JavaScript

---

## Project Structure

Current version is a **single-file prototype**:

```text
squat-app.py
```

Main logical sections inside the file:

1. **Configuration**
   - BLE addresses
   - UUIDs
   - thresholds
   - timing constants

2. **Shared State**
   - latest sensor values
   - connection status
   - chart history
   - log buffer

3. **Helpers**
   - CSV initialization/writing
   - logging
   - angle calculation
   - gesture detection
   - history append

4. **BLE Data Processing**
   - Flexible packet decode
   - Polar HR/ACC handlers
   - safe BLE command writes
   - stream startup logic

5. **Async Tasks**
   - `run_flexible()`
   - `run_polar()`
   - `state_loop()`

6. **Web App**
   - FastAPI routes
   - WebSocket endpoint
   - embedded HTML dashboard

---

## How It Works

### 1) Flexible sensors
Each Flexible device connects over BLE and subscribes to the data characteristic.

After connection:
- the app sends control commands to start streaming
- incoming packets are decoded with `struct.unpack`
- raw values are converted into readable units
- axis calibration is applied
- angles are derived from `ads2_x` and `ads2_y`
- gesture labels are inferred from angle thresholds
- rolling chart history is updated

### 2) Polar sensor
The Polar device provides:
- heart rate notifications
- accelerometer notifications

The accelerometer values are converted from **mg to g** and pushed into a queue for processing.

### 3) State loop
The `state_loop()` coroutine acts as the central orchestrator:
- fetches latest data from buffers/queues
- updates the global dashboard state
- computes gestures
- appends chart history
- writes synchronized CSV rows
- broadcasts JSON to all WebSocket clients

### 4) Browser dashboard
The browser connects to `/ws`, receives JSON, then:
- updates sensor status cards
- updates metric values
- redraws line charts on `<canvas>`
- refreshes the live log

---

## Key Functions

### `decode_packet(data)`
Decodes a Flexible BLE packet and converts it into a list of sensor samples.

It extracts:
- accelerometer
- gyroscope
- bend/stretch
- 2-axis angle channels

### `detect_gesture(angle_x, angle_y)`
Maps angle thresholds to symbolic directions like `LEFT`, `UP-RIGHT`, or `CENTER`.

### `update_smoothed_gesture(name, angle_x, angle_y)`
Uses a short rolling window to reduce noisy gesture flickering.

### `run_flexible(name, addr)`
Maintains connection to one Flexible device, subscribes to notifications, starts the stream, and auto-retries on disconnect.

### `run_polar()`
Maintains connection to the Polar device and starts heart-rate / accelerometer notifications.

### `state_loop()`
The core pipeline that combines sensor input, updates state, logs data, and pushes updates to the frontend.

---

## CSV Logging

The app creates a CSV file named like:

```text
sensor_data_YYYYMMDD_HHMMSS.csv
```

Rows are saved only when all three sensor sources have usable data:
- Polar
- Flexible1
- Flexible2

This helps keep the CSV synchronized instead of mixing partial rows.

---

## Run Locally

## 1. Install dependencies

```bash
pip install fastapi uvicorn bleak
```

## 2. Start the app

```bash
python squat-app.py
```

## 3. Open the dashboard

```text
http://localhost:8007
```

---

## Notes

- BLE device addresses are hardcoded in the file.
- UUIDs are hardcoded for the current hardware setup.
- The dashboard HTML is embedded directly in Python.
- This version is good for demo/prototype use, but it should be split into modules for maintainability.

---

## Suggested Next Refactor

A cleaner production layout could look like this:

```text
project/
├─ app.py
├─ sensors/
│  ├─ flexible.py
│  ├─ polar.py
│  └─ decoder.py
├─ services/
│  ├─ state.py
│  ├─ logging_service.py
│  └─ csv_writer.py
├─ web/
│  ├─ routes.py
│  ├─ websocket.py
│  └─ templates/
│     └─ index.html
├─ static/
│  ├─ styles.css
│  └─ dashboard.js
├─ requirements.txt
└─ README.md
```

---

🌐 Live Demo

You can access the realtime dashboard here:

👉 https://unstamped-childless-cogwheel.ngrok-free.dev/

⚠️ This demo is served via ngrok and may go offline if the tunnel is restarted.

💡 Notes about the demo
The dashboard streams live sensor data (not mock data)
If the page shows no data:
Sensors may not be connected
Backend may not be running
ngrok tunnel may have expired

Add your preferred license here.
