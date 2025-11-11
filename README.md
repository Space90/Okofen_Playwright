# 🔥 Okofen_Playwright

Automatisation de la chaudière **ÖkoFEN Pellematic** via **Playwright** (Python).  
Ce script permet d’**allumer ou d’éteindre la chaudière** en simulant les interactions sur l’interface web locale, lorsque l’API officielle n’est pas disponible.

---

## ⚙️ Fonctionnalités

- 🔁 Allume (`on`) ou éteint (`off`) la chaudière en fonction de son état actuel.
- 🧠 Ignore automatiquement la commande si le mode est déjà correct.
- 🔒 Identifiants et mots de passe **externalisés via `.env`** (non versionné).
- 🧩 Compatible avec un déploiement dans un **LXC Debian** (Proxmox, Docker ou autre VM légère).
- 💬 Prévu pour intégration avec **Home Assistant** et **Alexa**.

---

## 🧰 Installation

### 1️⃣ Cloner le dépôt

```bash
git clone https://github.com/Space90/Okofen_Playwright.git
cd Okofen_Playwright
