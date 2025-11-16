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

_lock = threading.Lock()


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
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        fh = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=5)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


def _extract_summary_from_stdout(stdout: str):
    """
    Cherche une ligne du type:
      OKOFEN_SUMMARY:{...json...}
    et retourne le dict JSON si trouvé, sinon None.
    """
    if not stdout:
        return None

    lines = stdout.strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("OKOFEN_SUMMARY:"):
            raw = line[len("OKOFEN_SUMMARY:"):]
            try:
                return json.loads(raw)
            except Exception:
                logging.warning("Impossible de parser le JSON de résumé: %s", raw)
                return None
    return None


def create_app():
    # Charger .env
    load_dotenv(dotenv_path=os.environ.get("OKOFEN_ENV_FILE", ".env"))

    app = Flask(__name__)

    # Config depuis l'environnement
    app.config["OKOFEN_TOKEN"] = os.environ.get("OKOFEN_TOKEN", "change-me")
    app.config["SCRIPT_PATH"] = os.environ.get(
        "SCRIPT_PATH",
        os.path.abspath("Okofen_Playwright.py"),
    )
    app.config["SCRIPT_TIMEOUT"] = int(os.environ.get("SCRIPT_TIMEOUT", "40"))
    app.config["LOG_PATH"] = os.environ.get(
        "LOG_PATH",
        "/opt/Okofen_Playwright/logs/okofen-web.log",
    )
    app.config["LOG_LEVEL"] = os.environ.get("LOG_LEVEL", "INFO")

    _setup_logging(app.config["LOG_PATH"], app.config["LOG_LEVEL"])

    logging.info("Okofen web service starting…")
    logging.info("Using script: %s", app.config["SCRIPT_PATH"])

    # ---------------------------
    # Auth Bearer
    # ---------------------------

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

    # ---------------------------
    # Exécution script
    # ---------------------------

    def _run_script(action: str):
        start = time.time()

        if action not in {"on", "off"}:
            return 400, {"ok": False, "error": "invalid_action", "action": action}

        # Empêcher deux exécutions simultanées
        if not _lock.acquire(blocking=False):
            logging.warning("Concurrent invocation refused (action=%s)", action)
            payload = {
                "ok": False,
                "action": action,
                "status": "unknown",
                "changed": None,
                "duration_ms": 0,
                "error_code": "busy",
                "error_message": "Une commande est déjà en cours d'exécution.",
                "speech": "Une commande de pilotage de la chaudière est déjà en cours, réessaie dans quelques secondes.",
            }
            return 429, payload

        try:
            cmd = [sys.executable, app.config["SCRIPT_PATH"], action]
            logging.info("Running %s (timeout=%ss)", cmd, app.config["SCRIPT_TIMEOUT"])

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=app.config["SCRIPT_TIMEOUT"],
                    env={**os.environ},
                )

                duration = int((time.time() - start) * 1000)

                # Logs bruts côté serveur
                if proc.stdout:
                    logging.debug("Script stdout:\n%s", proc.stdout)
                if proc.stderr:
                    level = logging.WARNING if proc.returncode != 0 else logging.DEBUG
                    logging.log(level, "Script stderr:\n%s", proc.stderr)

                summary = _extract_summary_from_stdout(proc.stdout or "")

                if summary is None:
                    # fallback générique
                    ok = (proc.returncode == 0)
                    payload = {
                        "ok": ok,
                        "action": action,
                        "status": "unknown",
                        "changed": None,
                        "duration_ms": duration,
                        "speech": "Commande exécutée, mais sans résumé structuré.",
                    }
                    if not ok:
                        payload["error_code"] = "script_error"
                        payload["error_message"] = "Erreur lors de l'exécution du script."
                        logging.warning("Script terminé avec rc=%s sans résumé JSON", proc.returncode)
                    http_code = 200 if ok else 500
                    return http_code, payload

                # Construction de la réponse à partir du résumé
                ok = bool(summary.get("ok"))
                status_after = summary.get("status_after", "unknown")
                changed = summary.get("changed")
                duration_ms = summary.get("duration_ms", duration)
                message = summary.get("message")

                payload = {
                    "ok": ok,
                    "action": summary.get("action", action),
                    "status": status_after,
                    "changed": changed,
                    "duration_ms": duration_ms,
                    "speech": message,
                    "summary": summary,
                }

                http_code = 200 if ok else 500
                if ok:
                    logging.info(
                        "Script success action=%s status=%s changed=%s duration_ms=%s",
                        action,
                        status_after,
                        changed,
                        duration_ms,
                    )
                else:
                    logging.warning(
                        "Script failure action=%s status=%s changed=%s duration_ms=%s error=%s",
                        action,
                        status_after,
                        changed,
                        duration_ms,
                        summary.get("error"),
                    )

                return http_code, payload

            except subprocess.TimeoutExpired as e:
                duration = int((time.time() - start) * 1000)
                logging.error("Timeout after %sms for action=%s", duration, action)

                stdout = (e.stdout or "")
                stderr = (e.stderr or "")

                if stdout:
                    logging.debug("Script stdout (timeout):\n%s", stdout)
                if stderr:
                    logging.warning("Script stderr (timeout):\n%s", stderr)

                payload = {
                    "ok": False,
                    "action": action,
                    "status": "unknown",
                    "changed": None,
                    "duration_ms": duration,
                    "error_code": "timeout",
                    "error_message": "La chaudière ne répond pas (timeout).",
                    "speech": "Je n'arrive pas à contacter la chaudière pour l'instant.",
                }
                return 504, payload

        finally:
            _lock.release()

    # ---------------------------
    # Routes HTTP
    # ---------------------------

    @app.get("/healthz")
    def health():
        script_ok = (
            os.path.isfile(app.config["SCRIPT_PATH"])
            and os.access(app.config["SCRIPT_PATH"], os.R_OK)
        )
        return jsonify(
            {
                "ok": True,
                "script_path": app.config["SCRIPT_PATH"],
                "script_readable": script_ok,
                "timeout_s": app.config["SCRIPT_TIMEOUT"],
            }
        )

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


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
