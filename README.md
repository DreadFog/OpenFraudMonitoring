# OpenFraudMonitoring

A self-hosted browser fingerprinting and fraud monitoring service. Drop one script tag on any page to start collecting device fingerprints, behavioral signals, and bot detection data — all visible in a live React dashboard.

## Architecture

```
OpenFraudMonitoring/
├── client/                 # Fingerprint script (built with Vite)
│   ├── src/
│   │   ├── index.js        # Entry point
│   │   ├── config.js       # Endpoint config
│   │   ├── helpers.js      # Utilities (safe, now, rnd)
│   │   ├── session.js      # Session ID management
│   │   ├── behavior.js     # Mouse/click/keyboard/copy/navigation tracking
│   │   ├── collect.js      # Assembles and sends initial fingerprint
│   │   ├── heartbeat.js    # Periodic behavioral updates
│   │   ├── deviceid.js     # Device ID generation
│   │   ├── send.js         # Beacon/fetch transport
│   │   └── collectors/     # Individual signal collectors
│   │       ├── navigator.js
│   │       ├── screen.js
│   │       ├── timezone.js
│   │       ├── canvas.js
│   │       ├── webgl.js
│   │       ├── audio.js
│   │       ├── network.js
│   │       ├── storage.js
│   │       ├── botsignals.js
│   │       ├── apis.js
│   │       ├── webrtc.js
│   │       └── ip.js
│   ├── package.json
│   └── vite.config.js
├── backend/                # Python Flask API
│   ├── app.py
│   ├── analysis/           # Risk scoring engine
│   ├── models/             # Session data model
│   ├── routes/             # API blueprints
│   ├── utils/              # Helpers
│   └── requirements.txt
├── frontend/               # React dashboard (Vite)
│   ├── src/
│   │   ├── App.jsx
│   │   ├── Dashboard.jsx
│   │   └── api.js
│   ├── public/
│   │   └── demo.html       # Demo page for testing
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
└── docker-compose.yml
```

## Quick Start (Docker)

```bash
docker compose up --build
```

- Dashboard: http://localhost:3000
- Demo page: http://localhost:3000/demo
- Backend API: http://localhost:5000

## Manual Setup

### Client script

```bash
cd client
npm install
npm run build        # outputs client/dist/fingerprint.js
```

### Backend

```bash
cd backend
pip install -r requirements.txt
python app.py        # runs on :5000
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # runs on :3000, proxies /api/* to :5000
```

## Integration

Add the script to any page you want to monitor:

```html
<script src="http://your-server/fingerprint.js"></script>
```

## What is collected

### On page load (POST /api/collect)

- Hardware: CPU cores, RAM, screen resolution, color depth, pixel ratio
- Canvas 2D fingerprint
- WebGL vendor, renderer, and render fingerprint
- Audio context compressor fingerprint
- Bot/automation signals: WebDriver, Puppeteer, Phantom, Selenium, ChromeDriver cdc_ props
- Browser: user agent, language, platform, OS, device type (mobile/workstation)
- Network: connection type, effective bandwidth
- Storage: localStorage, sessionStorage, IndexedDB availability
- Public IP via ifconfig.me (country, city)
- WebRTC local and public IP leak

### Every 30 seconds (POST /api/heartbeat)

- Mouse movements (up to 300 sampled)
- Clicks
- Key presses (key code + modifiers only)
- Touch events
- Scroll positions
- Copy/paste events (first 100 chars of content)
- URL navigation events

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/collect | Initial fingerprint |
| POST | /api/heartbeat | Behavioral update |
| GET | /api/sessions | All sessions (sorted by risk) |
| GET | /api/sessions/`<device_id>` | Session detail |
| GET | /api/stats | Aggregate statistics |
| GET | /fingerprint.js | Client script |

## Risk Scoring

Scores accumulate up to 100. Key signals:

| Flag | +Score |
|------|--------|
| CHROMEDRIVER_PROPS | 45 |
| WEBDRIVER_DETECTED | 40 |
| PHANTOMJS_DETECTED | 40 |
| SELENIUM_DETECTED | 35 |
| PUPPETEER_DETECTED | 35 |
| NIGHTMARE_DETECTED | 35 |
| NATIVE_SPOOFED | 30 |
| ZERO_SCREEN | 25 |
| EMPTY_LANGUAGES | 20 |
| ZERO_CPU_CORES | 20 |
| OUTER_WIDTH_ZERO_HEADLESS | 20 |
| ZERO_DEVICE_MEMORY | 15 |
| NO_PLUGINS | 15 |
| NO_CANVAS | 10 |
| NO_WEBGL | 10 |

## Security Notes

- Data is in-memory only — lost on restart. Use a database for production.
- No authentication on API endpoints — restrict access in production.
- CORS is open — restrict origins in production.
- Copy/paste content is capped at 100 characters.
- Device ID uses a 32-bit hash — sufficient for tracking but not cryptographically secure.

## License

MIT
