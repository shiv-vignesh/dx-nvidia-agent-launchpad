"""Synthetic med-surg ward: 3 patients, 2 nurses, 1 aide, 1 charge nurse, 1 provider.
No real PHI. Deliberately seeded with gaps so the demo has something to catch."""
from .db import write
from .clock import at, now, MIN, HOUR

def P(id, mrn, name, sex, age, room, bed, dx, code_status, allergies, fall_score,
      fall_interventions, language, allergies_status="documented", isolation="none",
      restraints="none", admitted_on=None, surgery_on=None, weight_kg=None,
      weight_hour=None, weight_source=None, family=None):
    """One patient row. Keyword defaults keep the med-surg eight terse while letting
    the ICU patient carry weight, surgery date, family contact and the rest."""
    fam = family or (None, None, None, None)
    return dict(id=id, mrn=mrn, name=name, sex=sex, age=age, unit="4 West", room=room,
                bed=bed, dx=dx, admitted_on=admitted_on, surgery_on=surgery_on,
                code_status=code_status, allergies=allergies,
                allergies_status=allergies_status, isolation=isolation,
                restraints=restraints, fall_score=fall_score,
                fall_interventions=fall_interventions, language=language,
                weight_kg=weight_kg, weight_hour=weight_hour, weight_source=weight_source,
                family_name=fam[0], family_relation=fam[1], family_phone=fam[2],
                family_updated_hour=fam[3])


PATIENTS = [
    P("P-101", "MRN-40-11827", "Alma Whitfield", "F", 78, "412-A", "A",
      "CHF exacerbation", "DNR", "penicillin, shellfish", 14,
      "bed alarm on, non-slip socks, hourly rounding", "English",
      weight_kg=81.4, weight_hour=6, weight_source="bed scale"),
    P("P-102", "MRN-40-11903", "Dmitri Sokolov", "M", 64, "412-B", "B",
      "post-op day 1, hip ORIF", "Full code", "none known", 11,
      "bed alarm on, gait belt with transfers", "Russian",
      surgery_on="2026-10-02", weight_kg=92.0, weight_hour=6, weight_source="bed scale"),
    P("P-103", "MRN-40-12044", "Ruth Okonkwo", "F", 55, "414-A", "A",
      "pyelonephritis, sepsis watch", "Full code", "sulfa", 6,
      "standard precautions", "English", isolation="contact"),
    # --- the rest of the unit: background load, so an RN panel looks real ---
    P("P-104", "MRN-40-11650", "Henry Baptiste", "M", 71, "414-B", "B",
      "COPD exacerbation", "Full code", "none known", 9,
      "bed alarm on, oxygen tubing clear", "Haitian Creole"),
    P("P-105", "MRN-40-12110", "Wen Li", "F", 44, "416-A", "A",
      "diabetic ketoacidosis, resolving", "Full code",
      "metformin (GI intolerance)", 4, "standard precautions", "Mandarin"),
    P("P-106", "MRN-40-10988", "Grace Mbeki", "F", 83, "416-B", "B",
      "aspiration pneumonia", "DNR/DNI", "codeine", 16,
      "bed alarm on, sitter overnight, non-slip socks", "English", isolation="droplet"),
    P("P-107", "MRN-40-12201", "Tomas Herrera", "M", 59, "418-A", "A",
      "GI bleed, 2 units transfused", "Full code", "none known", 12,
      "bed alarm on, assist to bathroom", "Spanish"),
    P("P-108", "MRN-40-11775", "Eileen Novak", "F", 67, "418-B", "B",
      "cellulitis, right lower leg", "Full code", "vancomycin (rash)", 7,
      "standard precautions", "English", isolation="contact"),

    # --- P-109: the teammates' night-to-day handoff script, bed 7.
    # Name and MRN are invented; the script's initials and partial MRN are not used.
    # Post-op day 3, sedated and ventilated — richer than the med-surg eight and the
    # reason the schema grew devices, wounds, vent_settings, sedation and restraints.
    P("P-109", "MRN-77-00412", "Theresa Vance", "F", 58, "4W-7", "7",
      "day 3 post-op, laparotomy", "Full code",
      "none recorded", 13,
      "bed alarm on, two-person assist, restraints reviewed each shift", "English",
      allergies_status="NOT DOCUMENTED — absence of a record is not a cleared allergy",
      isolation="contact", restraints="off since 00:05",
      admitted_on="2026-09-29", surgery_on="2026-09-30",
      weight_kg=74.0, weight_hour=None, weight_source="admission weight, not re-weighed",
      family=("daughter", "daughter", "on chart", 2)),
]

