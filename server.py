#!/usr/bin/env python3
"""Samsung TV web remote: a phone-friendly remote page that relays button presses to a
Samsung Tizen TV over its local WebSocket API (port 8002). Power-on uses Wake-on-LAN.

Configure with environment variables:
  TV_IP      TV's LAN IP address (required)
  TV_MAC     TV's Wi-Fi/Ethernet MAC, for Wake-on-LAN, e.g. AA:BB:CC:DD:EE:FF (optional)
  TV_TOKEN   pairing token (optional; on first use the TV asks you to Allow, then the
             token is printed to the log so you can set it and skip the prompt)
  REMOTE_NAME  name shown on the TV's pairing prompt (default: Web Remote)
  PORT       HTTP port (default: 8095)
"""
import socket, ssl, base64, os, json, struct, time, urllib.request, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

TV = os.environ["TV_IP"]
TV_MAC = os.environ.get("TV_MAC", "").replace(":", "").replace("-", "")
TOKEN = os.environ.get("TV_TOKEN", "")
NAME = os.environ.get("REMOTE_NAME", "Web Remote")
PORT = int(os.environ.get("PORT", "8095"))
HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()  # one TV connection at a time
ALLOWED = {"KEY_POWER","KEY_VOLUP","KEY_VOLDOWN","KEY_MUTE","KEY_CHUP","KEY_CHDOWN","KEY_PRECH",
           "KEY_UP","KEY_DOWN","KEY_LEFT","KEY_RIGHT","KEY_ENTER","KEY_RETURN","KEY_EXIT","KEY_HOME",
           "KEY_MENU","KEY_SOURCE","KEY_INFO","KEY_GUIDE","KEY_TOOLS","KEY_CH_LIST",
           "KEY_PLAY","KEY_PAUSE","KEY_STOP","KEY_REWIND","KEY_FF","KEY_RED","KEY_GREEN","KEY_YELLOW","KEY_CYAN",
           "KEY_HDMI","KEY_TV"} | {f"KEY_{d}" for d in range(10)}

def ws_open():
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    s = ctx.wrap_socket(socket.create_connection((TV, 8002), timeout=8))
    name = base64.b64encode(NAME.encode()).decode(); k = base64.b64encode(os.urandom(16)).decode()
    tok = f"&token={TOKEN}" if TOKEN else ""
    s.send((f"GET /api/v2/channels/samsung.remote.control?name={name}{tok} HTTP/1.1\r\n"
            f"Host: {TV}:8002\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    h = b""
    while b"\r\n\r\n" not in h: h += s.recv(1)
    hello = ws_recv(s)  # ms.channel.connect (carries a token after you press Allow on the TV)
    try:
        t = json.loads(hello).get("data", {}).get("token")
        if t and t != TOKEN: print(f"Paired. Set TV_TOKEN={t} to skip the TV prompt next time.", flush=True)
    except Exception:
        pass
    return s

def ws_recv(s):
    b = s.recv(2); n = b[1] & 127
    if n == 126: n = struct.unpack(">H", s.recv(2))[0]
    elif n == 127: n = struct.unpack(">Q", s.recv(8))[0]
    d = b""
    while len(d) < n: d += s.recv(n - len(d))
    return d.decode(errors="replace")

def ws_send(s, o):
    p = json.dumps(o).encode(); m = os.urandom(4); L = len(p)
    hdr = bytes([0x81]) + (bytes([0x80 | L]) if L < 126 else bytes([0x80 | 126]) + struct.pack(">H", L))
    s.send(hdr + m + bytes(c ^ m[i % 4] for i, c in enumerate(p)))

def keys(seq):
    with LOCK:
        s = ws_open()
        try:
            for key in seq:
                ws_send(s, {"method": "ms.remote.control", "params": {"Cmd": "Click", "DataOfCmd": key,
                            "Option": "false", "TypeOfRemote": "SendRemoteKey"}})
                time.sleep(0.45)
        finally:
            s.close()

# Older Tizen sets ignore the ed.installedApp.get request, so use a list of well-known app IDs.
KNOWN_APPS = {"3201907018807": "Netflix", "111299001912": "YouTube", "3201910019365": "Prime Video",
              "3201601007625": "Hulu", "3201901017640": "Disney+", "3202006020991": "Peacock",
              "3201807016597": "Apple TV", "3201504001965": "Tubi", "3201606009684": "Spotify",
              "3201907018784": "Internet", "3201710015037": "Gallery"}

def apps():
    # Shown as-is; launching an app that isn't installed just returns an error. Check yours with
    # GET http://<tv>:8001/api/v2/applications/<id> and edit KNOWN_APPS to taste.
    return sorted(({"id": i, "name": n} for i, n in KNOWN_APPS.items()), key=lambda a: a["name"].lower())

def launch(app_id):
    if app_id not in KNOWN_APPS: raise ValueError("unknown app")
    req = urllib.request.Request(f"http://{TV}:8001/api/v2/applications/{app_id}", method="POST", data=b"")
    urllib.request.urlopen(req, timeout=8).read()

def state():
    try: return json.load(urllib.request.urlopen(f"http://{TV}:8001/api/v2/", timeout=3))["device"].get("PowerState", "?")
    except Exception: return "off"

def wol():
    if not TV_MAC: raise RuntimeError("set TV_MAC to use Power On")
    pkt = b"\xff" * 6 + bytes.fromhex(TV_MAC) * 16
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for _ in range(5):
        for dst in (("255.255.255.255", 9), (TV, 9)): s.sendto(pkt, dst)
        time.sleep(0.3)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.reply(200, open(os.path.join(HERE, "remote.html"), "rb").read(), "text/html; charset=utf-8")
            if u.path == "/api/state": return self.reply(200, {"state": state()})
            if u.path == "/api/apps": return self.reply(200, {"apps": apps()})
        except Exception as e:
            return self.reply(502, {"error": str(e)})
        self.reply(404, {"error": "not found"})
    def do_POST(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/key":
                k = q.get("k", "")
                if k not in ALLOWED: return self.reply(400, {"error": "key not allowed"})
                keys([k]); return self.reply(200, {"ok": True})
            if u.path == "/api/channel":
                n = q.get("n", "")
                if not n.replace("-", "").isdigit() or len(n) > 5: return self.reply(400, {"error": "bad channel"})
                seq = [("KEY_PLUS100" if c == "-" else f"KEY_{c}") for c in n] + ["KEY_ENTER"]
                keys(seq); return self.reply(200, {"ok": True})
            if u.path == "/api/power":
                if q.get("to") == "on":
                    wol(); return self.reply(200, {"ok": True, "note": "wake sent"})
                if state() == "on": keys(["KEY_POWER"])
                return self.reply(200, {"ok": True})
            if u.path == "/api/launch":
                launch(q.get("id", "")); return self.reply(200, {"ok": True})
        except Exception as e:
            return self.reply(502, {"error": f"TV not reachable: {e}"})
        self.reply(404, {"error": "not found"})

if __name__ == "__main__":
    print(f"Samsung TV web remote on :{PORT} -> {TV}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
