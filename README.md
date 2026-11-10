# SmartSeat – AI-Powered Library Seating Management System

Python · Flask · Jinja2 · Bootstrap 5 · HTML/CSS/JS · MySQL · scikit-learn · NumPy · pandas

```
library-seating-ai/
├── backend/                 # Flask app, database, ML
│   ├── app.py               # routes + REST API
│   ├── config.py            # settings (DB, opening hours)
│   ├── db.py                # MySQL helpers
│   ├── ml.py                # forecasting, no-show model, seat ranking
│   ├── setup_data.py        # seeds seats/admin/history and trains models
│   ├── schema.sql           # MySQL tables
│   └── requirements.txt
└── frontend/                # served by Flask (Jinja2 templates + static)
    ├── templates/           # base, index, login, register, book, my_bookings, admin
    └── static/{css,js}/     # style.css, forecast.js, booking.js
```

## AI features
1. **Occupancy forecast** – RandomForestRegressor predicts crowd level per hour from hour, weekday, weekend and exam-period features.
2. **Smart seat recommendation** – pandas/NumPy scoring ranks free seats by your needs (power, window, quiet) and prefers less crowded zones.
3. **No-show prediction** – LogisticRegression estimates the chance a booking is abandoned (lead time, history, time of day). Admins see risky bookings.
4. Models retrain from the admin page; real hourly occupancy snapshots are logged automatically.

## Setup
```bash
cd backend
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

mysql -u root -p < schema.sql                        # create DB + tables
export DB_USER=root DB_PASSWORD=yourpass             # Windows: set DB_USER=root ...
python setup_data.py                                 # seed data + train models
python app.py                                        # http://127.0.0.1:5000
```
Admin login: `admin@library.local` / `admin123` (change it). Students sign up on the site.

## Notes
- Booking is hourly (08:00–21:00, max 4h). Seats are row-locked on booking to prevent double-booking.
- Check-in opens 15 min before the slot; no check-in within 15 min after start marks a no-show and frees the seat.
- Before deploying: set `SECRET_KEY`, add CSRF protection (Flask-WTF), and run behind gunicorn.