STAFF = [
    ("N-01", "Priya Raman", "nurse", 7, 19, None),
    ("N-02", "Marcus Hale", "nurse", 19, 7, None),
    ("N-03", "Aisha Farouk", "nurse", 7, 19, None),
    ("N-04", "Sean Donnelly", "nurse", 19, 7, None),
    ("A-01", "Joy Adeyemi", "aide", 11, 23, None),
    ("C-01", "Dana Brooks", "charge", 15, 23, None),
    ("D-01", "Dr. Owusu", "provider", 7, 19, None),
    ("D-02", "Dr. Lindqvist", "provider", 19, 7, "D-01"),
]


def seed_ward():
    for p in PATIENTS:
        r = dict(p)
        wh = r.pop("weight_hour")
        fh = r.pop("family_updated_hour")
        r["weight_at"] = at(wh) if wh is not None else None
        r["family_updated_at"] = at(fh) if fh is not None else None
        cols = ",".join(r)
        write(f"INSERT INTO patients ({cols}) VALUES ({','.join('?' * len(r))})",
              tuple(r.values()))

    for sid, name, role, s, e, backup in STAFF:
        write("""INSERT INTO staff (id,name,role,shift_start,shift_end,backup_for)
                 VALUES (?,?,?,?,?,?)""", (sid, name, role, at(s), at(e), backup))

    # Priya (day) holds the three demo patients; the rest of the unit is split so an
    # RN panel shows a believable load. Night nurses mirror the day assignment.
    day = {"N-01": ["P-101", "P-102", "P-103"],
           "N-03": ["P-104", "P-105", "P-106", "P-107", "P-108"]}
    night = {"N-02": ["P-101", "P-102", "P-103"],
             "N-04": ["P-104", "P-105", "P-106", "P-107", "P-108"]}
    for shift, mapping in (("day", day), ("night", night)):
        for rn, pids in mapping.items():
            for pid in pids:
                write("""INSERT INTO assignments (patient_id, staff_id, shift, since)
                         VALUES (?,?,?,?)""", (pid, rn, shift, now()))

    # ---- vitals: Alma trending toward trouble, Ruth febrile and tachycardic ----
    v = [
        ("P-101", -6, 88, "128/74", 18, 36.8, 95, 0),
        ("P-101", -4, 96, "122/70", 20, 36.9, 93, 0),
        ("P-101", -2, 108, "104/62", 24, 37.1, 90, 1),
        ("P-101", -0.5, 114, "98/58", 26, 37.2, 89, 1),
        ("P-102", -4, 78, "132/80", 16, 36.6, 97, 0),
        ("P-102", -1, 82, "128/78", 16, 36.7, 98, 0),
        ("P-103", -5, 102, "118/68", 20, 38.4, 96, 1),
        ("P-103", -1, 110, "112/66", 22, 38.9, 95, 1),
        # background patients: one baseline and one current reading each
        ("P-104", -5, 92, "138/84", 22, 36.9, 91, 1),
        ("P-104", -1, 88, "134/80", 20, 36.8, 93, 0),
        ("P-105", -5, 84, "124/76", 16, 36.5, 98, 0),
        ("P-105", -1, 80, "120/74", 16, 36.6, 99, 0),
        ("P-106", -5, 96, "118/70", 22, 37.6, 92, 1),
        ("P-106", -1, 94, "116/68", 20, 37.4, 94, 0),
        ("P-107", -5, 104, "102/60", 18, 36.4, 97, 1),
        ("P-107", -1, 92, "110/66", 16, 36.5, 98, 0),
        ("P-108", -5, 78, "128/78", 16, 37.2, 98, 0),
        ("P-108", -1, 76, "126/76", 16, 37.0, 99, 0),
    ]
    for pid, hrs, hr, bp, rr, temp, spo2, ab in v:
        write("""INSERT INTO vitals (patient_id,t,hr,bp,rr,temp,spo2,abnormal)
                 VALUES (?,?,?,?,?,?,?,?)""", (pid, now() + hrs * 3600, hr, bp, rr, temp, spo2, ab))

    # ---- meds: two due soon after handoff, one missed on the outgoing shift ----
    m = [
        ("P-101", "furosemide", "40 mg", "IV", at(16, 0), at(16, 5), "given"),
        ("P-101", "furosemide", "40 mg", "IV", at(20, 0), None, "due"),
        ("P-101", "potassium chloride", "20 mEq", "PO", at(19, 30), None, "due"),
        ("P-102", "oxycodone", "5 mg", "PO", at(18, 0), at(18, 10), "given"),
        ("P-102", "enoxaparin", "40 mg", "SC", at(18, 30), None, "missed"),
        ("P-102", "cefazolin", "1 g", "IV", at(20, 30), None, "due"),
        ("P-103", "ceftriaxone", "1 g", "IV", at(19, 15), None, "due"),
        ("P-104", "prednisone", "40 mg", "PO", at(20, 0), None, "due"),
        ("P-105", "insulin glargine", "18 units", "SC", at(21, 0), None, "due"),
        ("P-106", "piperacillin-tazobactam", "3.375 g", "IV", at(19, 45), None, "due"),
        ("P-107", "pantoprazole", "40 mg", "IV", at(20, 0), None, "due"),
        ("P-108", "clindamycin", "600 mg", "IV", at(19, 30), None, "due"),
    ]
    for row in m:
        write("""INSERT INTO meds (patient_id,name,dose,route,due_at,given_at,status)
                 VALUES (?,?,?,?,?,?,?)""", row)

    # ---- labs: one pending troponin (the classic omission), one critical K+ ----
    lab = [
        ("P-101", "troponin I", None, "ng/mL", "pending", None, None),
        ("P-101", "potassium", "3.1", "mmol/L", "resulted", "LOW", at(17, 40)),
        ("P-101", "BNP", "1840", "pg/mL", "resulted", "HIGH", at(13, 10)),
        ("P-102", "hemoglobin", "9.4", "g/dL", "resulted", "LOW", at(15, 20)),
        ("P-103", "lactate", "2.8", "mmol/L", "resulted", "HIGH", at(18, 5)),
        ("P-103", "blood culture", None, None, "pending", None, None),
        ("P-104", "ABG pCO2", "52", "mmHg", "resulted", "HIGH", at(16, 30)),
        ("P-105", "glucose", "184", "mg/dL", "resulted", "HIGH", at(18, 0)),
        ("P-106", "chest x-ray", None, None, "pending", None, None),
        ("P-107", "hemoglobin", "8.1", "g/dL", "resulted", "LOW", at(17, 0)),
        ("P-108", "CRP", "96", "mg/L", "resulted", "HIGH", at(15, 45)),
    ]
    for row in lab:
        write("""INSERT INTO labs (patient_id,name,value,unit,status,flag,resulted_at)
                 VALUES (?,?,?,?,?,?,?)""", row)

    o = [
        ("P-101", "Strict intake and output, daily weights", "active"),
        ("P-101", "Cardiology consult — not yet seen", "open"),
        ("P-102", "Out of bed with physio twice daily", "active"),
        ("P-102", "Remove surgical drain when output under 30 mL/shift", "open"),
        ("P-103", "Repeat lactate at 22:00", "open"),
        ("P-104", "Titrate oxygen to keep SpO2 88-92%", "active"),
        ("P-106", "Aspiration precautions, thickened fluids", "active"),
        ("P-107", "Serial hemoglobin every 6 hours", "active"),
    ]
    for row in o:
        write("INSERT INTO orders (patient_id,text,status) VALUES (?,?,?)", row)

    # ---- alarm changes during the outgoing shift: the safety-block payload ----
    a = [
        ("P-101", at(17, 50), "limit_changed", "SpO2 low limit 92% → 88%", "N-01"),
        ("P-101", at(18, 5), "silenced", "Monitor silenced 15 min during family visit", "N-01"),
        ("P-102", at(14, 20), "limit_changed", "HR high limit 120 → 130", "N-01"),
    ]
    for row in a:
        write("INSERT INTO alarm_events (patient_id,t,kind,detail,actor) VALUES (?,?,?,?,?)", row)

    n = [
        ("P-101", "N-01", at(18, 10), "shift_note",
         "Family at bedside, asking about discharge plan. Patient more short of breath on exertion this afternoon.", 0),
        ("P-101", "A-01", at(18, 25), "aide_obs",
         "Slightly confused about the time of day — new since this morning.", 1),
        ("P-102", "A-01", at(17, 45), "aide_obs", "Ate 25% of dinner, refused the rest.", 0),
        ("P-103", "N-01", at(18, 15), "shift_note",
         "Rigors at 18:00, warm blankets given. Pushing oral fluids.", 0),
    ]
    for row in n:
        write("INSERT INTO notes (patient_id,author,t,kind,text,abnormal) VALUES (?,?,?,?,?,?)", row)

    # Standing task carried from the outgoing shift
    write("""INSERT INTO tasks (patient_id,handoff_id,text,owner_id,due_at,status,origin)
             VALUES (?,?,?,?,?,?,?)""",
          ("P-102", None, "Reposition — last turn 15:40, overdue", "N-01",
           now() - 20 * MIN, "open", "auto:turn"))

    # Background patients start with their carry-over work already derived, so an RN
    # panel shows a real load. P-101..P-103 are left bare — the demo derives those.
    from .modules.tasks import derive
    for pid in ("P-104", "P-105", "P-106", "P-107", "P-108"):
        derive(pid)
    write("UPDATE tasks SET owner_id='N-03' WHERE patient_id IN "
          "('P-104','P-105','P-106','P-107','P-108') AND owner_id IS NULL")
    # one genuinely overdue item, so the panel's overdue count is not always zero
    write("""INSERT INTO tasks (patient_id,handoff_id,text,owner_id,due_at,status,origin)
             VALUES (?,?,?,?,?,?,?)""",
          ("P-106", None, "Oral care — aspiration precautions, last done 14:00", "N-03",
           now() - 45 * MIN, "open", "auto:turn"))

    seed_p109()


