# Realtime Sensor Dashboard (Refactored)

This is a modularized version of the original `squat-app.py` project.

## Structure

```text
refactored_sensor_dashboard/
├── app.py
├── config.py
├── requirements.txt
├── .gitignore
├── core/
├── sensors/
├── services/
├── static/
└── web/
```

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open: `http://localhost:8007`

## What changed

- Split BLE decoding, sensor runners, state management, logging, CSV writing, and web layer into separate modules.
- Moved HTML/CSS/JS out of Python into `web/templates` and `static`.
- Kept behavior close to the original file so the refactor is easier to compare and debug.
