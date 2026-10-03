#!/usr/bin/env bash
# Every module touched once. Prints PASS/FAIL per check, exits non-zero on failure.
set -u
H=${1:-localhost:8099}
pass=0; fail=0
chk() { # chk "name" "expected substring" curl-args...
  local name="$1" want="$2"; shift 2
  out=$(curl -sS --max-time 10 "$@" 2>&1)
  if grep -q -- "$want" <<<"$out"; then echo "PASS  $name"; pass=$((pass+1));
  else echo "FAIL  $name (wanted '$want')"; echo "      $(head -c 300 <<<"$out")"; fail=$((fail+1)); fi
}
J='-H content-type:application/json'

curl -sS -X POST "http://$H/demo/reset" >/dev/null
chk "index"              '"service"'            "http://$H/"
chk "ward"               'Alma'                 "http://$H/ward"
chk "clock"              'ward_time'            "http://$H/clock"
chk "F3 derive tasks"    '"created"'   -X POST  "http://$H/tasks/derive/P-101"
chk "F1 draft"           '"safety_block"' -X POST "http://$H/handoffs/P-101/draft"

HID=$(curl -sS "http://$H/handoffs" | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')
echo "      handoff=$HID"
chk "FR-1.3 blocks early readback" 'not ready' -X POST $J -d '{"text":"stable"}' "http://$H/handoffs/$HID/readback"
chk "FR-1.4 edit field"  '"status":"ready"' -X PATCH $J -d '{"value":"81.4 kg","actor":"N-01"}' "http://$H/handoffs/$HID/fields/baseline_weight"
chk "F2 readback gaps"   '"gaps"'   -X POST $J -d '{"text":"Alma, heart failure, DNR"}' "http://$H/handoffs/$HID/readback"
chk "close blocked"      '"closed":false'       "http://$H/handoffs/$HID/close-check"
chk "F6 focus on"        '"focus"'  -X POST $J -d '{"staff_id":"N-01","reason":"handoff"}' "http://$H/focus/start"
chk "F6 focus off"       '"digest"' -X POST     "http://$H/focus/end?staff_id=N-01"
chk "F4 sbar draft"      '"sendable":false' -X POST $J -d '{"patient_id":"P-101","concern":"SpO2 falling"}' "http://$H/escalations/draft"
MID=$(curl -sS "http://$H/messages?state=draft" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d[-1]["id"])')
chk "FR-4.1 send needs ask" 'Recommendation' -X POST $J -d "{\"message_id\":$MID}" "http://$H/messages/$MID/send"
chk "F4 set ask"         '"sendable":true' -X PATCH $J -d '{"recommendation":"Review in 30 min"}' "http://$H/escalations/$MID/recommendation"
chk "F5 send"            '"state"'  -X POST $J -d "{\"message_id\":$MID}" "http://$H/messages/$MID/send"
chk "F5 reroute timer"   'reroute_at'           "http://$H/messages/$MID"
chk "F8 board"           '"rows"'               "http://$H/oversight/board"
chk "F8 report"          'completion_rate'      "http://$H/oversight/report"
chk "F8 aide obs"        'in_next_handoff' -X POST $J -d '{"patient_id":"P-101","text":"refused dinner","abnormal":true}' "http://$H/oversight/observations"
chk "F7 family summary"  'room 412-A'           "http://$H/family-summary/P-101"
chk "F9 concern"         '"routed_to"' -X POST $J -d '{"body":"staffing unsafe","anonymous":true}' "http://$H/concerns"
chk "F9 transfer"        '"ipass"'  -X POST $J -d '{"patient_id":"P-103"}' "http://$H/transfers"
chk "F9 incident"        'linked_handoff' -X POST $J -d '{"patient_id":"P-101","text":"unwitnessed fall"}' "http://$H/incidents"
chk "audit log"          '"actor"'              "http://$H/audit"
chk "events buffer"      '"ch"'                 "http://$H/events/recent"
chk "demo script"        '"beats"'              "http://$H/demo/script"
chk "UI walkthrough"     'step by step'         "http://$H/ui"
chk "registry: patients" '"rn_id"'              "http://$H/patients"
chk "registry: one patient" 'Alma'              "http://$H/patients/P-101"
chk "registry: records join" '"counts"'         "http://$H/patients/P-101/records"
chk "registry: nurses"   'Priya'                "http://$H/nurses?role=nurse"
chk "registry: RN panel" 'open_tasks'           "http://$H/nurses/N-03/panel"
chk "registry: assignments" 'staff_id'          "http://$H/assignments"
chk "registry: data dictionary" 'patient_id'    "http://$H/schema"
chk "P-109 exists"       'Theresa Vance'        "http://$H/patients/P-109"
chk "P-109 post-op day"  '"post_op_day":3'     "http://$H/patients/P-109"
chk "P-109 stale weight" '"weight_stale":true' "http://$H/patients/P-109"
chk "P-109 ICU records"  'vent_changes'         "http://$H/patients/P-109/records"
chk "P-109 PEEP change"  '"peep":8'            "http://$H/patients/P-109/records"
chk "P-109 restraints off" 'removed'            "http://$H/patients/P-109/records"
chk "P-109 script note"  'reweighed'            "http://$H/patients/P-109/records"
chk "P-109 safety block" 'Ventilation' -X POST  "http://$H/handoffs/P-109/draft?giver=N-02&receiver=N-01"
chk "P-109 allergy gap"  'NOT DOCUMENTED'       "http://$H/patients/P-109"
chk "registry: filter by RN" 'P-101'            "http://$H/patients?rn_id=N-01"
chk "registry: bad patient id 422" '422'  -o /dev/null -w "%{http_code}" -X POST $J -d '{"id":"BAD","name":"X","room":"1","age":40,"dx":"y"}' "http://$H/patients"
chk "registry: role prefix guard" "needs an id starting" -X POST $J -d '{"id":"N-09","name":"X","role":"aide","shift_start_hour":7,"shift_end_hour":19}' "http://$H/nurses"
chk "registry: unknown patient assign" 'no patient' -X POST $J -d '{"patient_id":"P-999","staff_id":"N-01"}' "http://$H/assignments"
chk "swagger self-hosted" '/static/swagger-ui-bundle.js' "http://$H/docs"
chk "agent tool manifest" 'get_patient_snapshot' "http://$H/agent/tools"
chk "agent tool call"    '"role":"tool"' -X POST $J -d '{"name":"get_patient_snapshot","arguments":{"patient_id":"P-103"}}' "http://$H/agent/call"
chk "agent result capped" 'approx_tokens' -X POST $J -d '{"name":"list_open_items","arguments":{"patient_id":"P-101"}}' "http://$H/agent/call"
chk "agent bad tool 404" 'no tool'       -X POST $J -d '{"name":"rm_rf","arguments":{}}' "http://$H/agent/call"
chk "agent inference pts" 'AI-5'                "http://$H/agent/inference-points"
chk "FULL DEMO RUN"      '"transcript"' -X POST --max-time 30 "http://$H/demo/run"

echo; echo "  $pass passed, $fail failed"; [ "$fail" -eq 0 ]