# ---------------------------------------------------------------------------
# P-109 — the teammates' handoff script, as structured records.
# A ~07:00 night-to-day handoff: Marcus (N-02, nights) hands to Priya (N-01, days).
# Every line below traces to a sentence in that script. The gaps are kept on
# purpose: allergies never documented, a stale admission weight, a PEEP rise at
# 03:40 with no provider contact, and restraints removed with no reassessment.
SCRIPT_NOTE = (
    "Bed 7, 4 West. 58F, day 3 post-op. Full code. No allergies recorded. Contact "
    "precautions, gown and gloves going in. 74 kilos, that is her admission weight, "
    "we have not reweighed her. On propofol, RASS minus two overnight, settled. Fall "
    "risk, restraints were on at the start of shift, I took them off around midnight "
    "and she was fine after that. New peripheral line, left forearm, I put that in "
    "about eleven, maintenance fluids running through it. Abdominal dressing is dry "
    "and intact, I changed it at the start of shift. Foley draining well, about forty "
    "an hour, urine is clear. Family called around two, I spoke to the daughter and "
    "updated her, she is the contact, number is on the chart. PEEP went up from five "
    "to eight, that was around three forty, and she tolerated it fine. Surgery are "
    "coming by this morning to have a look at her, they said before rounds. Vitals "
    "have been stable since then. Sorry, it has been a night, we had an admission at five."
)


