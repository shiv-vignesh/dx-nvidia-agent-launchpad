// One recognition session. Final results are committed once; interim words stay provisional.
export function createSpeechSession(
  Recognition,
  { onFinal, onInterim, onState, onError },
) {
  const recognition = new Recognition();
  recognition.lang = "en-US";
  recognition.continuous = true;
  recognition.interimResults = true;
  let committed = new Set();
  let closed = false;
  recognition.onstart = () => {
    if (!closed) onState("listening");
  };
  recognition.onresult = (event) => {
    let interim = [];
    for (let i = 0; i < event.results.length; i++) {
      const result = event.results[i];
      const text = result[0].transcript.trim();
      if (result.isFinal) {
        if (!committed.has(i)) {
          committed.add(i);
          if (text) onFinal(text);
        }
      } else if (text) interim.push(text);
    }
    onInterim(interim.join(" "));
  };
  recognition.onerror = (event) => {
    const messages = {
      "not-allowed":
        "Microphone permission was denied. Allow microphone access in browser settings, then resume.",
      "service-not-allowed":
        "Speech recognition is unavailable in this browser. Try Chrome or type your transcript below.",
      "audio-capture":
        "No microphone is available. Check your microphone connection, then resume.",
      network:
        "The speech service could not connect. Check your connection, then resume.",
      "no-speech":
        "No speech was detected. Resume and speak near your microphone.",
    };
    if (event.error !== "aborted")
      onError(
        messages[event.error] ||
          "Transcription stopped. Resume to try again or type below.",
      );
  };
  recognition.onend = () => {
    closed = true;
    onInterim("");
    onState("idle");
  };
  return {
    start() {
      onState("starting");
      try {
        recognition.start();
      } catch {
        closed = true;
        onState("idle");
        onError("Could not start the microphone. Try again or type below.");
      }
    },
    stop() {
      if (!closed) {
        closed = true;
        onState("stopping");
        try {
          recognition.stop();
        } catch {
          onState("idle");
        }
      }
    },
    dispose() {
      closed = true;
      recognition.onstart =
        recognition.onresult =
        recognition.onerror =
        recognition.onend =
          null;
      recognition.abort();
    },
  };
}
