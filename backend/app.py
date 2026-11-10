from datetime import date, datetime, time, timedelta
from functools import wraps

import pandas as pd
from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import ml
from config import Config

# Frontend lives in a separate top-level folder
app = Flask(__name__,
            template_folder="../frontend/templates",
            static_folder="../frontend/static")
app.config.from_object(Config)
app.teardown_appcontext(db.close_db)

ACTIVE = "('booked','checked_in')"


# ------------------------------------------------------------------ helpers
@app.before_request
def load_user():
    g.user = None
    if "user_id" in session:
        g.user = db.query("SELECT id, name, email, role FROM users WHERE id=%s",
                          (session["user_id"],), one=True)


@app.context_processor
def inject_globals():
    return {"user": g.user, "cfg": Config}


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in first"), 401
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*a, **kw):
        if g.user["role"] != "admin":
            flash("Admins only.", "danger")
            return redirect(url_for("index"))
        return view(*a, **kw)
    return wrapped


def parse_slot(data):
    """Validate date/start/duration from a dict-like. Returns (date, start, end) or None."""
    try:
        d = date.fromisoformat(str(data.get("date", "")))
        start, dur = int(data.get("start")), int(data.get("duration", 1))
    except (TypeError, ValueError):
        return None
    end = start + dur
    if start < Config.OPEN_HOUR or end > Config.CLOSE_HOUR:
        return None
    if not 1 <= dur <= Config.MAX_DURATION:
        return None
    return d, start, end


def booked_seat_ids(d, start, end):
    rows = db.query(
        f"SELECT DISTINCT seat_id FROM bookings WHERE booking_date=%s "
        f"AND status IN {ACTIVE} AND start_hour<%s AND end_hour>%s", (d, end, start))
    return {r["seat_id"] for r in rows}


def sweep():
    """Mark no-shows, complete finished sessions, log an occupancy snapshot."""
    now = datetime.now()
    db.execute(
        "UPDATE bookings SET status='no_show' WHERE status='booked' AND "
        "TIMESTAMP(booking_date, MAKETIME(start_hour, %s, 0)) < %s",
        (Config.GRACE_MINUTES, now))
    db.execute(
        "UPDATE bookings SET status='completed' WHERE status='checked_in' AND "
        "TIMESTAMP(booking_date, MAKETIME(end_hour, 0, 0)) <= %s", (now,))
    if Config.OPEN_HOUR <= now.hour < Config.CLOSE_HOUR:
        total = db.query("SELECT COUNT(*) c FROM seats WHERE status='active'", one=True)["c"]
        occ = db.query(
            "SELECT COUNT(DISTINCT seat_id) c FROM bookings WHERE booking_date=%s "
            "AND status IN ('booked','checked_in','completed') "
            "AND start_hour<=%s AND end_hour>%s",
            (now.date(), now.hour, now.hour), one=True)["c"]
        db.execute(
            "INSERT INTO occupancy_history (record_date, hour, day_of_week, occupied, "
            "total_seats, is_exam_period) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE occupied=VALUES(occupied), total_seats=VALUES(total_seats)",
            (now.date(), now.hour, now.weekday(), occ, total, ml.is_exam_period(now.date())))


