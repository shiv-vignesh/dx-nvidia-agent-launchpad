export const patients = [
  {
    id: "7",
    name: "J. M.",
    bed: 7,
    context: "Post-op day 3 · vent · 2 drips",
    mrn: "004 882 10",
    age: "58 F",
    attention: true,
  },
  {
    id: "9",
    name: "R. T.",
    bed: 9,
    context: "Sepsis · pressors weaning",
    mrn: "004 882 19",
    attention: false,
  },
  {
    id: "11",
    name: "A. K.",
    bed: 11,
    context: "DKA · insulin infusion",
    mrn: "004 882 21",
    attention: true,
  },
  {
    id: "12",
    name: "L. S.",
    bed: 12,
    context: "Post-arrest · cooling",
    mrn: "004 882 22",
    attention: false,
  },
];
export const transcript = [
  "Bed 7, day three post op. Sedation on propofol, RASS minus two overnight.",
  "Fall risk. Restraints came off at midnight and she settled after that.",
  "New peripheral line in the left forearm at 23:00, maintenance fluids running.",
  "Family called around 02:00, I updated the daughter.",
  "PEEP went up from 5 to 8 at about 03:40, she tolerated it.",
  "Vitals have been stable since.",
];
export const changes = [
  {
    id: "potassium",
    title: "Potassium 2.9, order changed",
    severity: "red",
    lines: [
      "02:10   Potassium 2.9 mmol/L (ref 3.5 to 5.1)",
      "05:00   Order changed: KCl 40 mEq IV over 4h",
    ],
    source: "Lab result and medication order",
    text: "KCl 40 mEq IV running, due to finish 09:00",
  },
  {
    id: "norepinephrine",
    title: "Norepinephrine titrated up twice",
    severity: "amber",
    lines: [
      "01:15   Increased to 0.06 mcg/kg/min",
      "04:50   Increased to 0.08 mcg/kg/min",
    ],
    source: "Infusion flowsheet",
    text: "Norepinephrine now 0.08 mcg/kg/min; titrated up twice overnight.",
  },
  {
    id: "orders",
    title: "Morning lab orders",
    severity: "teal",
    lines: [
      "01:40   CBC and BMP resulted",
      "Review the source record before adding to the report.",
    ],
    source: "Orders and results",
    text: "CBC and BMP resulted at 01:40; see chart for complete results.",
  },
  {
    id: "family",
    title: "Follow-up for next shift",
    severity: "teal",
    lines: [
      "02:00   Family update documented",
      "Review any follow-up requested in the chart.",
    ],
    source: "Nursing notes",
    text: "Family updated overnight. Review nursing notes for follow-up.",
  },
];
export const tasks = [
  {
    id: "recheck",
    time: "Due\n07:30",
    text: "Recheck potassium after KCl infusion completes",
    owner: "Day RN",
    status: "Open",
  },
  {
    id: "wean",
    time: "Due\n08:00",
    text: "Wean trial if MAP holds above 65",
    owner: "Day RN",
    status: "Open",
  },
  {
    id: "potassium",
    time: "02:10",
    text: "Potassium 2.9. Order changed 05:00, not in the verbal report",
    owner: "Night RN",
    status: "Needs review",
  },
];
export function initialRecords() {
  return Object.fromEntries(
    patients.map((p) => [
      p.id,
      {
        status: p.id === "9" ? "given" : p.id === "7" ? "progress" : "new",
        stage: p.id === "9" ? "delivered" : "home",
        seconds: 0,
        decisions: {},
        reviewed: [],
        questions: [],
        notes: "",
        saved: "06:47",
        acknowledged: false,
      },
    ]),
  );
}
export function decide(record, id, choice) {
  return { ...record, decisions: { ...record.decisions, [id]: choice } };
}
export function counts(records) {
  const list = Object.values(records);
  return {
    new: list.filter((r) => r.status === "new").length,
    progress: list.filter((r) => r.status === "progress").length,
    given: list.filter((r) => r.status === "given").length,
    acknowledged: list.filter((r) => r.acknowledged).length,
  };
}
export function timecode(seconds) {
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}
export function incomingItems(record) {
  const base = [
    {
      id: "recheck",
      time: "Due\n07:30",
      text: "Recheck potassium after KCl infusion finishes",
      added: false,
    },
  ];
  const added = changes
    .filter((c) => record.decisions[c.id] === "added")
    .map((c) => ({
      id: c.id,
      time: c.id === "potassium" ? "05:00" : "This shift",
      text: c.text,
      added: true,
    }));
  return [...base, ...added];
}
