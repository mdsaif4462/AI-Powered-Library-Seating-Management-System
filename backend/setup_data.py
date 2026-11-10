"""One-time setup: admin user, seats, synthetic history, initial model training.
Run AFTER importing schema.sql:   python setup_data.py
"""
import mysql.connector
from werkzeug.security import generate_password_hash

import ml
from config import Config


def main():
    conn = mysql.connector.connect(**Config.DB_CONFIG)
    cur = conn.cursor()

    cur.execute("INSERT IGNORE INTO users (name,email,password_hash,role) "
                "VALUES (%s,%s,%s,'admin')",
                ("Librarian", "admin@library.local", generate_password_hash("admin123")))

    cur.execute("SELECT COUNT(*) FROM seats")
    if cur.fetchone()[0] == 0:
        zones = [("Quiet Zone", "Q", 20), ("Study Hall", "S", 24), ("Group Area", "G", 16)]
        rows = [(f"{p}{i:02d}", zone, int(i % 2 == 0), int(i % 5 in (1, 2)),
                 int(zone == "Quiet Zone"))
                for zone, p, n in zones for i in range(1, n + 1)]
        cur.executemany("INSERT INTO seats (seat_code,zone,has_power,near_window,is_quiet) "
                        "VALUES (%s,%s,%s,%s,%s)", rows)

    df = ml.synthetic_occupancy(total=60)
    cur.executemany(
        "INSERT IGNORE INTO occupancy_history (record_date,hour,day_of_week,occupied,"
        "total_seats,is_exam_period) VALUES (%s,%s,%s,%s,%s,%s)",
        [(r.record_date, int(r.hour), int(r.day_of_week), int(r.occupied),
          int(r.total_seats), int(r.is_exam_period)) for r in df.itertuples()])
    conn.commit()
    conn.close()

    print(ml.train_occupancy(df))
    print(ml.train_noshow())
    print("Done. Admin login: admin@library.local / admin123  (change it!)")


if __name__ == "__main__":
    main()
