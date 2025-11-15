#!/usr/bin/env python3
# -------------------------------------------------
def require_token(f):
@wraps(f)
def wrapper(*args, **kwargs):
auth = request.headers.get("Authorization", "")
if not auth.startswith("Bearer "):
return jsonify({"ok": False, "error": "missing_bearer"}), 401
token = auth.split(" ", 1)[1].strip()
if token != app.config["OKOFEN_TOKEN"]:
return jsonify({"ok": False, "error": "invalid_token"}), 401
return f(*args, **kwargs)
return wrapper


# -------------------------------------------------
# Outil d’exécution
# -------------------------------------------------
def _run_script(action: str):
start = time.time()
if action not in {"on", "off"}:
return 400, {"ok": False, "error": "invalid_action", "action": action}


# Empêche exécutions simultanées
acquired = _lock.acquire(blocking=False)
if not acquired:
logging.warning("Concurrent invocation refused for action=%s", action)
return 429, {"ok": False, "error": "busy", "action": action}


try:
cmd = [sys.executable, app.config["SCRIPT_PATH"], action]
logging.info("Exec: %s (timeout=%ss)", cmd, app.config["SCRIPT_TIMEOUT"])


try:
proc = subprocess.run(
cmd,
capture_output=True,
text=True,
timeout=app.config["SCRIPT_TIMEOUT"],
env={**os.environ},
)
duration = int((time.time() - start) * 1000)
payload = {
"ok": proc.returncode == 0,
"action": action,
"returncode": proc.returncode,
"stdout": proc.stdout[-4000:], # protège la taille
"stderr": proc.stderr[-4000:],
"duration_ms": duration,
}
level = logging.INFO if proc.returncode == 0 else logging.WARNING
logging.log(level, "Result: rc=%s duration_ms=%s", proc.returncode, duration)
return (200 if proc.returncode == 0 else 500), payload


except subprocess.TimeoutExpired as e:
duration = int((time.time() - start) * 1000)
logging.error("Timeout after %sms for action=%s", duration, action)
return 504, {
"ok": False,
"error": "timeout",
"action": action,
"duration_ms": duration,
"stdout": (e.stdout or "")[-4000:],
"stderr": (e.stderr or "")[-4000:],
}


finally:
if acquired:
_lock.release()


# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.get("/healthz")
def healthz():
script_exists = os.path.isfile(app.config["SCRIPT_PATH"]) and os.access(app.config["SCRIPT_PATH"], os.R_OK)
return jsonify({
"ok": True,
"script_path": app.config["SCRIPT_PATH"],
"script_readable": script_exists,
"timeout_s": app.config["SCRIPT_TIMEOUT"],
})


@app.post("/on")
@require_token
def turn_on():
code, body = _run_script("on")
return jsonify(body), code


@app.post("/off")
@require_token
def turn_off():
code, body = _run_script("off")
return jsonify(body), code


return app




# Pour gunicorn: "gunicorn -w 2 -b 0.0.0.0:5000 'app:create_app()'"
if __name__ == "__main__":
app = create_app()
app.run(host="0.0.0.0", port=5000)
