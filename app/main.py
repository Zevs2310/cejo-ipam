"""
CEJO — Custom Enterprise IP/Network Orchestrator
Full hierarchical IPAM simulator (BlueCat BAM-compatible)
Author: CEJO Project
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import ipaddress
import random
import sqlite3
import os
import functools
from datetime import datetime

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)

DB_PATH  = os.environ.get('DB_PATH', '/tmp/cejo.db')
API_KEY  = os.environ.get('CEJO_API_KEY', 'cejo-api-2024')

DEVICE_TYPES = {'Computer', 'Router', 'Switch', 'Gear', 'Server', 'Firewall', 'AP'}

# ─── Database ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS blocks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            cidr        TEXT NOT NULL UNIQUE,
            description TEXT,
            location    TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS networks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id    INTEGER NOT NULL,
            name        TEXT NOT NULL,
            cidr        TEXT NOT NULL UNIQUE,
            gateway     TEXT,
            vlan_id     INTEGER,
            description TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ip_addresses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            network_id   INTEGER NOT NULL,
            ip           TEXT NOT NULL UNIQUE,
            status       TEXT DEFAULT 'available',
            FOREIGN KEY (network_id) REFERENCES networks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS devices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            network_id   INTEGER NOT NULL,
            ip_id        INTEGER UNIQUE,
            name         TEXT NOT NULL,
            device_type  TEXT NOT NULL DEFAULT 'Computer',
            mac_address  TEXT UNIQUE,
            owner        TEXT,
            description  TEXT,
            status       TEXT DEFAULT 'active',
            allocated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (network_id) REFERENCES networks(id),
            FOREIGN KEY (ip_id) REFERENCES ip_addresses(id)
        );
    ''')
    conn.commit()
    _seed(conn)
    conn.close()

def _seed(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM blocks")
    if c.fetchone()[0] > 0:
        return

    # ── Seed Blocks ───────────────────────────────────────────────────────────
    blocks = [
        (1, 'Corporate LAN',     '10.0.0.0/8',     'Main corporate address space', 'HQ-Belgrade'),
        (2, 'Management Fabric', '172.16.0.0/12',   'OOB management network',       'DataCenter-1'),
        (3, 'DMZ',               '192.168.100.0/24','Demilitarized zone',            'Edge'),
    ]
    for b in blocks:
        c.execute("INSERT OR IGNORE INTO blocks (id,name,cidr,description,location) VALUES (?,?,?,?,?)", b)

    # ── Seed Networks ──────────────────────────────────────────────────────────
    networks = [
        (1, 1, 'Servers VLAN-10',    '10.0.10.0/24',  '10.0.10.1',   10,  'Production servers'),
        (2, 1, 'Workstations VLAN-20','10.0.20.0/24', '10.0.20.1',   20,  'Office workstations'),
        (3, 1, 'IoT VLAN-30',        '10.0.30.0/28',  '10.0.30.1',   30,  'IoT devices'),
        (4, 2, 'OOB Management',     '172.16.1.0/24', '172.16.1.1',  100, 'Out-of-band mgmt'),
        (5, 3, 'DMZ Web Tier',       '192.168.100.0/28','192.168.100.1',200,'Public-facing web'),
    ]
    for n in networks:
        nid, bid, name, cidr, gw, vlan, desc = n
        c.execute("INSERT OR IGNORE INTO networks (id,block_id,name,cidr,gateway,vlan_id,description) VALUES (?,?,?,?,?,?,?)",
                  (nid, bid, name, cidr, gw, vlan, desc))
        net = ipaddress.IPv4Network(cidr, strict=False)
        for host in net.hosts():
            ip = str(host)
            status = 'reserved' if ip == gw else 'available'
            c.execute("INSERT OR IGNORE INTO ip_addresses (network_id,ip,status) VALUES (?,?,?)",
                      (nid, ip, status))

    conn.commit()

    # ── Seed Devices ──────────────────────────────────────────────────────────
    seed_devices = [
        # net_id, ip, name, type, owner, desc
        (1, '10.0.10.10',  'cejo-dc01',      'Server',   'IT-Ops',   'Domain Controller'),
        (1, '10.0.10.11',  'cejo-app01',     'Server',   'DevOps',   'Application Server'),
        (1, '10.0.10.12',  'cejo-db01',      'Server',   'DBA',      'PostgreSQL Primary'),
        (2, '10.0.20.10',  'ws-markoi-pc',   'Computer', 'IT-Ops',   'Admin Workstation'),
        (2, '10.0.20.11',  'ws-laptop-01',   'Computer', 'HR',       'HR Laptop'),
        (3, '10.0.30.2',   'iot-sensor-01',  'Gear',     'IoT-Team', 'Temperature Sensor'),
        (4, '172.16.1.10', 'sw-core-01',     'Switch',   'NetOps',   'Core L3 Switch'),
        (4, '172.16.1.11', 'rtr-edge-01',    'Router',   'NetOps',   'Edge Router'),
        (5, '192.168.100.2','fw-dmz-01',     'Firewall', 'SecOps',   'DMZ Firewall'),
    ]
    for net_id, ip, dname, dtype, owner, desc in seed_devices:
        ip_row = conn.execute("SELECT id FROM ip_addresses WHERE ip=?", (ip,)).fetchone()
        if not ip_row:
            continue
        mac = _gen_mac(conn)
        conn.execute(
            "UPDATE ip_addresses SET status='allocated' WHERE id=?", (ip_row['id'],))
        conn.execute(
            "INSERT OR IGNORE INTO devices (network_id,ip_id,name,device_type,mac_address,owner,description) VALUES (?,?,?,?,?,?,?)",
            (net_id, ip_row['id'], dname, dtype, mac, owner, desc))

    conn.commit()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _gen_mac(conn):
    """Generate unique CEJO OUI MAC (CE:J0:00 → C0:EF:00)"""
    for _ in range(200):
        mac = "C0:EF:{:02X}:{:02X}:{:02X}:{:02X}".format(
            random.randint(0,255), random.randint(0,255),
            random.randint(0,255), random.randint(0,255))
        if not conn.execute("SELECT 1 FROM devices WHERE mac_address=?", (mac,)).fetchone():
            return mac
    raise RuntimeError("MAC exhausted")

def _require_key(f):
    @functools.wraps(f)
    def wrap(*a, **kw):
        k = request.headers.get('X-CEJO-API-Key') or request.args.get('api_key')
        if k != API_KEY:
            return jsonify({"error": "Unauthorized", "hint": "Header: X-CEJO-API-Key"}), 401
        return f(*a, **kw)
    return wrap

def _net_stats(conn, net_id):
    rows = conn.execute(
        "SELECT status, COUNT(*) c FROM ip_addresses WHERE network_id=? GROUP BY status",
        (net_id,)).fetchall()
    s = {'available':0,'allocated':0,'reserved':0}
    for r in rows: s[r['status']] = r['c']
    s['total'] = sum(s.values())
    s['utilization_pct'] = round(
        (s['allocated'] + s['reserved']) / s['total'] * 100, 1) if s['total'] else 0
    return s

def _ts():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

# ─── UI ───────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', api_key=API_KEY)

# ─── Health ───────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "CEJO IPAM", "version": "2.0.0",
                    "timestamp": _ts()})

# ─── /status ──────────────────────────────────────────────────────────────────

@app.route('/api/v1/status', methods=['GET'])
@_require_key
def status():
    conn = get_db()
    blocks = conn.execute("SELECT * FROM blocks ORDER BY id").fetchall()
    result = []
    for b in blocks:
        networks = conn.execute(
            "SELECT * FROM networks WHERE block_id=? ORDER BY id", (b['id'],)).fetchall()
        nets_out = []
        for n in networks:
            stats = _net_stats(conn, n['id'])
            devs = conn.execute(
                """SELECT d.name, d.device_type, d.mac_address, d.owner, d.description,
                          d.status, d.allocated_at, i.ip, i.status as ip_status
                   FROM devices d
                   JOIN ip_addresses i ON d.ip_id = i.id
                   WHERE d.network_id=? ORDER BY i.ip""",
                (n['id'],)).fetchall()
            nets_out.append({
                "id": n['id'], "name": n['name'], "cidr": n['cidr'],
                "gateway": n['gateway'], "vlan_id": n['vlan_id'],
                "description": n['description'], "stats": stats,
                "devices": [dict(d) for d in devs]
            })
        result.append({
            "id": b['id'], "name": b['name'], "cidr": b['cidr'],
            "description": b['description'], "location": b['location'],
            "networks": nets_out
        })
    conn.close()
    return jsonify({"cejo": "IPAM Status", "timestamp": _ts(), "blocks": result})

# ─── /create_block ────────────────────────────────────────────────────────────

@app.route('/api/v1/create_block', methods=['POST'])
@_require_key
def create_block():
    d = request.get_json(force=True) or {}
    name = d.get('name'); cidr = d.get('cidr')
    if not name or not cidr:
        return jsonify({"error": "name and cidr required"}), 400
    try: ipaddress.IPv4Network(cidr, strict=False)
    except ValueError as e: return jsonify({"error": str(e)}), 400

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO blocks (name,cidr,description,location) VALUES (?,?,?,?)",
            (name, cidr, d.get('description',''), d.get('location','')))
        conn.commit()
        bid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": f"Block {cidr} already exists"}), 409
    conn.close()
    return jsonify({"status": "created", "block_id": bid, "name": name, "cidr": cidr}), 201

# ─── /create_network ──────────────────────────────────────────────────────────

@app.route('/api/v1/create_network', methods=['POST'])
@_require_key
def create_network():
    d = request.get_json(force=True) or {}
    block_cidr = d.get('block_cidr'); name = d.get('name'); cidr = d.get('cidr')
    if not block_cidr or not name or not cidr:
        return jsonify({"error": "block_cidr, name, cidr required"}), 400

    try:
        net = ipaddress.IPv4Network(cidr, strict=False)
        block_net = ipaddress.IPv4Network(block_cidr, strict=False)
        if not net.subnet_of(block_net):
            return jsonify({"error": f"{cidr} is not within block {block_cidr}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db()
    block = conn.execute("SELECT * FROM blocks WHERE cidr=?", (block_cidr,)).fetchone()
    if not block:
        conn.close()
        return jsonify({"error": f"Block {block_cidr} not found"}), 404

    gw = d.get('gateway', str(list(net.hosts())[0]))

    try:
        conn.execute(
            "INSERT INTO networks (block_id,name,cidr,gateway,vlan_id,description) VALUES (?,?,?,?,?,?)",
            (block['id'], name, str(net), gw, d.get('vlan_id'), d.get('description','')))
        conn.commit()
        nid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for host in net.hosts():
            ip = str(host)
            status = 'reserved' if ip == gw else 'available'
            conn.execute("INSERT OR IGNORE INTO ip_addresses (network_id,ip,status) VALUES (?,?,?)",
                         (nid, ip, status))
        conn.commit()
        stats = _net_stats(conn, nid)
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": f"Network {cidr} already exists"}), 409

    conn.close()
    return jsonify({"status": "created", "network_id": nid, "cidr": str(net),
                    "gateway": gw, "stats": stats}), 201

# ─── /add_device ──────────────────────────────────────────────────────────────

@app.route('/api/v1/add_device', methods=['POST'])
@_require_key
def add_device():
    """Add a device to a network and auto-allocate or use specific IP."""
    d = request.get_json(force=True) or {}
    network_cidr = d.get('network_cidr')
    name         = d.get('name')
    device_type  = d.get('device_type', 'Computer')
    specific_ip  = d.get('ip')
    custom_mac   = d.get('mac_address')

    if not network_cidr or not name:
        return jsonify({"error": "network_cidr and name required"}), 400
    if device_type not in DEVICE_TYPES:
        return jsonify({"error": f"device_type must be one of {sorted(DEVICE_TYPES)}"}), 400

    conn = get_db()
    net = conn.execute("SELECT * FROM networks WHERE cidr=?", (network_cidr,)).fetchone()
    if not net:
        conn.close()
        return jsonify({"error": f"Network {network_cidr} not found"}), 404

    # Check duplicate device name in network
    if conn.execute("SELECT 1 FROM devices WHERE network_id=? AND name=?",
                    (net['id'], name)).fetchone():
        conn.close()
        return jsonify({"error": f"Device '{name}' already exists in {network_cidr}"}), 409

    if custom_mac and conn.execute("SELECT 1 FROM devices WHERE mac_address=?",
                                   (custom_mac,)).fetchone():
        conn.close()
        return jsonify({"error": f"MAC {custom_mac} already in use"}), 409

    # Find IP
    if specific_ip:
        ip_row = conn.execute(
            "SELECT * FROM ip_addresses WHERE ip=? AND network_id=?",
            (specific_ip, net['id'])).fetchone()
        if not ip_row:
            conn.close()
            return jsonify({"error": f"IP {specific_ip} not in {network_cidr}"}), 404
        if ip_row['status'] != 'available':
            conn.close()
            return jsonify({"error": f"IP {specific_ip} is {ip_row['status']}"}), 409
    else:
        ip_row = conn.execute(
            "SELECT * FROM ip_addresses WHERE network_id=? AND status='available' ORDER BY ip LIMIT 1",
            (net['id'],)).fetchone()
        if not ip_row:
            conn.close()
            return jsonify({"error": f"No available IPs in {network_cidr}"}), 409

    mac = custom_mac or _gen_mac(conn)
    conn.execute("UPDATE ip_addresses SET status='allocated' WHERE id=?", (ip_row['id'],))
    conn.execute(
        "INSERT INTO devices (network_id,ip_id,name,device_type,mac_address,owner,description) VALUES (?,?,?,?,?,?,?)",
        (net['id'], ip_row['id'], name, device_type, mac,
         d.get('owner',''), d.get('description','')))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "added",
        "device": name, "device_type": device_type,
        "ip_address": ip_row['ip'], "mac_address": mac,
        "network_cidr": network_cidr
    }), 201

# ─── /allocate_ip ─────────────────────────────────────────────────────────────

@app.route('/api/v1/allocate_ip', methods=['POST'])
@_require_key
def allocate_ip():
    d = request.get_json(force=True) or {}
    network_cidr = d.get('network_cidr')
    device_name  = d.get('device_name')
    if not network_cidr or not device_name:
        return jsonify({"error": "network_cidr and device_name required"}), 400

    conn = get_db()
    net = conn.execute("SELECT * FROM networks WHERE cidr=?", (network_cidr,)).fetchone()
    if not net:
        conn.close()
        return jsonify({"error": f"Network {network_cidr} not found"}), 404

    dev = conn.execute(
        "SELECT d.*, i.ip, i.status as ip_status FROM devices d JOIN ip_addresses i ON d.ip_id=i.id WHERE d.name=? AND d.network_id=?",
        (device_name, net['id'])).fetchone()

    if dev:
        # Re-allocate if needed
        if dev['ip_status'] == 'allocated':
            conn.close()
            return jsonify({"error": f"{device_name} already has {dev['ip']}"}), 409
        conn.execute("UPDATE ip_addresses SET status='allocated' WHERE id=?", (dev['ip_id'],))
        conn.commit()
        conn.close()
        return jsonify({"status": "reallocated", "ip": dev['ip'], "mac": dev['mac_address']})

    # New allocation
    specific = d.get('ip')
    dtype    = d.get('device_type', 'Computer')
    if specific:
        ip_row = conn.execute(
            "SELECT * FROM ip_addresses WHERE ip=? AND network_id=? AND status='available'",
            (specific, net['id'])).fetchone()
        if not ip_row:
            conn.close()
            return jsonify({"error": f"IP {specific} not available"}), 409
    else:
        ip_row = conn.execute(
            "SELECT * FROM ip_addresses WHERE network_id=? AND status='available' ORDER BY ip LIMIT 1",
            (net['id'],)).fetchone()
        if not ip_row:
            conn.close()
            return jsonify({"error": "No available IPs"}), 409

    mac = _gen_mac(conn)
    conn.execute("UPDATE ip_addresses SET status='allocated' WHERE id=?", (ip_row['id'],))
    conn.execute(
        "INSERT INTO devices (network_id,ip_id,name,device_type,mac_address,owner,description) VALUES (?,?,?,?,?,?,?)",
        (net['id'], ip_row['id'], device_name, dtype, mac,
         d.get('owner',''), d.get('description','')))
    conn.commit()
    conn.close()
    return jsonify({"status": "allocated", "ip": ip_row['ip'], "mac": mac,
                    "device": device_name, "network": network_cidr}), 201

# ─── /release_ip ──────────────────────────────────────────────────────────────

@app.route('/api/v1/release_ip', methods=['POST'])
@_require_key
def release_ip():
    d = request.get_json(force=True) or {}
    ip = d.get('ip_address') or d.get('ip')
    if not ip:
        return jsonify({"error": "ip_address required"}), 400

    conn = get_db()
    ip_row = conn.execute("SELECT * FROM ip_addresses WHERE ip=?", (ip,)).fetchone()
    if not ip_row:
        conn.close()
        return jsonify({"error": f"IP {ip} not found"}), 404
    if ip_row['status'] == 'reserved':
        conn.close()
        return jsonify({"error": "Cannot release a reserved address"}), 409
    if ip_row['status'] == 'available':
        conn.close()
        return jsonify({"error": f"IP {ip} is already available"}), 409

    dev = conn.execute("SELECT * FROM devices WHERE ip_id=?", (ip_row['id'],)).fetchone()
    prev_dev = dev['name'] if dev else None
    prev_mac = dev['mac_address'] if dev else None

    conn.execute("DELETE FROM devices WHERE ip_id=?", (ip_row['id'],))
    conn.execute("UPDATE ip_addresses SET status='available' WHERE id=?", (ip_row['id'],))
    conn.commit()
    conn.close()

    return jsonify({"status": "released", "ip": ip,
                    "previous_device": prev_dev, "previous_mac": prev_mac})

# ─── /blocks ──────────────────────────────────────────────────────────────────

@app.route('/api/v1/blocks', methods=['GET'])
@_require_key
def list_blocks():
    conn = get_db()
    blocks = conn.execute("SELECT * FROM blocks ORDER BY id").fetchall()
    result = []
    for b in blocks:
        nets = conn.execute("SELECT id,name,cidr FROM networks WHERE block_id=?", (b['id'],)).fetchall()
        result.append({**dict(b), "network_count": len(nets), "networks": [dict(n) for n in nets]})
    conn.close()
    return jsonify({"blocks": result})

# ─── /networks ────────────────────────────────────────────────────────────────

@app.route('/api/v1/networks', methods=['GET'])
@_require_key
def list_networks():
    conn = get_db()
    rows = conn.execute(
        "SELECT n.*, b.name as block_name, b.cidr as block_cidr FROM networks n JOIN blocks b ON n.block_id=b.id ORDER BY n.id"
    ).fetchall()
    result = []
    for r in rows:
        result.append({**dict(r), "stats": _net_stats(conn, r['id'])})
    conn.close()
    return jsonify({"networks": result})

# ─── /devices ─────────────────────────────────────────────────────────────────

@app.route('/api/v1/devices', methods=['GET'])
@_require_key
def list_devices():
    conn = get_db()
    rows = conn.execute(
        """SELECT d.name, d.device_type, d.mac_address, d.owner, d.description,
                  d.status, d.allocated_at, i.ip, n.cidr as network_cidr,
                  n.name as network_name, b.name as block_name
           FROM devices d
           JOIN ip_addresses i ON d.ip_id=i.id
           JOIN networks n ON d.network_id=n.id
           JOIN blocks b ON n.block_id=b.id
           ORDER BY d.device_type, d.name"""
    ).fetchall()
    conn.close()
    return jsonify({"devices": [dict(r) for r in rows], "total": len(rows)})

# ─── /lookup ──────────────────────────────────────────────────────────────────

@app.route('/api/v1/lookup', methods=['GET'])
@_require_key
def lookup():
    ip     = request.args.get('ip')
    mac    = request.args.get('mac')
    device = request.args.get('device')

    conn = get_db()
    base = """SELECT d.name, d.device_type, d.mac_address, d.owner, d.description,
                     d.status, d.allocated_at, i.ip, n.cidr, n.name as network_name,
                     b.cidr as block_cidr, b.name as block_name
              FROM devices d
              JOIN ip_addresses i ON d.ip_id=i.id
              JOIN networks n ON d.network_id=n.id
              JOIN blocks b ON n.block_id=b.id"""
    if ip:
        row = conn.execute(base + " WHERE i.ip=?", (ip,)).fetchone()
    elif mac:
        row = conn.execute(base + " WHERE d.mac_address=?", (mac,)).fetchone()
    elif device:
        row = conn.execute(base + " WHERE d.name=?", (device,)).fetchone()
    else:
        conn.close()
        return jsonify({"error": "Pass ?ip=, ?mac=, or ?device="}), 400

    conn.close()
    return jsonify(dict(row)) if row else (jsonify({"error": "Not found"}), 404)

# ─── /generate_mac ────────────────────────────────────────────────────────────

@app.route('/api/v1/generate_mac', methods=['GET'])
@_require_key
def gen_mac():
    conn = get_db()
    mac = _gen_mac(conn)
    conn.close()
    return jsonify({"mac_address": mac, "oui": "C0:EF (CEJO)"})

# ─── /summary ─────────────────────────────────────────────────────────────────

@app.route('/api/v1/summary', methods=['GET'])
@_require_key
def summary():
    conn = get_db()
    blocks   = conn.execute("SELECT COUNT(*) c FROM blocks").fetchone()['c']
    networks = conn.execute("SELECT COUNT(*) c FROM networks").fetchone()['c']
    total_ip = conn.execute("SELECT COUNT(*) c FROM ip_addresses").fetchone()['c']
    avail    = conn.execute("SELECT COUNT(*) c FROM ip_addresses WHERE status='available'").fetchone()['c']
    alloc    = conn.execute("SELECT COUNT(*) c FROM ip_addresses WHERE status='allocated'").fetchone()['c']
    devices  = conn.execute("SELECT COUNT(*) c FROM devices").fetchone()['c']
    by_type  = conn.execute("SELECT device_type, COUNT(*) c FROM devices GROUP BY device_type").fetchall()
    conn.close()
    return jsonify({
        "blocks": blocks, "networks": networks,
        "ip_addresses": {"total": total_ip, "available": avail, "allocated": alloc,
                         "utilization_pct": round(alloc/total_ip*100,1) if total_ip else 0},
        "devices": {"total": devices, "by_type": {r['device_type']: r['c'] for r in by_type}}
    })

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

