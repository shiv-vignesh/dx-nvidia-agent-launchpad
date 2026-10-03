import test from "node:test";
import assert from "node:assert/strict";
import { createSpeechSession } from "../src/speech.js";
function setup() {
  let engine;
  const final = [],
    interim = [],
    states = [],
    errors = [];
  class FakeRecognition {
    constructor() {
      engine = this;
    }
    start() {
      this.onstart();
    }
    stop() {
      this.stopped = true;
    }
    abort() {
      this.aborted = true;
    }
  }
  const session = createSpeechSession(FakeRecognition, {
    onFinal: (t) => final.push(t),
    onInterim: (t) => interim.push(t),
    onState: (s) => states.push(s),
    onError: (e) => errors.push(e),
  });
  const result = (text, isFinal) =>
    Object.assign([{ transcript: text }], { isFinal });
  return {
    session,
    get engine() {
      return engine;
    },
    final,
    interim,
    states,
    errors,
    result,
  };
}
test("interim updates do not become saved text; repeated final events commit once", () => {
  const s = setup();
  s.session.start();
  s.engine.onresult({ results: [s.result("hello", false)] });
  assert.deepEqual(s.final, []);
  assert.equal(s.interim.at(-1), "hello");
  s.engine.onresult({
    results: [s.result("hello nurse", true), s.result("next", false)],
  });
  s.engine.onresult({
    results: [s.result("hello nurse", true), s.result("next patient", true)],
  });
  assert.deepEqual(s.final, ["hello nurse", "next patient"]);
  assert.equal(s.interim.at(-1), "");
  assert.equal(s.engine.continuous, true);
  assert.equal(s.engine.interimResults, true);
});
test("stop preserves final speech returned while shutting down", () => {
  const s = setup();
  s.session.start();
  s.session.stop();
  s.engine.onresult({ results: [s.result("last sentence", true)] });
  s.engine.onend();
  assert.deepEqual(s.final, ["last sentence"]);
  assert.equal(s.states.at(-1), "idle");
  assert.equal(s.engine.stopped, true);
});
test("permission failure is actionable and disposal removes callbacks", () => {
  const s = setup();
  s.session.start();
  s.engine.onerror({ error: "not-allowed" });
  s.engine.onend();
  assert.match(s.errors[0], /permission was denied/);
  assert.equal(s.states.at(-1), "idle");
  s.session.dispose();
  assert.equal(s.engine.onresult, null);
  assert.equal(s.engine.aborted, true);
});
