# Data model

Everything in this backend hangs off two identifiers. Nothing else crosses module
boundaries, so any record traces to a patient and to whoever touched it.

| Identifier | Pattern | Example | Is |
|---|---|---|---|
| `patient_id` | `P-###` | `P-101` | The subject of care. Unique, never reused. |
| `staff_id` | `X-##` | `N-02` | The person acting. `X` is the role prefix. |
| `handoff_id` | `HO-<patient digits>-<4 hex>` | `HO-101-7b2d` | One handover of one patient. |

Role prefixes: **N** nurse (RN) · **A** aide · **C** charge nurse · **D** provider.
The prefix must match the role — posting an aide with an `N-` id is rejected.

Live versions of this page: `GET /schema` for the dictionary, `GET /openapi.json`
for field-level types, `/docs` to browse both.

## How the tables relate

```
staff (X-##) ──┬── assignments ──┬── patients (P-###)
               │   shift          │
               │                  ├── vitals        patient_id
               │                  ├── meds          patient_id
               │                  ├── labs          patient_id
               │                  ├── orders        patient_id
               │                  ├── alarm_events  patient_id + actor
               │                  └── notes         patient_id + author
               │
               ├── handoffs       patient_id + giver_id + receiver_id
               │     ├── handoff_fields   handoff_id
               │     └── acks             handoff_id + actor
               ├── tasks          patient_id + owner_id + handoff_id
               ├── messages       patient_id + sender_id + recipient_id
               │     └── message_events   message_id
               └── audit          actor
```

## Tables

| Table | Key | Holds |
|---|---|---|
| `patients` | `id` = P-### | Demographics, code status, allergies, isolation, restraints, Morse fall score, preferred language |
| `staff` | `id` = X-## | Name, role, shift window, `backup_for` (who they cover when unreachable) |
| `assignments` | rowid | Which caregiver holds which patient, per `shift` (day/night) |
| `vitals` | rowid | HR, BP, RR, temp, SpO2, `abnormal` flag |
| `meds` | rowid | Drug, dose, route, due, given, status (due/given/missed/held) |
| `labs` | rowid | Name, value, unit, status (pending/resulted), HIGH/LOW/CRITICAL flag |
| `orders` | rowid | Order text and status (active/open/complete) |
| `alarm_events` | rowid | Limit changes and silences, with who and when — the safety block's source |
| `notes` | rowid | Shift notes, aide observations, family concerns; `abnormal` marks the ones that escalate |
| `handoffs` | `id` = HO-… | Status, timings, the receiver's read-back text |
| `handoff_fields` | rowid | One row per I-PASS field: value, **its source**, whether required, who edited it |
| `acks` | rowid | Per-item acknowledgements, and agent proposals as `proposal:<kind>` |
| `tasks` | rowid | Carry-over work: text, owner, due time, status, origin (`auto:med`, `manual:N-01`) |
| `messages` | rowid | SBAR fields, urgency, state, re-route time, `rerouted_to` |
| `message_events` | rowid | The state trail with timestamps — sent → delivered → read → responded |
| `focus`, `held` | rowid | Focus-mode windows and the messages held during them |
| `concerns`, `incidents` | rowid | Speak-up concerns and incidents linked to a handoff |
| `audit` | rowid | Append-only: who did what, when (NFR-4) |

## Conventions

- **Times** are stored as ward-clock epoch floats and rendered `HH:MM` at the edge.
  Internal autoincrement ids are **not** exposed in the typed responses.
- **Fall risk** is derived from `fall_score`, never stored: 13+ HIGH, 7–12 moderate, else low.
- **The RN for a patient** is derived too — the assignee whose shift contains the ward
  clock right now. A patient has a day and a night assignment; `rn_id` resolves to
  whichever is on. That's why an aide's observation reaches the right nurse.
- **Foreign keys are off.** This is a mock. The relationships are real and the API
  validates them on write, but SQLite does not enforce them.

## The endpoints that join it up

