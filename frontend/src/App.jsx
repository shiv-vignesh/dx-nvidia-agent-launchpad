import { chartCoverage } from "./coverage";
import React, { useEffect, useRef, useState } from "react";
import {
  House,
  Users,
  SignIn,
  ListBullets,
  MagnifyingGlass,
  Clock,
  Check,
  CircleDashed,
  Warning,
  Microphone,
  ArrowsLeftRight,
  CaretDown,
  ArrowRight,
  Plus,
  X,
  ChatCircle,
  Sparkle,
  WifiHigh,
  Pause,
  Play,
  ArrowSquareOut,
  FloppyDisk,
  SignOut,
  ArrowCounterClockwise,
  CaretRight,
  CheckCircle,
} from "@phosphor-icons/react";
import { Button, Badge, Tabs, Modal, Player, Empty } from "./components";
import * as api from "./api";
import {
  patients,
  transcript,
  changes,
  tasks,
  initialRecords,
  decide,
  counts,
  timecode,
  incomingItems,
} from "./model";
import { createSpeechSession } from "./speech";
const STORAGE = "carechart-demo-v1";
// Bed 7 in the designs is P-109 on the backend (SCHEMA.md: the handoff script as records).
const BACKEND_PID = { 7: "P-109" };
const preview = new URLSearchParams(window.location.search).get("screen");
function load() {
  if (preview) {
    const r = initialRecords();
    if (["recording", "review"].includes(preview)) {
      r["7"].seconds = 252;
      r["7"].stage = preview;
    }
    if (preview === "incoming") {
      for (const id of ["7", "9", "11", "12"])
        r[id] = {
          ...r[id],
          status: "given",
          stage: "delivered",
          delivered: "06:58",
        };
      r["9"].acknowledged = true;
      r["7"].decisions = { potassium: "added" };
    }
    return r;
  }
  try {
    const data = JSON.parse(localStorage.getItem(STORAGE));
    if (data?.version === 1 && patients.every((p) => data.records?.[p.id]))
      return data.records;
  } catch {}
  return initialRecords();
}
function savedSession() {
  try {
    const value = sessionStorage.getItem("carechart-session");
    return ["outgoing", "incoming"].includes(value) ? value : null;
  } catch {
    return null;
  }
}
export function App() {
  const [records, setRecords] = useState(load);
  const [selected, setSelected] = useState("7");
  const [view, setView] = useState(
    savedSession() === "incoming" ? "incoming" : "home",
  );
  const [role, setRole] = useState(savedSession() || "outgoing");
  const [nav, setNav] = useState(
    preview && preview !== "home" ? "Handoffs" : "My patients",
  );
  const [patientTab, setPatientTab] = useState("Handoff");
  const [reviewTab, setReviewTab] = useState("Not covered");
  const [incomingTab, setIncomingTab] = useState("What I need to know");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("Handoff status");
  const [sortChanged, setSortChanged] = useState(false);
  const [filter, setFilter] = useState("all");
  const [paused, setPaused] = useState(false);
  const [profile, setProfile] = useState(false);
  const [overview, setOverview] = useState(false);
  const [modal, setModal] = useState(null);
  const [question, setQuestion] = useState("");
  const [toast, setToast] = useState(null);
  const [loggedOut, setLoggedOut] = useState(() => !savedSession());
  const [loginRole, setLoginRole] = useState("outgoing");
  const [storageError, setStorageError] = useState(false);
  const [speechState, setSpeechState] = useState("idle");
  const [speechError, setSpeechError] = useState("");
  const [interim, setInterim] = useState("");
  const [speechConsent, setSpeechConsent] = useState(false);
  const speechSession = useRef(null);
  const speechSupported = Boolean(
    window.SpeechRecognition || window.webkitSpeechRecognition,
  );
  // Server-side coverage: real records via the backend, semantic comparison by Nemotron.
  const [live, setLive] = useState({
    hid: null,
    gaps: [],
    fields: {},
    engine: null,
    status: null,
    elapsed: null,
    error: null,
  });
  const toastTimer = useRef();
  const body = useRef();
  const active = patients.find((p) => p.id === selected);
  const record = records[selected];
  const count = counts(records);
  const isIncoming = role === "incoming";
  const isRecording = view === "recording";
  const name = isIncoming ? "M. Chen" : "A. Rivera";
  const actualIncoming = record.status === "given" || record.acknowledged;
  const availableIncoming = actualIncoming;
  const incomingRecord = record;
  const incoming = selected === "7" ? incomingItems(incomingRecord) : [];
  const pendingIncoming = incoming.filter(
    (i) => !record.reviewed.includes(i.id),
  );
  const liveChanges = live.gaps.map((g) => api.gapToChange(g, live.fields));
  const sourceChanges = liveChanges.length ? liveChanges : changes;
  const unresolved = sourceChanges.filter((c) => !record.decisions[c.id]);
  const homeTasks = tasks.filter(
    (t) => t.id !== "potassium" || !record.decisions.potassium,
  );
  const reviewedSections = record.acknowledged
    ? 5
    : record.status === "given" || record.stage === "review"
      ? 4
      : record.seconds
        ? 3
        : 2;
  const update = (patch) =>
    setRecords((prev) => ({
      ...prev,
      [selected]:
        typeof patch === "function"
          ? patch(prev[selected])
          : { ...prev[selected], ...patch },
    }));
  function notify(text) {
    setToast(text);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3800);
  }
  useEffect(() => () => clearTimeout(toastTimer.current), []);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE, JSON.stringify({ version: 1, records }));
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }, [records]);
  useEffect(() => {
    if (!isRecording || paused || speechState !== "listening") return;
    const id = setInterval(
      () =>
        setRecords((prev) => ({
          ...prev,
          [selected]: {
            ...prev[selected],
            seconds: prev[selected].seconds + 1,
          },
        })),
      1000,
    );
    return () => clearInterval(id);
  }, [isRecording, paused, selected, speechState]);
  useEffect(() => {
    body.current?.scrollTo({ top: 0 });
  }, [view, selected, patientTab, nav]);
  // Live coverage: deterministic gaps land immediately, Nemotron replaces them when it finishes.
  useEffect(() => {
    const pid = BACKEND_PID[selected];
    if (view !== "review" || !pid) return;
    let stop = false;
    let timer;
    (async () => {
      try {
        setLive((l) => ({ ...l, status: "loading", error: null }));
        await api.deriveTasks(pid).catch(() => {});
        const draft = await api.draftHandoff(pid);
        const hid = draft.id;
        const fields = {};
        for (const f of [
          ...draft.safety_block,
          ...Object.values(draft.ipass).flat(),
        ])
          fields[f.label] = f;
        if (draft.missing_required.length)
          await api.editField(
            hid,
            "baseline_weight",
            "74.8 kg (bed scale, 06:30)",
          );
        const spoken =
          records[selected]?.liveTranscript?.trim() || transcript.join(" ");
        const first = await api.startCoverage(hid, spoken);
        if (stop) return;
        setLive({
          hid,
          gaps: first.gaps,
          fields,
          engine: first.engine,
          status: first.status,
          elapsed: null,
          error: null,
        });
        const poll = async () => {
          if (stop) return;
          try {
            const next = await api.getCoverage(hid);
            if (stop) return;
            setLive((l) => ({
              ...l,
              gaps: next.gaps,
              engine: next.engine,
              status: next.status,
              elapsed: next.elapsed_s ?? null,
              error: next.model_error || null,
            }));
            if (next.engine !== "nemotron" && !next.model_error)
              timer = setTimeout(poll, 3000);
          } catch {
            timer = setTimeout(poll, 3000);
          }
        };
        timer = setTimeout(poll, 3000);
      } catch (e) {
        if (!stop)
          setLive((l) => ({
            ...l,
            status: "error",
            error: e.message || String(e),
          }));
      }
    })();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [view, selected]);
  useEffect(() => {
    if (!isRecording || paused || speechState !== "listening") return;
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isRecording, paused, speechState]);
  useEffect(() => {
    if (!profile) return;
    const fn = (e) => {
      if (!e.target.closest(".profile-wrap")) setProfile(false);
    };
    document.addEventListener("click", fn);
    return () => document.removeEventListener("click", fn);
  }, [profile]);
  useEffect(() => {
    if (!isRecording || paused || loggedOut) speechSession.current?.stop();
  }, [isRecording, paused, selected, loggedOut]);
  useEffect(() => () => speechSession.current?.dispose(), []);
  function beginSpeech() {
    if (!speechConsent) {
      notify(
        "Before starting, enable sample-only speech on the preparation screen.",
      );
      return false;
    }
    if (!speechSupported) {
      setSpeechError(
        "Live transcription is unavailable in this browser. Open this URL in Chrome, or type your transcript below.",
      );
      return false;
    }
    if (["starting", "listening", "stopping"].includes(speechState))
      return false;
    speechSession.current?.dispose();
    setSpeechError("");
    setInterim("");
    const patientId = selected;
    speechSession.current = createSpeechSession(
      window.SpeechRecognition || window.webkitSpeechRecognition,
      {
        onFinal: (text) =>
          setRecords((prev) => ({
            ...prev,
            [patientId]: {
              ...prev[patientId],
              transcript: [prev[patientId].transcript, text]
                .filter(Boolean)
                .join(" "),
            },
          })),
        onInterim: setInterim,
        onState: (state) => {
          setSpeechState(state);
          if (state === "idle") setPaused(true);
        },
        onError: setSpeechError,
      },
    );
    speechSession.current.start();
    return true;
  }
  function toggleSpeech() {
    if (speechState === "listening" || speechState === "starting") {
      speechSession.current?.stop();
      setPaused(true);
    } else if (beginSpeech()) setPaused(false);
  }
  function save() {
    update({
      saved: new Date().toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      stage: isRecording ? "recording" : record.stage,
    });
    if (isRecording) setPaused(true);
    notify(
      storageError
        ? "Draft kept for this session. Browser storage is unavailable."
        : "Draft saved on this browser.",
    );
  }
  function move(next) {
    if (
      !isIncoming &&
      record.status === "given" &&
      ["prepare", "recording", "review", "incoming"].includes(next)
    )
      next = "delivered";
    if (isRecording && !paused && next !== "review") {
      setPaused(true);
      update({ stage: "recording" });
      notify("Recording paused. Your draft is saved.");
    }
    window.speechSynthesis?.cancel();
    setView(next);
    setPatientTab("Handoff");
    setNav(next === "home" ? "My patients" : "Handoffs");
  }
  function selectPatient(id) {
    if (id === selected) return;
    if (isRecording) {
      setPaused(true);
      notify("Recording paused and saved before switching patients.");
    }
    window.speechSynthesis?.cancel();
    setSelected(id);
    setOverview(false);
    setPatientTab("Handoff");
    setView(
      isIncoming
        ? "incoming"
        : records[id].status === "given"
          ? "delivered"
          : "home",
    );
  }
  function resume() {
    if (isIncoming) {
      move("incoming");
      return;
    }
    move(
      record.stage === "recording"
        ? "prepare"
        : record.stage === "review"
          ? "review"
          : record.status === "given"
            ? "delivered"
            : "prepare",
    );
  }
  function start() {
    if (!beginSpeech()) return;
    update({ status: "progress", stage: "recording", liveTranscript: true });
    setPaused(false);
    move("recording");
  }
  function stop() {
    speechSession.current?.stop();
    update({ stage: "review", status: "progress" });
    setPaused(false);
    move("review");
    setReviewTab("Transcript");
  }
  function login(next) {
    if (!loggedOut) return;
    try {
      sessionStorage.setItem("carechart-session", next);
    } catch {}
    setLoggedOut(false);
    setSelected(
      patients.find(
        (p) =>
          next === "incoming" &&
          records[p.id].status === "given" &&
          !records[p.id].acknowledged,
      )?.id || "7",
    );
    setSearch("");
    setModal(null);
    setSpeechConsent(false);
    setSpeechError("");
    setInterim("");
    if (isRecording) setPaused(true);
    window.speechSynthesis?.cancel();
    setRole(next);
    setView(next === "incoming" ? "incoming" : "home");
    setNav(next === "incoming" ? "Handoffs" : "My patients");
    setProfile(false);
    setPatientTab("Handoff");
    setFilter("all");
  }
  function logout() {
    speechSession.current?.stop();
    window.speechSynthesis?.cancel();
    setPaused(true);
    setModal(null);
    setProfile(false);
    setToast(null);
    setSpeechConsent(false);
    try {
      sessionStorage.removeItem("carechart-session");
    } catch {}
    setLoggedOut(true);
  }
  function decision(id, value) {
    update((r) => decide(r, id, value));
    notify(
      value === "added"
        ? "Added to the report."
        : "Suggestion dismissed. You can undo this below.",
    );
  }
  function deliver() {
    if (isIncoming || record.status === "given") return;
    update({
      status: "given",
      stage: "delivered",
      signedBy: "A. Rivera, RN",
      signedAt: new Date().toISOString(),
      delivered: new Date().toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    });
    setModal(null);
    move("delivered");
    notify("Handoff signed by A. Rivera and sent to M. Chen’s demo dashboard.");
  }
  const statusLabel = (p) => {
    const r = records[p.id];
    if (isIncoming)
      return r.acknowledged
        ? "Acknowledged"
        : p.id === selected && availableIncoming
          ? "Reviewing"
          : r.status === "given"
            ? "Received"
            : "Awaiting report";
    return r.acknowledged
      ? "Acknowledged"
      : r.status === "given"
        ? "Report given"
        : r.status === "progress"
          ? "In progress"
          : "Not started";
  };
  let listed = patients.filter(
    (p) =>
      `${p.name} ${p.bed} ${p.mrn}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (filter === "all" || filter === "acknowledged"
        ? filter === "all" || records[p.id].acknowledged
        : records[p.id].status === filter),
  );
  if (sort === "Handoff status" && sortChanged)
    listed = [...listed].sort(
      (a, b) =>
        ({ progress: 0, new: 1, given: 2 })[records[a.id].status] -
        { progress: 0, new: 1, given: 2 }[records[b.id].status],
    );
  if (sort === "Bed") listed = [...listed].sort((a, b) => a.bed - b.bed);
  if (sort === "Needs attention")
    listed = [...listed].sort(
      (a, b) => Number(b.attention) - Number(a.attention),
    );
  const reportText = record.liveTranscript
    ? [record.transcript, record.notes].filter(Boolean).join(" ")
    : selected === "7"
      ? [
          ...transcript,
          ...changes
            .filter((c) => record.decisions[c.id] === "added")
            .map((c) => c.text),
          record.notes,
        ]
          .filter(Boolean)
          .join(" ")
      : record.notes ||
        `Sample handoff for bed ${active.bed}, ${active.name}. ${active.context}.`;
  function source(id) {
    setModal({
      type: "source",
      item: changes.find((c) => c.id === id) || changes[0],
    });
  }
  if (loggedOut)
    return (
      <div className="signed-out">
        <div className="login-card">
          <h1>CareChart</h1>
          <h2>Sign in to your shift</h2>
          <p>
            Choose your demo nurse account. Each nurse has a separate workspace;
            signed reports are available to the receiving nurse.
          </p>
          <label htmlFor="nurse-account">Nurse account</label>
          <select
            id="nurse-account"
            value={loginRole}
            onChange={(e) => setLoginRole(e.target.value)}
          >
            <option value="outgoing">
              A. Rivera, RN · Outgoing · Night shift
            </option>
            <option value="incoming">M. Chen, RN · Incoming · Day shift</option>
          </select>
          <Button primary icon={SignIn} onClick={() => login(loginRole)}>
            Sign in
          </Button>
          <small>Demo sign-in · No password or real authentication</small>
        </div>
      </div>
    );
  return (
    <div className="app-shell">
      <a href="#workspace" className="skip-link">
        Skip to patient workspace
      </a>
      <header className="global-header">
        <strong className="wordmark">CareChart</strong>
        <div className="unit">
          4 West ICU{" "}
          <em>
            {isIncoming
              ? "Day shift 07:00 to 19:00"
              : "Night shift 19:00 to 07:00"}
          </em>
        </div>
        <div
          className="profile-wrap"
          onKeyDown={(e) => {
            if (e.key === "Escape") setProfile(false);
          }}
        >
          <button
            className="profile"
            onClick={() => setProfile(!profile)}
            aria-expanded={profile}
          >
            <img src="/assets/nurse.png" alt="" />
            <span>
              {name}, RN<em>ID {isIncoming ? "51904" : "48812"}</em>
            </span>
            <CaretDown size={12} />
          </button>
          {profile && (
            <div className="profile-menu">
              <span className="eyebrow">Signed in as {name}, RN</span>
              <p>
                {isIncoming
                  ? "Incoming nurse · Day shift"
                  : "Outgoing nurse · Night shift"}
              </p>
              <hr />
              <button
                onClick={() => {
                  setProfile(false);
                  setModal({ type: "reset" });
                }}
              >
                <ArrowCounterClockwise size={17} />
                Reset demo
              </button>
            </div>
          )}
        </div>
        <Button className="logout" onClick={logout}>
          Log out
        </Button>
      </header>
      <nav className="global-nav" aria-label="Main navigation">
        {[
          ["Home", House],
          ["My patients", Users],
          ["Handoffs", SignIn],
          ["Worklist", ListBullets],
        ].map(([label, Icon]) => (
          <button
            className={nav === label ? "active" : ""}
            key={label}
            onClick={() => {
              if (label === "Handoffs") resume();
              else {
                if (isRecording) {
                  setPaused(true);
                  notify("Recording paused. Draft saved.");
                }
                window.speechSynthesis?.cancel();
                setNav(label);
                setPatientTab("Handoff");
                setView(isIncoming ? "incoming" : "home");
              }
            }}
          >
            <Icon size={17} />
            {label}
            {label === "Handoffs" && (
              <Badge tone={isRecording ? "red" : isIncoming ? "amber" : ""}>
                {isRecording ? (
                  <>
                    <span className="record-dot" />
                    Recording
                  </>
                ) : isIncoming ? (
                  `${count.given - count.acknowledged} to acknowledge`
                ) : (
                  `${count.new + count.progress} to give`
                )}
              </Badge>
            )}
          </button>
        ))}
      </nav>
      <section className="assignment">
        <div>
          <h1>My assignment</h1>
          <div className="stats">
            {(isIncoming
              ? [
                  [4, "assigned", "all"],
                  [count.given, "handoffs received", "given"],
                  [count.acknowledged, "acknowledged", "acknowledged"],
                  [
                    patients.filter((p) => p.attention).length,
                    "with open items",
                    "attention",
                  ],
                ]
              : [
                  [4, "assigned", "all"],
                  [count.new, "not started", "new"],
                  [count.progress, "in progress", "progress"],
                  [count.given, "report given", "given"],
                  [count.acknowledged, "acknowledged", "acknowledged"],
                ]
            ).map(([n, label, key]) => (
              <button
                key={key}
                className={`stat ${filter === key && key !== "all" ? "selected" : ""}`}
                onClick={() =>
                  key === "attention"
                    ? setSort("Needs attention")
                    : setFilter(filter === key ? "all" : key)
                }
              >
                <strong
                  className={
                    key === "given" || key === "acknowledged" ? "green" : ""
                  }
                >
                  {n}
                </strong>
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="assignment-action">
          <p>
            {isIncoming
              ? "Shift started 07:00 · " +
                (count.given - count.acknowledged) +
                " handoffs to acknowledge"
              : "Shift ends at 07:00 · 12 min remaining"}
          </p>
          <Button primary icon={ArrowsLeftRight} onClick={resume}>
            {isIncoming
              ? "Review handoff"
              : record.status === "given"
                ? "View handoff"
                : record.status === "new"
                  ? "Start handoff"
                  : "Resume handoff"}
            <span>· Bed {active.bed}</span>
          </Button>
        </div>
      </section>
      <div className="workspace">
        <aside className="sidebar" aria-label="Patient assignment">
          <div className="patient-filters">
            <label htmlFor="patient-search">Find patient</label>
            <div className="search">
              <MagnifyingGlass size={16} />
              <input
                id="patient-search"
                placeholder="Name, MRN or bed"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button aria-label="Clear search" onClick={() => setSearch("")}>
                  <X size={14} />
                </button>
              )}
            </div>
            <div className="sort">
              <label htmlFor="sort">Sort by</label>
              <select
                id="sort"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value);
                  setSortChanged(true);
                }}
              >
                <option>Handoff status</option>
                <option>Bed</option>
                <option>Needs attention</option>
              </select>
            </div>
            {filter !== "all" && (
              <button
                className="text-button clear-filter"
                onClick={() => setFilter("all")}
              >
                Clear status filter <X size={12} />
              </button>
            )}
          </div>
          <div className="patient-list">
            {listed.map((p) => {
              const label = statusLabel(p);
              return (
                <button
                  key={p.id}
                  className={`patient-row ${p.id === selected ? "selected" : ""}`}
                  onClick={() => selectPatient(p.id)}
                  aria-pressed={p.id === selected}
                >
                  <strong>
                    Bed {p.bed} · {p.name}
                  </strong>
                  <span className="patient-context">{p.context}</span>
                  <span className="patient-badges">
                    <Badge
                      tone={
                        ["Report given", "Acknowledged"].includes(label)
                          ? "green"
                          : ["In progress", "Reviewing"].includes(label)
                            ? "teal"
                            : ""
                      }
                      icon={
                        ["Report given", "Acknowledged"].includes(label)
                          ? Check
                          : ["In progress", "Reviewing"].includes(label)
                            ? Clock
                            : CircleDashed
                      }
                    >
                      {label}
                    </Badge>
                    {p.attention && (
                      <span className="attention">
                        <Warning size={13} />
                        Needs attention
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
            {!listed.length && (
              <div className="search-empty">
                <p>No patients found.</p>
                <button
                  className="text-button"
                  onClick={() => {
                    setSearch("");
                    setFilter("all");
                  }}
                >
                  Clear filters
                </button>
              </div>
            )}
          </div>
        </aside>
        <main id="workspace" className="patient-workspace" tabIndex={-1}>
          <div className="patient-banner">
            <div className="patient-title">
              <h2>{active.name}</h2>
              <span>
                Bed {active.bed} · 4 West ICU {active.age && `· ${active.age}`}{" "}
                · MRN {active.mrn}
              </span>
              <Button
                onClick={() => setOverview(!overview)}
                aria-expanded={overview}
              >
                Overview
                <CaretDown size={12} />
              </Button>
            </div>
            <div className="safety">
              <span>
                Code status{" "}
                <strong>{selected === "7" ? "Full code" : "See chart"}</strong>
              </span>
              <span>
                Allergies{" "}
                <strong>
                  {selected === "7" ? "No allergies recorded" : "See chart"}
                </strong>
              </span>
              <span>
                Isolation{" "}
                <strong className="teal">
                  {selected === "7" ? "Contact" : "See chart"}
                </strong>
              </span>
            </div>
            {overview && (
              <div className="overview-popover">
                <h3>Patient overview</h3>
                <p>{active.context}</p>
                {selected === "7" ? (
                  <dl>
                    <dt>Admitted</dt>
                    <dd>29 Sep · Post-op day 3</dd>
                    <dt>Weight</dt>
                    <dd>74 kg</dd>
                    <dt>Lines</dt>
                    <dd>PIV left forearm · A-line right radial</dd>
                    <dt>Drips</dt>
                    <dd>Norepinephrine · Propofol</dd>
                    <dt>Vent</dt>
                    <dd>PC · PEEP 8 · FiO₂ 40%</dd>
                    <dt>Fall risk</dt>
                    <dd>High</dd>
                  </dl>
                ) : (
                  <p>Additional chart details are not included in this demo.</p>
                )}
                <Button onClick={() => setOverview(false)}>
                  Close overview
                </Button>
              </div>
            )}
          </div>
          <div className="patient-tabs">
            <Tabs
              items={[
                "Handoff",
                "Chart Review",
                "MAR",
                "Flowsheets",
                "Notes",
                "Results",
              ]}
              value={patientTab}
              onChange={(t) => {
                if (isRecording) {
                  setPaused(true);
                  notify("Recording paused while you review the chart.");
                }
                window.speechSynthesis?.cancel();
                setPatientTab(t);
              }}
              label="Patient chart"
            />
          </div>
          <div className="main-scroll" ref={body}>
            <div
              className="screen-enter"
              key={`${view}-${selected}-${patientTab}-${nav}`}
            >
              {nav === "Worklist" ? (
                <>
                  <h2 className="section-page-title">My worklist</h2>
                  <p className="muted">
                    Open follow-ups for your assignment. Reviewing a handoff
                    does not complete these tasks.
                  </p>
                  <TaskRows
                    items={tasks}
                    onSource={source}
                    onReview={() => {
                      selectPatient("7");
                      setNav("My patients");
                    }}
                    worklist
                  />
                </>
              ) : patientTab !== "Handoff" ? (
                <ChartPanel
                  tab={patientTab}
                  selected={selected}
                  record={record}
                  update={update}
                  readOnly={isIncoming || record.status === "given"}
                  source={source}
                />
              ) : (
                <>
                  {view === "home" && (
                    <>
                      <section className="handoff-prep panel">
                        <div className="split">
                          <h3>Handoff preparation</h3>
                          <span className="muted">
                            Draft saved {record.saved}
                          </span>
                        </div>
                        <p className="muted">
                          A. Rivera, RN <ArrowRight size={13} /> M. Chen, RN{" "}
                          <span>·</span> Bed {active.bed}, {active.name}{" "}
                          <span>·</span> Night shift 19:00 to 07:00
                        </p>
                        <div className="progress-label">
                          {record.status === "given"
                            ? record.acknowledged
                              ? "Handoff acknowledged · Follow-up tasks remain open"
                              : "Report delivered · Awaiting acknowledgement"
                            : selected === "7"
                              ? `Reviewed ${reviewedSections} of 5 sections · ${homeTasks.length} items still unresolved`
                              : "Ready to prepare this patient’s report"}
                        </div>
                        <progress
                          value={reviewedSections}
                          max="5"
                          aria-label="Handoff preparation progress"
                        />
                        <div className="automation-note">
                          <Sparkle size={15} />
                          <span>
                            Suggested by Handoff Check, an automated comparison
                            against the chart. Not clinically verified. Every
                            item links to its source record and can be
                            corrected.
                          </span>
                        </div>
                        <div className="steps">
                          {[
                            "Review",
                            "Give report",
                            "Address open items",
                            "Receipt status",
                          ].map((s, i) => (
                            <button
                              key={s}
                              className={i === 0 ? "complete" : ""}
                              onClick={() =>
                                i === 0
                                  ? body.current
                                      ?.querySelector("#attention")
                                      ?.scrollIntoView({
                                        behavior: window.matchMedia(
                                          "(prefers-reduced-motion: reduce)",
                                        ).matches
                                          ? "instant"
                                          : "smooth",
                                        block: "start",
                                      })
                                  : i === 1
                                    ? resume()
                                    : i === 2
                                      ? record.seconds
                                        ? move("review")
                                        : notify(
                                            "Record a report first to compare it with chart changes.",
                                          )
                                      : record.status === "given"
                                        ? move("delivered")
                                        : notify(
                                            "The incoming nurse can acknowledge receipt after signing in to her dashboard.",
                                          )
                              }
                            >
                              {i + 1}. {s}
                            </button>
                          ))}
                        </div>
                      </section>
                      <h3 id="attention" className="section-title">
                        <Warning className="red" size={19} />
                        Needs attention{" "}
                        <small>
                          {selected === "7"
                            ? `${homeTasks.length} unresolved`
                            : active.attention
                              ? "Review chart"
                              : "No open items"}
                        </small>
                      </h3>
                      {selected === "7" ? (
                        <TaskRows items={homeTasks} onSource={source} />
                      ) : (
                        <Empty
                          title={
                            active.attention
                              ? "Review this patient’s chart"
                              : "No open handoff items"
                          }
                        >
                          The supplied designs include detailed chart data for
                          Bed 7. Other patient records are intentionally
                          limited.
                        </Empty>
                      )}
                      <h3 className="section-title">Changes this shift</h3>
                      <div className="panel detail-summary">
                        <p>{active.context}</p>
                        <Button
                          onClick={() => setPatientTab("Chart Review")}
                          icon={ArrowSquareOut}
                        >
                          Review chart
                        </Button>
                      </div>
                    </>
                  )}
                  {view === "prepare" && (
                    <>
                      <section className="record-ready panel">
                        <h2>Ready to record report</h2>
                        <p className="muted">
                          A. Rivera, RN <ArrowRight size={14} /> M. Chen, RN{" "}
                          <span>·</span> Bed {active.bed}, {active.name}{" "}
                          <span>·</span> Night shift 19:00 to 07:00
                        </p>
                        <img
                          className="waveform idle"
                          src="/assets/waveform.svg"
                          alt=""
                        />
                        <strong className="ready-timer">
                          {timecode(record.seconds)}
                        </strong>
                        <label className="speech-consent">
                          <input
                            type="checkbox"
                            checked={speechConsent}
                            onChange={(e) => setSpeechConsent(e.target.checked)}
                          />
                          Enable microphone for sample-only speech. My browser
                          may send audio to its speech service. Do not use real
                          patient information.
                        </label>
                        <Button
                          primary
                          className="record-start"
                          icon={Microphone}
                          onClick={start}
                        >
                          {record.seconds
                            ? "Resume recording"
                            : "Start recording"}
                        </Button>
                        <p className="muted">
                          Speak as you normally would. Nothing to fill in.
                        </p>

                        <p className="muted">
                          Live English transcription · Audio is not saved
                        </p>
                        {!speechSupported && (
                          <p role="status">
                            Live transcription is unavailable in this browser.
                            Open this page in Chrome, or enter a typed report
                            below.
                          </p>
                        )}
                        {speechError && <p role="alert">{speechError}</p>}
                        <label htmlFor="typed-transcript">
                          Transcript draft
                        </label>
                        <textarea
                          id="typed-transcript"
                          rows="3"
                          value={record.transcript || ""}
                          onChange={(e) =>
                            update({
                              transcript: e.target.value,
                              liveTranscript: true,
                            })
                          }
                          placeholder="You can also type your report here…"
                        />
                        <Button
                          onClick={() => {
                            update({ liveTranscript: true });
                            stop();
                          }}
                        >
                          Review typed report
                        </Button>
                      </section>
                      <CoveragePanel patient={selected} text={record.transcript || ""} />
                    </>
                  )}
                  {view === "recording" && (
                    <>
                      <section
                        className={`recording-bar panel ${speechState !== "listening" ? "paused" : ""}`}
                      >
                        <span className="record-dot" />
                        <strong>
                          {speechState === "listening"
                            ? "Listening"
                            : speechState === "starting"
                              ? "Connecting…"
                              : speechState === "stopping"
                                ? "Finishing…"
                                : "Paused"}
                        </strong>
                        <img
                          className={`waveform ${speechState !== "listening" ? "idle" : "live"}`}
                          src="/assets/waveform.svg"
                          alt={paused ? "" : "Animated recording indicator"}
                        />
                        <strong className="timer">
                          {timecode(record.seconds)}
                        </strong>
                        <Button
                          icon={paused ? Play : Pause}
                          onClick={toggleSpeech}
                          disabled={speechState === "stopping"}
                        >
                          {paused ? "Resume" : "Pause"}
                        </Button>
                        <span className="demo-label">
                          Live speech · Audio not saved
                        </span>
                      </section>
                      <div className="recording-columns">
                        <section className="panel transcript">
                          <h3>Live transcript</h3>
                          {speechError && <p role="alert">{speechError}</p>}
                          <p className="preserve-lines">
                            {record.transcript ||
                              "Your words will appear here when you speak."}
                          </p>
                          {interim && (
                            <p
                              className="muted"
                              aria-label="Provisional transcript"
                            >
                              {interim}
                            </p>
                          )}
                          <p role="status" className="muted faint">
                            {speechState === "listening"
                              ? "Listening to your microphone…"
                              : speechState === "starting"
                                ? "Waiting for microphone permission and speech service…"
                                : "Microphone paused. Resume to continue."}
                          </p>
                        </section>
                        <CoveragePanel patient={selected} text={record.transcript || ""} interim={interim} />
                      </div>
                    </>
                  )}
                  {view === "review" && (
                    <>
                      {record.liveTranscript && <CoveragePanel patient={selected} text={record.transcript || ""} />}
                      <section className="panel audio-panel">
                        <Player
                          key={selected}
                          duration={record.seconds || 252}
                          text={reportText}
                        />
                      </section>
                      <Tabs
                        items={[
                          "Report summary",
                          {
                            id: "Not covered",
                            label: `${record.liveTranscript ? "Chart reference" : "Not covered"} · ${selected === "7" ? unresolved.length : 0}${
                              live.engine === "nemotron"
                                ? " · Nemotron"
                                : live.engine === "deterministic"
                                  ? " · keyword match, asking Nemotron…"
                                  : ""
                            }`,
                          },
                          "Transcript",
                        ]}
                        value={reviewTab}
                        onChange={setReviewTab}
                        label="Report review"
                      />
                      {reviewTab === "Not covered" ? (
                        <>
                          <p className="review-description">
                            {record.liveTranscript
                              ? "These are sample chart changes for manual review. Your speech has not been checked against the chart. Add relevant context for the next nurse."
                              : "These changes are in the sample chart for this shift. Add what the next nurse needs, dismiss the rest."}
                          </p>
                          {selected === "7" && unresolved.length ? (
                            <div className="panel suggestions">
                              {unresolved.map((c) => (
                                <article
                                  key={c.id}
                                  className={`suggestion ${c.severity}`}
                                >
                                  <h4>{c.title}</h4>
                                  {c.lines.map((line) => (
                                    <p key={line}>{line}</p>
                                  ))}
                                  <p className="source-line">
                                    <Sparkle size={13} />
                                    <em>Suggested by Handoff Check</em>
                                    <button
                                      className="text-button"
                                      onClick={() => source(c.id)}
                                    >
                                      View in chart
                                    </button>
                                  </p>
                                  <div className="button-row">
                                    <Button
                                      primary
                                      icon={Plus}
                                      onClick={() => decision(c.id, "added")}
                                    >
                                      Add to report
                                    </Button>
                                    <Button
                                      icon={Microphone}
                                      onClick={() => {
                                        setModal({ type: "say", item: c });
                                        setQuestion(c.text);
                                      }}
                                    >
                                      Say it now
                                    </Button>
                                    <Button
                                      icon={X}
                                      onClick={() =>
                                        decision(c.id, "dismissed")
                                      }
                                    >
                                      Not relevant
                                    </Button>
                                  </div>
                                </article>
                              ))}
                            </div>
                          ) : (
                            <Empty title="All suggestions reviewed">
                              Your report is ready for a final check before
                              delivery.
                            </Empty>
                          )}
                          {Object.keys(record.decisions).length > 0 && (
                            <section className="resolved panel">
                              <h3>Reviewed suggestions</h3>
                              {changes
                                .filter((c) => record.decisions[c.id])
                                .map((c) => (
                                  <div className="resolved-row" key={c.id}>
                                    <CheckCircle size={17} className="green" />
                                    <span>
                                      {c.title}
                                      <small>
                                        {record.decisions[c.id] === "added"
                                          ? "Added to report"
                                          : "Dismissed as not relevant"}
                                      </small>
                                    </span>
                                    <button
                                      className="text-button"
                                      onClick={() =>
                                        update((r) => {
                                          const decisions = { ...r.decisions };
                                          delete decisions[c.id];
                                          return { ...r, decisions };
                                        })
                                      }
                                    >
                                      Undo
                                    </button>
                                  </div>
                                ))}
                            </section>
                          )}
                        </>
                      ) : reviewTab === "Transcript" ? (
                        <section className="panel report-content">
                          <h3>Report transcript</h3>
                          <p className="muted">
                            Review and correct the transcript before delivery.
                            Playback uses synthesized speech; microphone audio
                            is not saved.
                          </p>
                          <label htmlFor="report-notes">
                            Additional notes or corrections
                          </label>
                          <textarea
                            id="report-notes"
                            rows="4"
                            value={record.notes}
                            placeholder="Add context for the incoming nurse…"
                            onChange={(e) => update({ notes: e.target.value })}
                          />
                          {record.liveTranscript ? (
                            <>
                              <label htmlFor="final-transcript">
                                Your transcript
                              </label>
                              <textarea
                                id="final-transcript"
                                rows="8"
                                value={record.transcript || ""}
                                onChange={(e) =>
                                  update({ transcript: e.target.value })
                                }
                              />
                            </>
                          ) : (
                            selected === "7" &&
                            transcript.map((p) => <p key={p}>{p}</p>)
                          )}
                        </section>
                      ) : (
                        <ReportSummary
                          selected={selected}
                          record={record}
                          active={active}
                        />
                      )}
                    </>
                  )}
                  {(view === "incoming" || view === "delivered") && (
                    <>
                      {view === "delivered" && !isIncoming ? (
                        <section className="delivered panel">
                          <CheckCircle size={34} />
                          <div>
                            <h3>
                              {record.acknowledged
                                ? "Handoff acknowledged"
                                : "Handoff signed and sent to M. Chen"}
                            </h3>
                            <p>
                              Bed {active.bed} · {active.name} ·{" "}
                              {record.acknowledged
                                ? "Receipt confirmed. Open follow-ups remain on the worklist."
                                : "Signed by A. Rivera, RN. You can log out when your shift is complete. M. Chen will sign in separately to acknowledge receipt."}
                            </p>
                          </div>
                          <Button onClick={logout} icon={SignOut}>
                            Log out
                          </Button>
                        </section>
                      ) : null}
                      {!availableIncoming && isIncoming ? (
                        <Empty title="Waiting for a handoff">
                          No report has been delivered for Bed {active.bed} yet.
                          <br />
                          The outgoing nurse has not signed and sent this report
                          yet. It will be available here once sent.
                        </Empty>
                      ) : isIncoming ? (
                        <>
                          <section className="received panel">
                            <div className="split">
                              <div>
                                <h3>
                                  {isIncoming
                                    ? "Handoff received"
                                    : "Delivered report"}
                                </h3>
                                <p className="muted">
                                  From A. Rivera, RN · night shift 19:00 to
                                  07:00 · delivered{" "}
                                  {record.delivered || "06:58"}
                                </p>
                              </div>
                              <Badge
                                tone={record.acknowledged ? "green" : "amber"}
                                icon={record.acknowledged ? Check : Warning}
                              >
                                {record.acknowledged
                                  ? "Acknowledged"
                                  : "Not acknowledged"}
                              </Badge>
                            </div>
                            <Player
                              key={`in-${selected}`}
                              report
                              text={reportText}
                              duration={record.seconds || 252}
                            />
                          </section>
                          <Tabs
                            items={[
                              "What I need to know",
                              "Full report",
                              "Transcript",
                            ]}
                            value={incomingTab}
                            onChange={setIncomingTab}
                            label="Received report"
                          />
                          {incomingTab === "What I need to know" ? (
                            <>
                              <h3 className="section-title">
                                <Warning className="red" size={19} />
                                Needs attention{" "}
                                <small>
                                  {incoming.length} open
                                  {incoming.some((i) => i.added)
                                    ? ", " +
                                      incoming.filter((i) => i.added).length +
                                      " added after the report"
                                    : ""}
                                </small>
                              </h3>
                              {incoming.length ? (
                                <div className="panel incoming-tasks">
                                  {incoming.map((item) => (
                                    <article
                                      className="incoming-task"
                                      key={item.id}
                                    >
                                      <span className="task-time">
                                        {item.time}
                                      </span>
                                      <div>
                                        <p>{item.text}</p>
                                        <p className="source-line">
                                          {item.added && <Sparkle size={13} />}
                                          <em>
                                            {item.added
                                              ? "Added by A. Rivera after review"
                                              : "In the verbal report"}
                                          </em>
                                          {item.added && (
                                            <button
                                              className="text-button"
                                              onClick={() => source(item.id)}
                                            >
                                              View in chart
                                            </button>
                                          )}
                                        </p>
                                        <div className="button-row">
                                          <Button
                                            primary={
                                              !record.reviewed.includes(item.id)
                                            }
                                            icon={Check}
                                            onClick={() => {
                                              update((r) => ({
                                                ...r,
                                                reviewed: r.reviewed.includes(
                                                  item.id,
                                                )
                                                  ? r.reviewed.filter(
                                                      (i) => i !== item.id,
                                                    )
                                                  : [...r.reviewed, item.id],
                                              }));
                                            }}
                                          >
                                            {record.reviewed.includes(item.id)
                                              ? "Reviewed · Undo"
                                              : "Mark reviewed"}
                                          </Button>
                                          <Button
                                            icon={ChatCircle}
                                            onClick={() => {
                                              setQuestion("");
                                              setModal({
                                                type: "question",
                                                item,
                                              });
                                            }}
                                          >
                                            Ask A. Rivera
                                          </Button>
                                        </div>
                                      </div>
                                      <span className="muted">You</span>
                                      <span className="red">Open</span>
                                    </article>
                                  ))}
                                </div>
                              ) : (
                                <Empty title="No open items in this report">
                                  Review the full report before acknowledging
                                  receipt.
                                </Empty>
                              )}
                              {record.questions.length > 0 && (
                                <div className="panel question-history">
                                  <h3>Questions for A. Rivera</h3>
                                  {record.questions.map((q, i) => (
                                    <p key={i}>
                                      <ChatCircle size={15} />
                                      {q}
                                      <Badge>Awaiting reply · Demo</Badge>
                                    </p>
                                  ))}
                                </div>
                              )}
                              <p className="review-note">
                                Marking an item reviewed confirms you’ve seen
                                it. The clinical task stays open.
                              </p>
                            </>
                          ) : incomingTab === "Full report" ? (
                            <ReportSummary
                              selected={selected}
                              record={record}
                              active={active}
                            />
                          ) : (
                            <section className="panel report-content">
                              <h3>Report transcript</h3>
                              {record.liveTranscript ? (
                                <p className="preserve-lines">
                                  {record.transcript ||
                                    "No transcript provided."}
                                </p>
                              ) : selected === "7" ? (
                                transcript.map((p) => <p key={p}>{p}</p>)
                              ) : (
                                <p>{reportText}</p>
                              )}
                              {record.notes && <p>{record.notes}</p>}
                            </section>
                          )}
                        </>
                      ) : null}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
          <footer className="action-bar">
            <div>
              <strong>
                Patient {patients.findIndex((p) => p.id === selected) + 1} of 4
              </strong>
              <span>
                {storageError
                  ? "Draft not saved to browser."
                  : isIncoming
                    ? !availableIncoming
                      ? "Waiting for report."
                      : record.acknowledged
                        ? "Acknowledged. Follow-up tasks remain open."
                        : `Received ${record.delivered || "06:58"}. ${incoming.length} items still open.`
                    : view === "recording"
                      ? `${speechState === "listening" ? "Listening" : speechState === "starting" ? "Connecting…" : speechState === "stopping" ? "Finishing…" : "Paused"}. Demo audio is not captured.`
                      : view === "prepare"
                        ? "Not started. Nothing recorded yet."
                        : view === "review"
                          ? `Recorded ${timecode(record.seconds)}. Draft saved, not yet delivered.`
                          : record.status === "given"
                            ? "Delivered. " +
                              (record.acknowledged
                                ? "Receipt acknowledged."
                                : "Awaiting receipt.")
                            : `Draft saved ${record.saved}. Not yet delivered.`}
              </span>
            </div>
            <div className="footer-buttons">
              {isIncoming ? (
                <>
                  <Button
                    icon={ChatCircle}
                    disabled={!availableIncoming}
                    onClick={() => {
                      setQuestion("");
                      setModal({ type: "question" });
                    }}
                  >
                    Ask a question
                  </Button>
                  <Button
                    primary
                    icon={Check}
                    disabled={!availableIncoming || record.acknowledged}
                    onClick={() => setModal({ type: "acknowledge" })}
                  >
                    {record.acknowledged
                      ? "Handoff acknowledged"
                      : "Acknowledge handoff"}
                  </Button>
                </>
              ) : record.status === "given" ? (
                <>
                  <Button onClick={logout} icon={SignOut}>
                    Log out
                  </Button>
                  <Button
                    primary
                    icon={ArrowRight}
                    onClick={() => {
                      const next = patients.find(
                        (p) => records[p.id].status !== "given",
                      );
                      if (next) {
                        selectPatient(next.id);
                        setView("prepare");
                      } else
                        notify(
                          "All reports delivered. Waiting for acknowledgements.",
                        );
                    }}
                  >
                    Next patient
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    icon={Check}
                    onClick={() => {
                      save();
                      move("home");
                    }}
                  >
                    {isRecording ? "Pause and save" : "Save and exit"}
                  </Button>
                  <Button
                    primary
                    icon={Microphone}
                    onClick={() =>
                      view === "home"
                        ? move("prepare")
                        : view === "prepare"
                          ? start()
                          : view === "recording"
                            ? stop()
                            : setModal({ type: "deliver" })
                    }
                  >
                    {view === "home"
                      ? "Start verbal report"
                      : view === "prepare"
                        ? "Start recording"
                        : view === "recording"
                          ? "Stop and review"
                          : "Sign and send to M. Chen"}
                  </Button>
                </>
              )}
            </div>
          </footer>
        </main>
      </div>
      <footer className="system-status">
        <span>
          <WifiHigh size={15} className="green" />
          Connected{" "}
          <span className="sync">
            Last successful sync {isIncoming ? "07:04" : "06:47"}
          </span>
        </span>
        <span className="demo-status">
          Interactive demo <span className="status-separator">·</span> Handoff
          Check running on unit
        </span>
      </footer>
      <div
        className={`toast ${toast ? "visible" : ""}`}
        role="status"
        aria-live="polite"
      >
        {toast && (
          <>
            <CheckCircle size={19} />
            {toast}
            <button
              aria-label="Dismiss notification"
              onClick={() => setToast(null)}
            >
              <X size={16} />
            </button>
          </>
        )}
      </div>
      {modal && (
        <Modal
          title={
            modal.type === "deliver"
              ? "Sign and send handoff"
              : modal.type === "acknowledge"
                ? "Acknowledge handoff"
                : modal.type === "question"
                  ? "Ask A. Rivera"
                  : modal.type === "source"
                    ? "Source record"
                    : modal.type === "say"
                      ? "Add a report addendum"
                      : "Reset demo?"
          }
          onClose={() => setModal(null)}
          footer={
            modal.type === "source" ? (
              <Button onClick={() => setModal(null)}>Close</Button>
            ) : (
              <>
                <Button onClick={() => setModal(null)}>Cancel</Button>
                <Button
                  primary
                  disabled={
                    ["question", "say"].includes(modal.type) && !question.trim()
                  }
                  onClick={() => {
                    if (modal.type === "deliver") deliver();
                    if (
                      modal.type === "acknowledge" &&
                      isIncoming &&
                      availableIncoming
                    ) {
                      update({ acknowledged: true });
                      setModal(null);
                      notify(
                        "Handoff acknowledged. Follow-up tasks remain open.",
                      );
                    }
                    if (modal.type === "question") {
                      update((r) => ({
                        ...r,
                        questions: [...r.questions, question.trim()],
                      }));
                      setModal(null);
                      notify(
                        "Question added to the demo handoff. No message was sent.",
                      );
                    }
                    if (modal.type === "say") {
                      update((r) => ({
                        ...decide(r, modal.item.id, "added"),
                        notes: [r.notes, question.trim()]
                          .filter(Boolean)
                          .join("\n"),
                      }));
                      setModal(null);
                      notify("Addendum saved to the report.");
                    }
                    if (modal.type === "reset") {
                      setRecords(initialRecords());
                      setSelected("7");
                      setView(isIncoming ? "incoming" : "home");
                      setNav("My patients");
                      setFilter("all");
                      setSearch("");
                      setPaused(false);
                      setModal(null);
                      notify("Demo reset.");
                    }
                  }}
                >
                  {modal.type === "deliver"
                    ? "Sign and send report"
                    : modal.type === "acknowledge"
                      ? "Confirm acknowledgement"
                      : modal.type === "question"
                        ? "Add question"
                        : modal.type === "say"
                          ? "Save addendum"
                          : "Reset demo"}
                </Button>
              </>
            )
          }
        >
          {modal.type === "deliver" && (
            <>
              <p>
                Sign as <strong>A. Rivera, RN</strong> and send the report for{" "}
                <strong>
                  Bed {active.bed} · {active.name}
                </strong>{" "}
                to <strong>M. Chen, RN</strong>.
              </p>
              <div className="modal-summary">
                <CheckCircle size={20} />
                <span>
                  Transcript and{" "}
                  {
                    Object.values(record.decisions).filter((v) => v === "added")
                      .length
                  }{" "}
                  added items will be included.
                </span>
              </div>
              {selected === "7" && unresolved.length > 0 && (
                <p className="notice">
                  <Warning size={18} />
                  {unresolved.length} suggestions have not been reviewed. You
                  can return to review or deliver with these remaining.
                </p>
              )}
              <p className="muted">
                Signing locks this handoff for the outgoing nurse. M. Chen must
                sign in to her own dashboard to acknowledge it. This is a local
                demo, not a clinical signature or delivery.
              </p>
            </>
          )}
          {modal.type === "acknowledge" && (
            <>
              <p>
                Confirm receipt of the handoff for{" "}
                <strong>
                  Bed {active.bed} · {active.name}
                </strong>
                .
              </p>
              <p>
                {pendingIncoming.length
                  ? `${pendingIncoming.length} handoff items have not been marked reviewed.`
                  : "All handoff items have been reviewed."}
              </p>
              <p className="notice">
                Acknowledging receipt does not complete the {incoming.length}{" "}
                open follow-up tasks.
              </p>
            </>
          )}
          {modal.type === "question" && (
            <>
              {modal.item && <blockquote>{modal.item.text}</blockquote>}
              <label htmlFor="question">Your question</label>
              <textarea
                id="question"
                autoFocus
                rows="4"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What would you like to clarify?"
              />
              <p className="muted">
                Saved to this demo only. No message is sent.
              </p>
            </>
          )}
          {modal.type === "say" && (
            <>
              <p>
                Demo addendum for <strong>{modal.item.title}</strong>. Edit the
                sample wording below.
              </p>
              <label htmlFor="addendum">Addendum transcript</label>
              <textarea
                id="addendum"
                autoFocus
                rows="4"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <p className="muted">
                Microphone capture and transcription require a backend
                integration.
              </p>
            </>
          )}
          {modal.type === "source" && (
            <>
              <Badge tone="teal">Sample chart record</Badge>
              <h3>{modal.item.title}</h3>
              <p className="muted">
                Bed {active.bed} · {active.name} · {modal.item.source}
              </p>
              {modal.item.lines.map((l) => (
                <p className="source-record-line" key={l}>
                  {l}
                </p>
              ))}
              <p className="muted">
                Source data from the supplied design. Automated suggestions are
                not clinically verified.
              </p>
            </>
          )}
          {modal.type === "reset" && (
            <p>
              This clears the demo’s saved drafts, report decisions, questions,
              and acknowledgements from this browser.
            </p>
          )}
        </Modal>
      )}
    </div>
  );
}
function TaskRows({ items, onSource, onReview, worklist = false }) {
  return (
    <div className="panel task-table">
      {items.map((task) => (
        <div className="task-row" key={task.id}>
          <span className="task-time">{task.time}</span>
          <div>
            <p>{task.text}</p>
            {task.id === "potassium" && (
              <p className="source-line">
                <Sparkle size={13} />
                Suggested by Handoff Check{" "}
                <button
                  className="text-button"
                  onClick={() => onSource("potassium")}
                >
                  View source
                </button>
              </p>
            )}
            {worklist && (
              <button className="text-button" onClick={onReview}>
                Bed 7 · Open handoff <ArrowRight size={12} />
              </button>
            )}
          </div>
          <span className="muted">{task.owner}</span>
          <span className={task.status === "Open" ? "red" : "teal"}>
            {task.status}
          </span>
        </div>
      ))}
    </div>
  );
}
function ReportSummary({ selected, record, active }) {
  return (
    <section className="panel report-content">
      <h3>Report summary · Bed {active.bed}</h3>
      <p className="muted">A. Rivera, RN → M. Chen, RN · Night shift</p>
      {record.liveTranscript ? (
        <>
          <h4>Recorded transcript</h4>
          <p className="preserve-lines">
            {record.transcript || "No transcript provided."}
          </p>
        </>
      ) : selected === "7" ? (
        <>
          <h4>Current situation</h4>
          <p>
            Post-op day 3 · Ventilated · Propofol and norepinephrine infusions.
          </p>
          <h4>Changes covered in the report</h4>
          <ul>
            <li>Peripheral line placed · 23:00</li>
            <li>Restraints removed · 00:00</li>
            <li>PEEP increased from 5 to 8 · 03:40</li>
          </ul>
        </>
      ) : (
        <p>{active.context}</p>
      )}
      {changes.some((c) => record.decisions[c.id] === "added") && (
        <>
          <h4>Added after review</h4>
          {changes
            .filter((c) => record.decisions[c.id] === "added")
            .map((c) => (
              <p key={c.id}>
                <Check size={15} className="green" /> {c.text}
              </p>
            ))}
        </>
      )}
      {record.notes && (
        <>
          <h4>Additional notes</h4>
          <p className="preserve-lines">{record.notes}</p>
        </>
      )}
    </section>
  );
}
function ChartPanel({ tab, selected, record, update, source, readOnly }) {
  if (tab === "Notes")
    return (
      <section className="panel report-content">
        <h3>Handoff notes</h3>
        <p className="muted">
          {readOnly
            ? "Signed handoff notes are read-only in this workspace."
            : "Notes stay with this patient’s local demo draft."}
        </p>
        <label htmlFor="chart-notes">Additional context</label>
        <textarea
          id="chart-notes"
          readOnly={readOnly}
          rows="8"
          value={record.notes}
          onChange={(e) => update({ notes: e.target.value })}
          placeholder="Write a handoff note…"
        />
        <p className="muted">
          <FloppyDisk size={14} /> Saved automatically on this browser
        </p>
      </section>
    );
  if (selected !== "7")
    return (
      <Empty title="No additional sample chart data">
        Detailed chart information was provided only for Bed 7.
      </Empty>
    );
  const rows =
    tab === "MAR"
      ? [
          ["Norepinephrine", "0.08 mcg/kg/min", "04:50"],
          ["Propofol", "25 mcg/kg/min", "21:30"],
          ["KCl", "40 mEq IV over 4h", "05:00"],
        ]
      : tab === "Results"
        ? [
            ["Potassium", "2.9 mmol/L", "02:10"],
            ["CBC, BMP", "Resulted — view source", "01:40"],
          ]
        : [
            ["06:00", "92", "104/58", "73", "96%", "37.4"],
            ["05:00", "95", "101/56", "71", "96%", "37.3"],
            ["04:00", "88", "98/54", "69", "97%", "37.1"],
            ["03:00", "86", "102/60", "74", "97%", "37.0"],
          ];
  return (
    <section className="panel report-content">
      <h3>{tab === "Chart Review" ? "Shift summary · 19:00 to 07:00" : tab}</h3>
      <p className="muted">Sample chart data · Last refreshed 06:47</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {(tab === "MAR"
                ? ["Agent", "Dose / Rate", "Last change"]
                : tab === "Results"
                  ? ["Test", "Result", "Time"]
                  : ["Time", "HR", "BP", "MAP", "SpO₂", "Temp"]
              ).map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((v, j) => (
                  <td key={j}>{v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button icon={ArrowSquareOut} onClick={() => source("potassium")}>
        View order and result source
      </Button>
    </section>
  );
}

function CoveragePanel({ patient, text, interim = "" }) {
  const coverage = chartCoverage(patient, text, interim);
  return <section className="panel covered live-coverage" aria-label="Live chart coverage">
    <h3>Chart coverage · Bed {patient}</h3>
    <p className="muted">Prototype phrase matching · Nurse verification required</p>
    {coverage.mismatches.length > 0 && <p role="alert" className="notice">Patient mismatch: speech mentions Bed {coverage.mismatches.join(", ")}, but Bed {patient} is selected. Pause and confirm the patient; correct the transcript before relying on coverage. No chart was switched.</p>}
    {!coverage.items.length ? <p>No detailed sample chart is available for Bed {patient}. Coverage cannot be checked for this patient.</p> : <>
      <p role="status">{coverage.mentioned} of {coverage.items.length} sample chart items mentioned</p>
      {coverage.items.map(item => <div className="coverage-row" key={item.id}>
        <strong>{item.title}</strong>
        <span className={item.status === "Mentioned" ? "coverage-status matched" : "coverage-status"}>{item.status === "Mentioned" ? "✓ " : ""}{item.status}</span>
        <small>Chart: {item.source}</small>
        {item.excerpt && <blockquote>“{item.excerpt}”</blockquote>}
      </div>)}
    </>}
    <p className="muted">A mention does not confirm accuracy or completion. Matching uses this patient’s transcript only; provisional words are not counted.</p>
  </section>;
}
