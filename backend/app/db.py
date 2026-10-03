"""SQLite store. Mock backend: schema + synthetic seed, no migrations, no pooling."""
import sqlite3
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("SG_DB", Path(__file__).resolve().parent.parent / "shiftguard.db"))

SCHEMA = """
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS vitals;
DROP TABLE IF EXISTS meds;
DROP TABLE IF EXISTS labs;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS alarm_events;
DROP TABLE IF EXISTS staff;
DROP TABLE IF EXISTS assignments;
DROP TABLE IF EXISTS notes;
DROP TABLE IF EXISTS handoffs;
DROP TABLE IF EXISTS handoff_fields;
DROP TABLE IF EXISTS acks;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS message_events;
DROP TABLE IF EXISTS focus;
DROP TABLE IF EXISTS held;
DROP TABLE IF EXISTS concerns;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS device_obs;
DROP TABLE IF EXISTS wounds;
DROP TABLE IF EXISTS vent_settings;
DROP TABLE IF EXISTS sedation;
DROP TABLE IF EXISTS restraint_events;
DROP TABLE IF EXISTS audit;

CREATE TABLE patients (
  id TEXT PRIMARY KEY, mrn TEXT, name TEXT, sex TEXT, age INT,
  unit TEXT, room TEXT, bed TEXT,
  dx TEXT, admitted_on TEXT, surgery_on TEXT,
  code_status TEXT, allergies TEXT, allergies_status TEXT,
  isolation TEXT, restraints TEXT,
  fall_score INT, fall_interventions TEXT, language TEXT,
  weight_kg REAL, weight_at REAL, weight_source TEXT,
  family_name TEXT, family_relation TEXT, family_phone TEXT, family_updated_at REAL
);
CREATE TABLE vitals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, t REAL,
  hr INT, bp TEXT, rr INT, temp REAL, spo2 INT, abnormal INT DEFAULT 0
);
CREATE TABLE meds (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, name TEXT, dose TEXT,
  route TEXT, due_at REAL, given_at REAL, status TEXT
);
CREATE TABLE labs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, name TEXT, value TEXT,
  unit TEXT, status TEXT, flag TEXT, resulted_at REAL
);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, text TEXT, status TEXT
);
CREATE TABLE alarm_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, t REAL,
  kind TEXT, detail TEXT, actor TEXT
);
CREATE TABLE staff (
  id TEXT PRIMARY KEY, name TEXT, role TEXT,
  shift_start REAL, shift_end REAL, backup_for TEXT
);
CREATE TABLE assignments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id TEXT, staff_id TEXT, shift TEXT DEFAULT 'day', since REAL
);
CREATE TABLE notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, author TEXT, t REAL,
  kind TEXT, text TEXT, abnormal INT DEFAULT 0
);
CREATE TABLE handoffs (
  id TEXT PRIMARY KEY, patient_id TEXT, giver_id TEXT, receiver_id TEXT,
  status TEXT, created_at REAL, ready_at REAL, started_at REAL, closed_at REAL,
  readback TEXT
);
CREATE TABLE handoff_fields (
  id INTEGER PRIMARY KEY AUTOINCREMENT, handoff_id TEXT, section TEXT, key TEXT,
  label TEXT, value TEXT, source TEXT, required INT, filled_by TEXT, edited_by TEXT
);
CREATE TABLE acks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, handoff_id TEXT, kind TEXT,
  ref TEXT, actor TEXT, t REAL
);
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, handoff_id TEXT, text TEXT,
  owner_id TEXT, due_at REAL, status TEXT, origin TEXT, escalated INT DEFAULT 0
);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, sender_id TEXT,
  recipient_id TEXT, urgency TEXT, situation TEXT, background TEXT,
  assessment TEXT, recommendation TEXT, state TEXT, created_at REAL,
  sent_at REAL, reroute_at REAL, rerouted_to TEXT, reply_to INT, body TEXT
);
CREATE TABLE message_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INT, state TEXT, t REAL, actor TEXT
);
CREATE TABLE focus (
  id INTEGER PRIMARY KEY AUTOINCREMENT, staff_id TEXT, reason TEXT,
  started_at REAL, ended_at REAL
);
CREATE TABLE held (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INT, staff_id TEXT, released INT DEFAULT 0);
CREATE TABLE concerns (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, body TEXT, anonymous INT,
  reporter_id TEXT, routed_to TEXT, state TEXT, opened_at REAL, closed_at REAL
);
CREATE TABLE incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, text TEXT, t REAL, handoff_id TEXT
);
-- Lines, tubes and airways. One row per device, status tracks removal.
CREATE TABLE devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT,
  kind TEXT, site TEXT, detail TEXT,
  inserted_at REAL, inserted_by TEXT, removed_at REAL, status TEXT
);
-- Output or an observation on a device (Foley 40 mL/hr, drain serous).
CREATE TABLE device_obs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, device_id INT, patient_id TEXT,
  t REAL, detail TEXT, actor TEXT
);
CREATE TABLE wounds (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, site TEXT,
  description TEXT, dressing TEXT, last_changed_at REAL, changed_by TEXT, status TEXT
);
-- One row per ventilator CHANGE, so 'PEEP 5 to 8 at 03:40' is two rows, not one value.
CREATE TABLE vent_settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, t REAL,
  mode TEXT, peep INT, fio2 INT, rate INT, tidal_volume INT,
  changed_by TEXT, note TEXT
);
CREATE TABLE sedation (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, t REAL,
  drug TEXT, dose TEXT, rass INT, note TEXT, actor TEXT
);
-- Restraints go on and come off. A single column would lose the midnight removal.
CREATE TABLE restraint_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, t REAL,
  action TEXT, kind TEXT, reason TEXT, actor TEXT
);
CREATE TABLE audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, actor TEXT, action TEXT, detail TEXT
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


_conn = None


def db():
    global _conn
    if _conn is None:
        _conn = connect()
    return _conn


def rows(sql, args=()):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = db().execute(sql, args).fetchone()
    return dict(r) if r else None


def write(sql, args=()):
    cur = db().execute(sql, args)
    db().commit()
    return cur.lastrowid


def audit(actor, action, detail=""):
    from .clock import now
    write("INSERT INTO audit (t, actor, action, detail) VALUES (?,?,?,?)",
          (now(), actor, action, detail))


def reset_and_seed():
    """Wipe and rebuild the synthetic ward. Safe to call mid-demo."""
    global _conn
    if _conn:
        _conn.close()
        _conn = None
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = db()
    conn.executescript(SCHEMA)
    conn.commit()
    from .seed import seed_ward
    seed_ward()