def seed_p109():
    pid = "P-109"
    THEATRE = at(9) - 3 * 24 * HOUR   # laparotomy, three days back

    # vitals: stable, as the script says, but recorded sparsely across a busy night
    for hour, hr, bp, rr, temp, spo2, ab in (
            (20, 88, "118/68", 14, 36.9, 97, 0),
            (23, 84, "116/66", 14, 36.8, 98, 0),
            (3, 86, "114/64", 15, 37.0, 95, 0),
            (4, 85, "118/70", 14, 37.1, 97, 0),
            (6, 84, "116/68", 14, 37.0, 98, 0)):
        write("""INSERT INTO vitals (patient_id,t,hr,bp,rr,temp,spo2,abnormal)
                 VALUES (?,?,?,?,?,?,?,?)""", (pid, at(hour), hr, bp, rr, temp, spo2, ab))

    # "on propofol, RASS minus two overnight, settled"
    for hour, rass, note in ((20, -2, "settled"), (0, -2, "settled after restraints off"),
                             (4, -2, "settled"), (6, -2, "settled, no spontaneous waking trial")):
        write("""INSERT INTO sedation (patient_id,t,drug,dose,rass,note,actor)
                 VALUES (?,?,?,?,?,?,?)""",
              (pid, at(hour), "propofol", "20 mcg/kg/min", rass, note, "N-02"))

    # "PEEP went up from five to eight, that was around three forty"
    write("""INSERT INTO vent_settings
             (patient_id,t,mode,peep,fio2,rate,tidal_volume,changed_by,note)
             VALUES (?,?,?,?,?,?,?,?,?)""",
          (pid, at(19), "PRVC", 5, 40, 16, 440, "N-02", "settings at shift start"))
    write("""INSERT INTO vent_settings
             (patient_id,t,mode,peep,fio2,rate,tidal_volume,changed_by,note)
             VALUES (?,?,?,?,?,?,?,?,?)""",
          (pid, at(3, 40), "PRVC", 8, 40, 16, 440, "N-02",
           "PEEP 5 to 8, tolerated; no provider contact recorded"))

    # "restraints were on at the start of shift, I took them off around midnight"
    write("""INSERT INTO restraint_events (patient_id,t,action,kind,reason,actor)
             VALUES (?,?,?,?,?,?)""",
          (pid, at(19), "applied", "soft wrist, bilateral",
           "line and airway protection while sedated", "N-01"))
    write("""INSERT INTO restraint_events (patient_id,t,action,kind,reason,actor)
             VALUES (?,?,?,?,?,?)""",
          (pid, at(0, 5), "removed", "soft wrist, bilateral",
           "settled on propofol, no pulling at lines", "N-02"))

    # "new peripheral line, left forearm, about eleven" + the airway + the Foley
    piv = write("""INSERT INTO devices
                   (patient_id,kind,site,detail,inserted_at,inserted_by,status)
                   VALUES (?,?,?,?,?,?,?)""",
                (pid, "peripheral_iv", "left forearm", "20g, maintenance fluids running",
                 at(23), "N-02", "in situ"))
    write("""INSERT INTO devices (patient_id,kind,site,detail,inserted_at,inserted_by,status)
             VALUES (?,?,?,?,?,?,?)""",
          (pid, "airway", "oral", "ETT 7.5, 22 cm at the lip, PRVC", THEATRE, "theatre", "in situ"))
    foley = write("""INSERT INTO devices
                     (patient_id,kind,site,detail,inserted_at,inserted_by,status)
                     VALUES (?,?,?,?,?,?,?)""",
                  (pid, "foley", "urethral", "16Fr, placed in theatre",
                   THEATRE, "theatre", "in situ"))
    write("""INSERT INTO device_obs (device_id,patient_id,t,detail,actor) VALUES (?,?,?,?,?)""",
          (foley, pid, at(6), "draining well, about 40 mL/hr, urine clear", "N-02"))
    write("""INSERT INTO device_obs (device_id,patient_id,t,detail,actor) VALUES (?,?,?,?,?)""",
          (piv, pid, at(6), "site clean and dry, no infiltration", "N-02"))

    # "abdominal dressing is dry and intact, I changed it at the start of shift"
    write("""INSERT INTO wounds
             (patient_id,site,description,dressing,last_changed_at,changed_by,status)
             VALUES (?,?,?,?,?,?,?)""",
          (pid, "abdomen, midline laparotomy", "dry and intact, no strikethrough",
           "dry gauze and tape", at(19, 30), "N-02", "intact"))

    # "surgery are coming by this morning, before rounds"
    for text, status in (
            ("Surgical team review before rounds this morning — not yet seen", "open"),
            ("Daily sedation hold and spontaneous breathing trial", "active"),
            ("Re-weigh — admission weight is day 1, patient on maintenance fluids", "open"),
            ("Document allergy history — none currently recorded", "open")):
        write("INSERT INTO orders (patient_id,text,status) VALUES (?,?,?)", (pid, text, status))

    for name, value, unit, status, flag, hour in (
            ("hemoglobin", "10.2", "g/dL", "resulted", "LOW", 4),
            ("white cell count", "13.8", "10^9/L", "resulted", "HIGH", 4),
            ("creatinine", "88", "umol/L", "resulted", None, 4),
            ("CRP", None, None, "pending", None, None)):
        write("""INSERT INTO labs (patient_id,name,value,unit,status,flag,resulted_at)
                 VALUES (?,?,?,?,?,?,?)""",
              (pid, name, value, unit, status, flag, at(hour) if hour else None))

    for name, dose, route, hour, given, status in (
            ("propofol infusion", "20 mcg/kg/min", "IV", 19, 19, "given"),
            ("paracetamol", "1 g", "IV", 4, 4, "given"),
            ("enoxaparin", "40 mg", "SC", 8, None, "due"),
            ("cefazolin", "1 g", "IV", 7, None, "due")):
        write("""INSERT INTO meds (patient_id,name,dose,route,due_at,given_at,status)
                 VALUES (?,?,?,?,?,?,?)""",
              (pid, name, dose, route, at(hour), at(given) if given else None, status))

    # the verbatim handoff, as the free-text an AI-1 model would parse
    write("INSERT INTO notes (patient_id,author,t,kind,text,abnormal) VALUES (?,?,?,?,?,?)",
          (pid, "N-02", at(6, 50), "shift_note", SCRIPT_NOTE, 0))
    write("INSERT INTO notes (patient_id,author,t,kind,text,abnormal) VALUES (?,?,?,?,?,?)",
          (pid, "family", at(2), "family_concern",
           "Daughter asking when she will be woken up and whether she can visit before rounds.",
           0))
    write("""INSERT INTO assignments (patient_id, staff_id, shift, since)
             VALUES (?,?,?,?)""", (pid, "N-02", "night", at(19)))
    write("""INSERT INTO assignments (patient_id, staff_id, shift, since)
             VALUES (?,?,?,?)""", (pid, "N-01", "day", at(7)))