# --------------------------------------------------------------------- auth
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if not name or not email or len(password) < 6:
            flash("Fill all fields; password needs at least 6 characters.", "danger")
        elif db.query("SELECT id FROM users WHERE email=%s", (email,), one=True):
            flash("That email is already registered.", "danger")
        else:
            db.execute("INSERT INTO users (name,email,password_hash) VALUES (%s,%s,%s)",
                       (name, email, generate_password_hash(password)))
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        row = db.query("SELECT * FROM users WHERE email=%s",
                       (request.form["email"].strip().lower(),), one=True)
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = row["id"]
            return redirect(url_for("admin" if row["role"] == "admin" else "index"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# -------------------------------------------------------------------- pages
@app.get("/")
def index():
    sweep()
    now = datetime.now()
    total = db.query("SELECT COUNT(*) c FROM seats WHERE status='active'", one=True)["c"]
    in_use = len(booked_seat_ids(now.date(), now.hour, now.hour + 1))
    stats = {"total": total, "in_use": in_use, "free": max(total - in_use, 0),
             "pct": round(100 * in_use / total) if total else 0}
    return render_template("index.html", stats=stats, today=date.today().isoformat())


@app.get("/book")
@login_required
def book():
    return render_template("book.html", today=date.today().isoformat())


@app.get("/my-bookings")
@login_required
def my_bookings():
    sweep()
    rows = db.query(
        "SELECT b.*, s.seat_code, s.zone FROM bookings b JOIN seats s ON s.id=b.seat_id "
        "WHERE b.user_id=%s ORDER BY b.booking_date DESC, b.start_hour DESC", (g.user["id"],))
    return render_template("my_bookings.html", bookings=rows, today=date.today())


@app.post("/bookings/<int:booking_id>/cancel")
@login_required
def cancel_booking(booking_id):
    n = db.execute("UPDATE bookings SET status='cancelled' WHERE id=%s AND user_id=%s "
                   "AND status='booked'", (booking_id, g.user["id"]))
    flash("Booking cancelled." if n else "Could not cancel this booking.",
          "success" if n else "danger")
    return redirect(url_for("my_bookings"))


@app.post("/bookings/<int:booking_id>/checkin")
@login_required
def checkin(booking_id):
    sweep()
    b = db.query("SELECT * FROM bookings WHERE id=%s AND user_id=%s AND status='booked'",
                 (booking_id, g.user["id"]), one=True)
    ok = False
    if b and b["booking_date"] == date.today():
        opens = datetime.combine(b["booking_date"], time(b["start_hour"])) - timedelta(minutes=15)
        ok = datetime.now() >= opens
    if ok:
        db.execute("UPDATE bookings SET status='checked_in' WHERE id=%s", (booking_id,))
        flash("Checked in. Enjoy your session!", "success")
    else:
        flash("Check-in opens 15 minutes before your slot (and closes "
              f"{Config.GRACE_MINUTES} minutes after it starts).", "warning")
    return redirect(url_for("my_bookings"))


# ---------------------------------------------------------------------- API
@app.get("/api/forecast")
def api_forecast():
    try:
        d = date.fromisoformat(request.args.get("date", date.today().isoformat()))
    except ValueError:
        return jsonify(error="Invalid date"), 400
    data = ml.forecast(d, Config.OPEN_HOUR, Config.CLOSE_HOUR)
    best = min(data, key=lambda r: r["occupancy"])
    peak = max(data, key=lambda r: r["occupancy"])
    return jsonify(date=d.isoformat(), forecast=data, best_hour=best["hour"],
                   peak_hour=peak["hour"])


@app.get("/api/seats")
@login_required
def api_seats():
    slot = parse_slot(request.args)
    if not slot:
        return jsonify(error="Choose a valid date and time range."), 400
    d, start, end = slot
    seats = db.query("SELECT * FROM seats ORDER BY seat_code")
    booked = booked_seat_ids(d, start, end)
    zone_total, zone_busy = {}, {}
    for s in seats:
        s["available"] = s["status"] == "active" and s["id"] not in booked
        zone_total[s["zone"]] = zone_total.get(s["zone"], 0) + 1
        if not s["available"]:
            zone_busy[s["zone"]] = zone_busy.get(s["zone"], 0) + 1
    zone_load = {z: zone_busy.get(z, 0) / n for z, n in zone_total.items()}
    prefs = {k: int(request.args.get(k, 0) == "1") for k in ("power", "window", "quiet")}
    recommended = ml.rank_seats([s for s in seats if s["available"]], prefs, zone_load)
    return jsonify(seats=seats, recommended=recommended)


@app.post("/api/bookings")
@login_required
def api_create_booking():
    data = request.get_json(silent=True) or {}
    slot = parse_slot(data)
    if not slot:
        return jsonify(error="Invalid date or time range."), 400
    d, start, end = slot
    now = datetime.now()
    if d < now.date() or (d == now.date() and start < now.hour):
        return jsonify(error="That time slot has already started or passed."), 400
    try:
        seat_id = int(data.get("seat_id"))
    except (TypeError, ValueError):
        return jsonify(error="Choose a seat."), 400

    conn = db.get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, status FROM seats WHERE id=%s FOR UPDATE", (seat_id,))
        seat = cur.fetchone()
        if not seat or seat["status"] != "active":
            conn.rollback()
            return jsonify(error="Seat not available."), 404
        cur.execute(
            f"SELECT id FROM bookings WHERE seat_id=%s AND booking_date=%s "
            f"AND status IN {ACTIVE} AND start_hour<%s AND end_hour>%s",
            (seat_id, d, end, start))
        if cur.fetchone():
            conn.rollback()
            return jsonify(error="Someone just booked that seat. Pick another."), 409
        cur.execute(
            f"SELECT id FROM bookings WHERE user_id=%s AND booking_date=%s "
            f"AND status IN {ACTIVE} AND start_hour<%s AND end_hour>%s",
            (g.user["id"], d, end, start))
        if cur.fetchone():
            conn.rollback()
            return jsonify(error="You already have a booking that overlaps this time."), 409

        cur.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(status='no_show'),0) AS ns FROM bookings "
            "WHERE user_id=%s AND status IN ('completed','checked_in','no_show')",
            (g.user["id"],))
        hist = cur.fetchone()
        past, ns = int(hist["n"]), float(hist["ns"])
        lead = max((datetime.combine(d, time(start)) - now).total_seconds() / 3600, 0)
        risk = ml.predict_noshow(lead, start, d.weekday(), end - start,
                                 past, ns / past if past else 0.0)
        cur.execute(
            "INSERT INTO bookings (user_id, seat_id, booking_date, start_hour, end_hour, "
            "no_show_risk) VALUES (%s,%s,%s,%s,%s,%s)",
            (g.user["id"], seat_id, d, start, end, risk))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return jsonify(ok=True, redirect=url_for("my_bookings"))


