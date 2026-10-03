import React, { useEffect, useRef, useState } from "react";
import {
  Check,
  X,
  Play,
  Pause,
  SpeakerHigh,
  ArrowCounterClockwise,
} from "@phosphor-icons/react";
import { timecode } from "./model";
export function Button({
  children,
  icon: Icon,
  primary = false,
  className = "",
  ...props
}) {
  return (
    <button
      className={`button ${primary ? "primary" : ""} ${className}`}
      {...props}
      onClick={(e) => {
        e.currentTarget.focus();
        props.onClick?.(e);
      }}
    >
      {Icon && <Icon size={16} aria-hidden="true" />}
      {children}
    </button>
  );
}
export function Badge({ children, tone = "", icon: Icon }) {
  return (
    <span className={`badge ${tone}`}>
      {Icon && <Icon size={13} aria-hidden="true" />}
      {children}
    </span>
  );
}
export function Tabs({ items, value, onChange, label }) {
  return (
    <div
      className="tabs"
      role="tablist"
      aria-label={label}
      onKeyDown={(e) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
        e.preventDefault();
        const i = items.findIndex(
          (t) => (typeof t === "string" ? t : t.id) === value,
        );
        const next =
          e.key === "Home"
            ? 0
            : e.key === "End"
              ? items.length - 1
              : (i + (e.key === "ArrowRight" ? 1 : -1) + items.length) %
                items.length;
        onChange(
          typeof items[next] === "string" ? items[next] : items[next].id,
        );
        e.currentTarget.querySelectorAll("[role=tab]")[next].focus();
      }}
    >
      {items.map((item) => {
        const id = typeof item === "string" ? item : item.id;
        return (
          <button
            key={id}
            role="tab"
            aria-selected={value === id}
            tabIndex={value === id ? 0 : -1}
            className={value === id ? "active" : ""}
            onClick={() => onChange(id)}
          >
            {typeof item === "string" ? item : item.label}
          </button>
        );
      })}
    </div>
  );
}
export function Modal({ title, children, onClose, footer }) {
  const dialog = useRef(null);
  const previous = useRef(document.activeElement);
  useEffect(() => {
    dialog.current.showModal();
    const element = dialog.current;
    return () => {
      element.close();
      previous.current?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="modal"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            onClose();
        }
      }}
      aria-labelledby="modal-title"
    >
      <header>
        <h2 id="modal-title">{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </header>
      <div className="modal-body">{children}</div>
      {footer && <footer>{footer}</footer>}
    </dialog>
  );
}
export function Player({ duration = 252, text = "", report = false }) {
  const [playing, setPlaying] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [supported, setSupported] = useState(true);
  useEffect(() => () => window.speechSynthesis?.cancel(), []);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(
      () => setSeconds((s) => Math.min(s + 1, duration)),
      1000,
    );
    return () => clearInterval(id);
  }, [playing, duration]);
  function play() {
    if (playing) {
      window.speechSynthesis?.pause();
      setPlaying(false);
      return;
    }
    if (!window.speechSynthesis) {
      setSupported(false);
      return;
    }
    if (window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
      setPlaying(true);
      return;
    }
    window.speechSynthesis.cancel();
    setSeconds(0);
    const speech = new SpeechSynthesisUtterance(
      text || "No recorded report is available for this patient.",
    );
    speech.rate = 0.9;
    speech.onend = () => {
      setPlaying(false);
      setSeconds(duration);
    };
    speech.onerror = () => setPlaying(false);
    window.speechSynthesis.speak(speech);
    setPlaying(true);
  }
  return (
    <div>
      <div className="player">
        <Button primary icon={playing ? Pause : Play} onClick={play}>
          {playing ? "Pause" : report ? "Play report" : "Play"}
        </Button>
        <span>{timecode(seconds)}</span>
        <progress
          aria-label="Report playback progress"
          value={seconds}
          max={duration}
        />
        <span>{timecode(duration)}</span>
        {seconds > 0 && !playing && (
          <button
            className="icon-button"
            aria-label="Replay report"
            onClick={() => {
              setSeconds(0);
              play();
            }}
          >
            <ArrowCounterClockwise size={16} />
          </button>
        )}
      </div>
      {playing && (
        <p className="player-note">
          <SpeakerHigh size={13} /> Demo narration of the sample transcript
        </p>
      )}
      {!supported && (
        <p className="player-note">
          Audio playback isn’t supported here. You can read the Transcript tab.
        </p>
      )}
    </div>
  );
}
export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Check size={25} />
      </div>
      <h3>{title}</h3>
      <div className="empty-description">{children}</div>
      {action}
    </div>
  );
}
