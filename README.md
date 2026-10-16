# YouthConnect

A Flask + HTML/CSS/JavaScript capstone prototype for scholarship applications, youth announcements, events, reminders, and analytics. **No database is used.** Server-side demo records are held in Python memory and reset when Flask restarts. Browser localStorage is device/browser-specific and is not shared across users or devices.

## Requirements
- Python 3.10+
- Internet connection for CDN-hosted Chart.js and icons (optional; core pages still load without charts/icons)

## Run on Windows
```powershell
cd youthconnect
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000.

## Run on macOS/Linux
```bash
cd youthconnect
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Demo access
- Admin: `admin@youthconnect.local` / `AdminDemo123!`
- Scholarship coordinator: `coordinator@youthconnect.local` / `Coordinator123!`
- Student: register a new account on the registration page.

These are local demonstration accounts only. Change them before any public deployment. Passwords are hashed, and Flask sessions are used, but the in-memory account store is not production persistence.

## Included features
- Student registration/login and role-protected admin routes
- Scholarship directory and application submission/status review
- Announcements and event management
- Event registrations and attendance recording
- In-system notifications/reminder generation when a page loads
- Admin analytics, CSV reports, and printable reports
- User/role management, activity log, responsive styling

## Important limitations
- No database: Python collections reset after server restart.
- Browser localStorage is not a shared server data store.
- Reminders are generated when pages load; no background scheduler, email, SMS, or push delivery is configured.
- File inputs are demonstration selections only; uploads are not permanently stored.
- Use a production database, CSRF protection, HTTPS, secure deployment configuration, and a real notification service before real-world use.