# -------------------------------------------------------------------- admin
@app.get("/admin")
@admin_required
def admin():
    sweep()
    stats = db.query(
        "SELECT (SELECT COUNT(*) FROM users WHERE role='student') AS students, "
        "(SELECT COUNT(*) FROM bookings WHERE booking_date=CURDATE() "
        " AND status<>'cancelled') AS today_bookings, "
        "(SELECT COALESCE(ROUND(100*SUM(status='no_show')/NULLIF(COUNT(*),0),1),0) "
        " FROM bookings WHERE booking_date>=CURDATE()-INTERVAL 30 DAY "
        " AND status IN ('completed','checked_in','no_show')) AS noshow_rate", one=True)
    risky = db.query(
        "SELECT b.*, u.name, s.seat_code FROM bookings b "
        "JOIN users u ON u.id=b.user_id JOIN seats s ON s.id=b.seat_id "
        "WHERE b.status='booked' AND b.booking_date>=CURDATE() AND b.no_show_risk>=0.3 "
        "ORDER BY b.no_show_risk DESC LIMIT 15")
    seats = db.query("SELECT * FROM seats ORDER BY seat_code")
    return render_template("admin.html", stats=stats, risky=risky, seats=seats)


@app.post("/admin/seats/<int:seat_id>/toggle")
@admin_required
def toggle_seat(seat_id):
    db.execute("UPDATE seats SET status=IF(status='active','maintenance','active') "
               "WHERE id=%s", (seat_id,))
    return redirect(url_for("admin"))


@app.post("/admin/retrain")
@admin_required
def retrain():
    hist = db.query("SELECT record_date, hour, day_of_week, occupied, total_seats, "
                    "is_exam_period FROM occupancy_history")
    occ = ml.train_occupancy(pd.DataFrame(hist))
    rows = db.query("SELECT user_id, booking_date, start_hour, end_hour, created_at, status "
                    "FROM bookings WHERE status IN ('completed','checked_in','no_show') "
                    "ORDER BY created_at")
    ns = ml.train_noshow(ml.build_noshow_frame(rows) if rows else None)
    flash(f"Occupancy model retrained on {occ['rows']} rows "
          f"(MAE {occ['mae_pct_points']} pts). No-show model trained on "
          f"{ns['source']}, AUC {ns.get('auc', 'n/a')}.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)
