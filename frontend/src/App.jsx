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
const STORAGE = "carechart-demo-v1";
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
export function App() {
  const [records, setRecords] = useState(load);
  const [selected, setSelected] = useState("7");
  const [view, setView] = useState(
    ["prepare", "recording", "review", "incoming"].includes(preview)
      ? preview
      : "home",
  );
  const [role, setRole] = useState(
    preview === "incoming" ? "incoming" : "outgoing",
  );
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
  const [loggedOut, setLoggedOut] = useState(false);
  const [storageError, setStorageError] = useState(false);
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
  const unresolved = changes.filter((c) => !record.decisions[c.id]);
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
    if (!isRecording || paused) return;
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
  }, [isRecording, paused, selected]);
  useEffect(() => {
    body.current?.scrollTo({ top: 0 });
  }, [view, selected, patientTab, nav]);
  useEffect(() => {
    if (!isRecording || paused) return;
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isRecording, paused]);
  useEffect(() => {
    if (!profile) return;
    const fn = (e) => {
      if (!e.target.closest(".profile-wrap")) setProfile(false);
    };
    document.addEventListener("click", fn);
    return () => document.removeEventListener("click", fn);
  }, [profile]);
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
    setView(isIncoming ? "incoming" : "home");
  }
  function resume() {
    if (isIncoming) {
      move("incoming");
      return;
    }
    move(
      record.stage === "recording"
        ? "recording"
        : record.stage === "review"
          ? "review"
          : record.status === "given"
            ? "delivered"
            : "prepare",
    );
  }
  function start() {
    update({ status: "progress", stage: "recording" });
    setPaused(false);
    move("recording");
  }
  function stop() {
    update({ stage: "review", status: "progress" });
    setPaused(false);
    move("review");
    setReviewTab("Not covered");
  }
  function changeRole(next) {
    if (isRecording) setPaused(true);
    window.speechSynthesis?.cancel();
    setRole(next);
    setView(next === "incoming" ? "incoming" : "home");
    setNav(next === "incoming" ? "Handoffs" : "My patients");
    setProfile(false);
    setPatientTab("Handoff");
    setFilter("all");
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
    update({
      status: "given",
      stage: "delivered",
      delivered: new Date().toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    });
    setModal(null);
    move("delivered");
    notify("Report delivered to M. Chen in this demo.");
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
  const reportText =
    selected === "7"
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
          <h2>You’re signed out</h2>
          <p>Your demo drafts are saved on this browser.</p>
          <Button primary icon={SignIn} onClick={() => setLoggedOut(false)}>
            Return to demo
          </Button>
          <small>Interactive frontend demo · No live patient records</small>
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
              <span className="eyebrow">Demo perspectives</span>
              <button onClick={() => changeRole("outgoing")}>
                <SignOut size={17} />
                A. Rivera · Outgoing nurse{!isIncoming && <Check size={15} />}
              </button>
              <button onClick={() => changeRole("incoming")}>
                <SignIn size={17} />
                M. Chen · Incoming nurse{isIncoming && <Check size={15} />}
              </button>
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
        <Button
          className="logout"
          onClick={() => {
            if (isRecording) {
              setPaused(true);
              save();
            }
            setLoggedOut(true);
          }}
        >
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
                            "Confirm receipt",
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
                                            "Receipt can be confirmed after the report is delivered.",
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
                        <span className="demo-label">
                          Demo recording · Sample transcript · Microphone is not
                          captured
                        </span>
                      </section>
                      <h3 className="section-title">
                        Handoff Check will compare your report against{" "}
                        <small>
                          {selected === "7"
                            ? "7 changes this shift"
                            : "the available chart"}
                        </small>
                      </h3>
                      <div className="change-counts">
                        {[
                          [2, "Orders"],
                          [1, "Vent change"],
                          [2, "Drip changes"],
                          [1, "Lab result"],
                          [1, "Line placed"],
                        ].map(([n, l]) => (
                          <div className="panel" key={l}>
                            <strong>{selected === "7" ? n : "—"}</strong>
                            <span>{l}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                  {view === "recording" && (
                    <>
                      <section
                        className={`recording-bar panel ${paused ? "paused" : ""}`}
                      >
                        <span className="record-dot" />
                        <strong>{paused ? "Paused" : "Recording"}</strong>
                        <img
                          className={`waveform ${paused ? "idle" : "live"}`}
                          src="/assets/waveform.svg"
                          alt={paused ? "" : "Animated recording indicator"}
                        />
                        <strong className="timer">
                          {timecode(record.seconds)}
                        </strong>
                        <Button
                          icon={paused ? Play : Pause}
                          onClick={() => setPaused(!paused)}
                        >
                          {paused ? "Resume" : "Pause"}
                        </Button>
                        <span className="demo-label">Demo recording</span>
                      </section>
                      <div className="recording-columns">
                        <section className="panel transcript">
                          <h3>Live transcript</h3>
                          {selected === "7" ? (
                            transcript
                              .slice(
                                0,
                                Math.min(6, 1 + Math.floor(record.seconds / 3)),
                              )
                              .map((line, i) => (
                                <p className="transcript-line" key={line}>
                                  {line}
                                </p>
                              ))
                          ) : (
                            <p>
                              {active.context}. This patient’s full report is
                              not included in the sample.
                            </p>
                          )}
                          <p className="muted faint">
                            {paused
                              ? "Recording paused. Resume whenever you’re ready."
                              : "Sample transcript appears as the demo runs…"}
                          </p>
                        </section>
                        <section className="panel covered">
                          <h3>Covered so far</h3>
                          <p className="muted">
                            {selected === "7"
                              ? Math.min(3, Math.floor(record.seconds / 4))
                              : 0}{" "}
                            of {selected === "7" ? 7 : 0} changes mentioned
                          </p>
                          {(selected === "7"
                            ? [
                                ["Peripheral line placed", "23:00"],
                                ["Restraints removed", "00:00"],
                                ["PEEP raised 5 to 8", "03:40"],
                                [
                                  "Potassium 2.9",
                                  "02:10 · order changed 05:00",
                                ],
                                ["Norepinephrine titrated up", "04:50"],
                              ]
                            : []
                          ).map(([label, time], i) => (
                            <div className="covered-item" key={label}>
                              <span
                                className={`coverage-check ${i < Math.min(3, Math.floor(record.seconds / 4)) ? "checked" : ""}`}
                              >
                                {i <
                                  Math.min(
                                    3,
                                    Math.floor(record.seconds / 4),
                                  ) && <Check size={12} />}
                              </span>
                              <span>
                                {label}
                                <em>{time}</em>
                              </span>
                            </div>
                          ))}
                        </section>
                      </div>
                    </>
                  )}
                  {view === "review" && (
                    <>
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
                            label: `Not covered · ${selected === "7" ? unresolved.length : 0}`,
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
                            These changes are in the record for this shift but
                            did not come up in your report. Add what the next
                            nurse needs, dismiss the rest.
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
                            Demo transcript · Review and correct before
                            delivery.
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
                          {selected === "7" &&
                            transcript.map((p) => <p key={p}>{p}</p>)}
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
                      {view === "delivered" ? (
                        <section className="delivered panel">
                          <CheckCircle size={34} />
                          <div>
                            <h3>
                              {record.acknowledged
                                ? "Handoff acknowledged"
                                : "Report delivered to M. Chen"}
                            </h3>
                            <p>
                              Bed {active.bed} · {active.name} ·{" "}
                              {record.acknowledged
                                ? "Receipt confirmed. Open follow-ups remain on the worklist."
                                : "Waiting for the incoming nurse to acknowledge receipt."}
                            </p>
                          </div>
                          <Button onClick={() => changeRole("incoming")}>
                            View as incoming nurse
                            <ArrowRight size={15} />
                          </Button>
                        </section>
                      ) : null}
                      {!availableIncoming && isIncoming ? (
                        <Empty title="Waiting for a handoff">
                          No report has been delivered for Bed {active.bed} yet.
                          <br />
                          Switch to the outgoing nurse to prepare and deliver
                          one.
                          <div className="empty-action">
                            <Button
                              onClick={() => changeRole("outgoing")}
                              icon={ArrowsLeftRight}
                            >
                              Switch to outgoing nurse
                            </Button>
                          </div>
                        </Empty>
                      ) : (
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
                              {selected === "7" ? (
                                transcript.map((p) => <p key={p}>{p}</p>)
                              ) : (
                                <p>{reportText}</p>
                              )}
                              {record.notes && <p>{record.notes}</p>}
                            </section>
                          )}
                        </>
                      )}
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
                      ? `${paused ? "Paused" : "Recording"}. Demo audio is not captured.`
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
                  <Button onClick={() => changeRole("incoming")}>
                    View as M. Chen
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
                          : "Deliver report to M. Chen"}
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
              ? "Deliver handoff"
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
                    if (modal.type === "acknowledge") {
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
                      setRole("outgoing");
                      setView("home");
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
                    ? "Deliver report"
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
                Deliver the report for{" "}
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
                This is a local demo. No report will be sent to a clinical
                system.
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
      {selected === "7" ? (
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
function ChartPanel({ tab, selected, record, update, source }) {
  if (tab === "Notes")
    return (
      <section className="panel report-content">
        <h3>Handoff notes</h3>
        <p className="muted">
          Notes stay with this patient’s local demo draft.
        </p>
        <label htmlFor="chart-notes">Additional context</label>
        <textarea
          id="chart-notes"
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
