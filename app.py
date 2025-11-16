#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import subprocess
import threading
from logging.handlers import RotatingFileHandler
from functools import wraps
from flask import Flask, request, jsonify
from dotenv import load_dotenv


# ============================================
# Logging global
# ============================================

def _setup_logging(log_path: str, level: str = "INFO"):
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Fichier rotatif
    if log_path:
        fh = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=5)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


# ============================================
# App factory
# ============================================

_lock = threading.Lock()

def create_app():

    # Charger .env
    load_dotenv(dotenv_path=os.environ.get("OKOFEN_ENV_FILE", ".env"))

    app = Flask(__name__)

    # Config
    app.config["OKOFEN_TOKEN"] = os.environ.get("OKOFEN_TOKEN", "change-me")
    app.config["SCRIPT_PATH"] = os.environ.get(
        "SCRIPT_PATH", os.path.abspath("Okofen_Playwright.py")
    )
    app.config["SCRIPT_TIMEOUT"] = int(os.environ.get("SCRIPT_TIMEOUT", "25"))
    app.config["LOG_PATH"] = os.environ.get("LOG_PATH", "/var/log/okofen-web.log")
    app.config["LOG_LEVEL"] = os.environ.get("LOG_LEVEL", "INFO")

    _setup_logging(app.config["LOG_PATH"], app.config["LOG_LEVEL"])

    logging.info("Okofen web service starting…")
    logging.info("Using script: %s", app.config["SCRIPT_PATH"])


    # ============================================
    # Authentification Bearer
    # ============================================

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


    # ============================================
    # Fonction interne d’exécution
    # ============================================

    def _run_script(action: str):
        start = time.time()

        if action not in {"on", "off"}:
            return 400, {"ok": False, "error": "invalid_action", "action": action}

        # Empêcher deux exécutions simultanées
        if not _lock.acquire(blocking=False):
            logging.warning("Concurrent invocation refused (action=%s)", action)
            return 429, {"ok": False, "error": "busy", "action": action}

        try:
            cmd = [sys.executable, app.config["SCRIPT_PATH"], action]
            logging.info("Running %s (timeout=%s)", cmd, app.config["SCRIPT_TIMEOUT"])

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
                    "stdout": proc.stdout[-4000:],
                    "stderr": proc.stderr[-4000:],
                    "duration_ms": duration,
                }

                if proc.returncode == 0:
                    logging.info("Success rc=0 duration=%sms", duration)
                    return 200, payload
                else:
                    logging.warning("Script error rc=%s", proc.returncode)
                    return 500, payload

            except subprocess.TimeoutExpired as e:
                duration = int((time.time() - start) * 1000)
                logging.error("Timeout after %sms", duration)
                return 504, {
                    "ok": False,
                    "error": "timeout",
                    "action": action,
                    "duration_ms": duration,
                    "stdout": (e.stdout or "")[-4000:],
                    "stderr": (e.stderr or "")[-4000:],
                }

        finally:
            _lock.release()


    # ============================================
    # Routes HTTP
    # ============================================

    @app.get("/healthz")
    def health():
        script_ok = (
            os.path.isfile(app.config["SCRIPT_PATH"]) and
            os.access(app.config["SCRIPT_PATH"], os.R_OK)
        )
        return jsonify({
            "ok": True,
            "script_path": app.config["SCRIPT_PATH"],
            "script_readable": script_ok,
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


# ============================================
# Mode direct
# ============================================

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
