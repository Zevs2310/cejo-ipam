# CEJO — Custom Enterprise IP/Network Orchestrator

> A fully functional BlueCat BAM-compatible IPAM simulator built for ServiceNow ITSM portfolio demonstrations.

![CEJO](https://img.shields.io/badge/CEJO-IPAM%20v2.0-39d0d8?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge)
![Flask](https://img.shields.io/badge/Flask-3.0-green?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge)

---

## Features

- **Hierarchical IPAM**: IP Blocks → Networks → IP Addresses → Devices
- **Device Management**: Computer, Server, Router, Switch, Firewall, Gear, AP
- **MAC Address Generation**: Unique CEJO OUI (C0:EF) MAC addresses
- **REST API**: Full CRUD for blocks, networks, IPs, devices
- **Web Dashboard**: Professional dark-theme UI with live topology tree
- **ServiceNow Integration**: Ready-to-use code for Business Rules, Scripted REST, Flow Designer
- **Docker**: Single-container deployment

---

## Quick Start (Local)

```bash
git clone https://github.com/YOUR_USER/cejo.git
cd cejo
docker-compose up --build
# Open: http://localhost:5000
```

Or without Docker:
```bash
pip install -r requirements.txt
DB_PATH=./cejo.db CEJO_API_KEY=cejo-api-2024 python wsgi.py
```

---

## REST API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/api/v1/status` | Full hierarchy: blocks/networks/devices |
| GET | `/api/v1/summary` | Aggregated stats |
| GET | `/api/v1/blocks` | List all blocks |
| POST | `/api/v1/create_block` | Create IP block |
| GET | `/api/v1/networks` | List all networks |
| POST | `/api/v1/create_network` | Create network in block |
| POST | `/api/v1/add_device` | Add device + allocate IP/MAC |
| POST | `/api/v1/allocate_ip` | Allocate IP to device |
| POST | `/api/v1/release_ip` | Release IP |
| GET | `/api/v1/devices` | List all devices |
| GET | `/api/v1/lookup?ip=` | Lookup by IP/MAC/device |
| GET | `/api/v1/generate_mac` | Generate CEJO MAC |

**Auth header:** `X-CEJO-API-Key: cejo-api-2024`

---

## Deploy to Render.com (Free)

1. Fork this repo to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Runtime: **Docker**
5. Add env var: `CEJO_API_KEY=cejo-api-2024`
6. Click **Deploy** — live in ~2 minutes

---

## ServiceNow Integration

See the **ServiceNow** tab in the web UI, or refer to `/docs/servicenow.md` for:
- Scripted REST API resource code
- Business Rule for auto-allocation on CI creation
- Flow Designer action configuration
- curl test commands

---

## Sample Data

CEJO ships with pre-seeded data:

| Block | CIDR | Networks |
|-------|------|----------|
| Corporate LAN | 10.0.0.0/8 | Servers VLAN-10, Workstations VLAN-20, IoT VLAN-30 |
| Management Fabric | 172.16.0.0/12 | OOB Management |
| DMZ | 192.168.100.0/24 | DMZ Web Tier |

9 pre-allocated devices across all networks.

---

## Tech Stack

- **Backend**: Python 3.12 + Flask 3.0
- **DB**: SQLite (via Python stdlib)
- **Server**: Gunicorn
- **Container**: Docker
- **Frontend**: Vanilla HTML/CSS/JS (no build step)

---

## License

MIT — free to use for portfolio and demo purposes.
