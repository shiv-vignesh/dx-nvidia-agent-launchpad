import test from "node:test";
import assert from "node:assert/strict";
import {
  initialRecords,
  decide,
  counts,
  incomingItems,
  timecode,
} from "../src/model.js";
test("report decisions remain isolated to their patient", () => {
  const records = initialRecords();
  const next = { ...records, 7: decide(records[7], "potassium", "added") };
  assert.deepEqual(records[7].decisions, {});
  assert.deepEqual(next[9].decisions, {});
  assert.equal(next[7].decisions.potassium, "added");
});
test("added items transfer to incoming report; dismissed suggestions do not", () => {
  let record = decide(initialRecords()[7], "potassium", "added");
  record = decide(record, "norepinephrine", "dismissed");
  assert.deepEqual(
    incomingItems(record).map((i) => i.id),
    ["recheck", "potassium"],
  );
});
test("review and receipt acknowledgement leave clinical tasks open", () => {
  const record = decide(initialRecords()[7], "potassium", "added");
  const acknowledged = {
    ...record,
    status: "given",
    acknowledged: true,
    reviewed: ["recheck", "potassium"],
  };
  assert.deepEqual(incomingItems(acknowledged), incomingItems(record));
});
test("progress counts change after delivery and acknowledgement without double counting", () => {
  const records = initialRecords();
  assert.deepEqual(counts(records), {
    new: 2,
    progress: 1,
    given: 1,
    acknowledged: 0,
  });
  records[7] = { ...records[7], status: "given", acknowledged: true };
  assert.deepEqual(counts(records), {
    new: 2,
    progress: 0,
    given: 2,
    acknowledged: 1,
  });
});
test("recording time is formatted across minute boundaries", () => {
  assert.equal(timecode(0), "00:00");
  assert.equal(timecode(252), "04:12");
  assert.equal(timecode(3600), "60:00");
});