| Call | Returns |
|---|---|
| `GET /patients` | Every patient with derived fall risk and the RN on shift. Filters: `rn_id`, `room`, `high_fall_risk` |
| `GET /patients/{id}/records` | **The full join** — vitals, meds, labs, orders, alarms, notes, plus row counts |
| `GET /nurses?role=nurse` | The RN roster with `on_shift` resolved against the ward clock |
| `GET /nurses/{id}/panel` | **One RN's whole workload** — assigned patients, open/overdue/unowned tasks, outstanding handoffs, unread messages |
| `GET /assignments` | Who holds whom, filterable by shift |
| `GET /schema` | This dictionary, as JSON |

## Events, not columns

Anything that **changes during a shift** is an event table, never a single column:
`vent_settings`, `restraint_events`, `alarm_events`, `sedation`, `message_events`.

A column holds the current value and loses the change — and the change is exactly what a
handoff has to carry. "Restraints were on at the start of shift, I took them off around
midnight" is two rows. As one column it becomes `restraints: off`, and the next nurse never
learns they were ever on, or why.

`post_op_day`, `fall_risk`, `weight_stale` and `rn_id` are derived on read, never stored.

## ICU tables

| Table | Holds | From the script |
|---|---|---|
| `devices` | Lines, Foley, drains, airway: site, when placed, by whom, status | "new peripheral line, left forearm, about eleven"; the Foley; the ETT |
| `device_obs` | Output and site checks against one device | "Foley draining well, about forty an hour, urine is clear" |
| `wounds` | Site, description, dressing, when last changed | "abdominal dressing is dry and intact, I changed it at the start of shift" |
| `vent_settings` | One row per **change** — mode, PEEP, FiO2, rate, Vt | "PEEP went up from five to eight, around three forty" = two rows |
| `sedation` | Drug, dose and RASS over time | "on propofol, RASS minus two overnight, settled" |
| `restraint_events` | applied / removed / reassessed, with the reason | "restraints were on at the start, I took them off around midnight" |

Patients also gained `mrn`, `sex`, `unit`, `bed`, `admitted_on`, `surgery_on`,
`weight_kg` + `weight_at` + `weight_source`, `allergies_status`, and the family contact.

`allergies_status` exists because **"no allergies recorded" is not "no known allergies."**
The first means nobody asked. The draft prints the distinction and the contingency list
says "allergy history has NOT been taken — confirm before any new drug."

## The synthetic ward

Ten patients, four RNs across two shifts, plus an aide, a charge nurse and two providers.

| | Patients | On shift |
|---|---|---|
| **N-01 Priya Raman** (day, 07–19) | P-101, P-102, P-103 | the three demo patients |
| **N-02 Marcus Hale** (night, 19–07) | P-101, P-102, P-103 | receives the demo handoff |
| **N-03 Aisha Farouk** (day, 07–19) | P-104 … P-108 | background load |
| **N-04 Sean Donnelly** (night, 19–07) | P-104 … P-108 | background load |

P-101 to P-103 are seeded with **deliberate gaps** and no derived tasks — the demo
derives those live. P-104 to P-108 come pre-derived so an RN panel shows a real load.

**P-109 Theresa Vance** is the team's handoff script as structured records: bed 7, day 3
post-op, sedated and ventilated, a ~07:00 night-to-day handoff (N-02 Marcus → N-01 Priya).
The name and MRN are invented — the script's initials and partial MRN are not used. Her
record keeps four gaps on purpose:

1. **Allergy history never taken** — "no allergies recorded".
2. **Weight is the admission weight**, day 1, never repeated, on a patient receiving fluids.
3. **PEEP raised 5→8 at 03:40** with no provider contact recorded.
4. **Restraints removed at 00:05** with no documented reassessment.

Build her handoff with
`POST /handoffs/P-109/draft?giver=N-02&receiver=N-01` — the safety block comes back with
nine fields instead of the med-surg five.

Adding more: `POST /patients`, `POST /nurses`, `POST /assignments`. Ids are validated,
duplicates return 409, and a role/prefix mismatch returns 422.
