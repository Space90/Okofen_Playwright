# AGENT CONTEXT — Okofen MCP Project

## 1. Production Environment (DO NOT MODIFY)

- The production system runs inside a Proxmox LXC container named `okofen-automation`.
- Production code is located in `/opt/Okofen_Playwright`.
- This directory is considered **PRODUCTION and STABLE**.
- It must NOT be modified, refactored, renamed, or redeployed unless explicitly requested.

### Production stack
- Python 3.11 virtual environment: `/opt/Okofen_Playwright/.venv`
- Flask API served via Gunicorn
- Systemd service: `okofen-web.service`
- Gunicorn binds to `0.0.0.0:5000`
- Playwright is executed on demand via HTTP routes (not as a long-running process)
- No Docker is used in production (native Playwright inside LXC)

### Production service command (reference only)
Gunicorn launches Flask which internally calls `Okofen_Playwright.py` when routes are invoked.

---

## 2. Development Environment (SAFE AREA)

- All development for the MCP server happens in:
  `/opt/Okofen_dev/Okofen_MCP`
- This directory is versioned on GitHub:
  https://github.com/Space90/Okofen_MCP
- This directory is SAFE to modify, refactor, and experiment with.

---

## 3. MCP Design Rules

- The MCP server MUST NOT directly modify production code at first.
- The MCP server MUST interact with production via:
  - HTTP calls to the existing Flask API (localhost:5000)
  - CSV parsing (touch_*.csv files)
- Direct Playwright execution inside the MCP is forbidden in early phases.
- Stability of the production boiler control has priority over new features.

---

## 4. Development Principles

- Prefer small, incremental changes.
- Commit frequently with clear messages.
- Any change that could impact production must be explicitly discussed first.
- Logging must be explicit and readable.
- Safety > Automation > Features.

---

End of document.
