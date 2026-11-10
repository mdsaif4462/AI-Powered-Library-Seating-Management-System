import mysql.connector
from flask import g, current_app


def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(**current_app.config["DB_CONFIG"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, params=(), one=False):
    cur = get_db().cursor(dictionary=True)
    cur.execute(sql, params)
    result = cur.fetchone() if one else cur.fetchall()
    cur.close()
    return result


def execute(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    last_id, affected = cur.lastrowid, cur.rowcount
    cur.close()
    return last_id if last_id else affected
