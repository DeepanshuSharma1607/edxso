function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

let sessionId = getQueryParam("session_id") || "";
document.getElementById("sessionIdInput").value = sessionId;

let mediaRecorder = null;
let recordedChunks = [];
let isRecording = false;
let interviewStartedAt = null;
let timerInterval = null;

const INTERVIEW_MAX_SECONDS = 10 * 60; // must match MAX_INTERVIEW_SECONDS in app/services/interview.py

function setStatus(msg, isError = false) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.classList.toggle("error", isError);
}

function appendMessage(role, text) {
  const chat = document.getElementById("chat");
  const row = document.createElement("div");
  row.className = `msg-row ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "ai" ? "🧑‍💼" : role === "user" ? "🙂" : "⏱";
  const bubble = document.createElement("div");
  bubble.className = `msg ${role}`;
  bubble.textContent = text;
  if (role === "system") {
    row.appendChild(bubble);
  } else {
    row.appendChild(avatar);
    row.appendChild(bubble);
  }
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

const LEVEL_STEP_IDS = { screening: "stepScreening", competency: "stepCompetency", deep_dive: "stepDeepDive" };
const LEVEL_ORDER = ["screening", "competency", "deep_dive"];

function setLevel(level) {
  document.getElementById("levelBadge").textContent = `Level: ${level.replace("_", "-")}`;
  const currentIdx = LEVEL_ORDER.indexOf(level);
  LEVEL_ORDER.forEach((lvl, idx) => {
    const el = document.getElementById(LEVEL_STEP_IDS[lvl]);
    el.classList.remove("active", "done");
    if (level === "done" || idx < currentIdx) el.classList.add("done");
    else if (idx === currentIdx) el.classList.add("active");
  });
}

function setAnswerEnabled(enabled) {
  document.getElementById("answerInput").disabled = !enabled;
  document.getElementById("sendBtn").disabled = !enabled;
  document.getElementById("recordBtn").disabled = !enabled;
}

function setStopEnabled(enabled) {
  document.getElementById("stopBtn").disabled = !enabled;
}

function startTimer(startedAt) {
  interviewStartedAt = startedAt;
  const badge = document.getElementById("timerBadge");
  badge.style.display = "";
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const elapsed = Date.now() / 1000 - interviewStartedAt;
    const remaining = Math.max(0, INTERVIEW_MAX_SECONDS - elapsed);
    const mm = Math.floor(remaining / 60);
    const ss = Math.floor(remaining % 60).toString().padStart(2, "0");
    badge.textContent = `Time left: ${mm}:${ss}`;
    badge.classList.toggle("warning", remaining <= 120 && remaining > 30);
    badge.classList.toggle("critical", remaining <= 30);
    if (remaining <= 0) {
      clearInterval(timerInterval);
      badge.textContent = "Time's up";
      // Server enforces the same cap on the next answer submission, but if
      // the user is just sitting idle when the clock runs out, force the
      // same end-of-interview flow client-side rather than waiting for them
      // to act.
      endInterview("/interview/stop");
    }
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
}

async function speakQuestion(text) {
  if (!document.getElementById("voiceToggle").checked) return;
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) return; // fail silently — text is still visible in chat
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audioEl = document.getElementById("ttsAudio");
    audioEl.src = url;
    await audioEl.play().catch(() => {}); // autoplay can be blocked; ignore
  } catch (e) {
    // Voice is a nice-to-have here — never block the interview on TTS failure.
  }
}

document.getElementById("startBtn").addEventListener("click", async () => {
  sessionId = document.getElementById("sessionIdInput").value.trim();
  if (!sessionId) {
    setStatus("Enter a session_id first.", true);
    return;
  }
  const startBtn = document.getElementById("startBtn");
  startBtn.disabled = true;
  setStatus("Starting interview...");
  try {
    const res = await fetch(`/api/session/${sessionId}/interview/start`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "Could not start interview.");
    const data = await res.json();
    document.getElementById("sessionEntry").classList.add("hidden");
    document.getElementById("interviewArea").classList.remove("hidden");
    setLevel(data.level);
    appendMessage("ai", data.question);
    setAnswerEnabled(true);
    setStopEnabled(true);
    if (data.interview_started_at) startTimer(data.interview_started_at);
    setStatus("");
    speakQuestion(data.question);
  } catch (err) {
    setStatus("Error: " + err.message, true);
  } finally {
    startBtn.disabled = false;
  }
});

document.getElementById("stopBtn").addEventListener("click", () => endInterview("/interview/stop"));

async function endInterview(path) {
  setStopEnabled(false);
  setAnswerEnabled(false);
  setStatus("Ending interview...");
  try {
    const res = await fetch(`/api/session/${sessionId}${path}`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "Could not stop the interview.");
    const data = await res.json();
    await handleInterviewTurnResult(data);
  } catch (err) {
    setStatus("Error: " + err.message, true);
  }
}

document.getElementById("sendBtn").addEventListener("click", async () => {
  const input = document.getElementById("answerInput");
  const answer = input.value.trim();
  if (!answer) return;

  appendMessage("user", answer);
  input.value = "";
  setAnswerEnabled(false);
  setStatus("Evaluating your answer...");

  try {
    const res = await fetch(`/api/session/${sessionId}/interview/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Could not submit answer.");
    const data = await res.json();
    await handleInterviewTurnResult(data);
  } catch (err) {
    setStatus("Error: " + err.message, true);
    setAnswerEnabled(true);
  }
});

// Allow Ctrl/Cmd+Enter to send, since the textarea itself needs plain Enter for newlines.
document.getElementById("answerInput").addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    document.getElementById("sendBtn").click();
  }
});

document.getElementById("recordBtn").addEventListener("click", async () => {
  if (!isRecording) {
    await startRecording();
  } else {
    stopRecording();
  }
});

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) recordedChunks.push(e.data);
    };
    mediaRecorder.onstop = onRecordingStopped;
    mediaRecorder.start();
    isRecording = true;
    const btn = document.getElementById("recordBtn");
    btn.classList.add("recording");
    document.getElementById("recordBtnLabel").textContent = "Stop Recording";
    document.getElementById("recordStatus").textContent = "Recording...";
    document.getElementById("sendBtn").disabled = true; // voice path submits itself
  } catch (err) {
    setStatus("Microphone access denied or unavailable: " + err.message, true);
  }
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
    isRecording = false;
    const btn = document.getElementById("recordBtn");
    btn.classList.remove("recording");
    document.getElementById("recordBtnLabel").textContent = "Record Answer";
  }
}

async function onRecordingStopped() {
  document.getElementById("recordStatus").textContent = "Transcribing...";
  setAnswerEnabled(false);

  const blob = new Blob(recordedChunks, { type: "audio/webm" });
  const form = new FormData();
  form.append("audio", blob, "recording.webm");

  try {
    const res = await fetch(`/api/session/${sessionId}/interview/voice-answer`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Voice answer failed.");
    const data = await res.json();
    appendMessage("user", data.transcribed_text);
    document.getElementById("recordStatus").textContent = "";
    await handleInterviewTurnResult(data);
  } catch (err) {
    setStatus("Error: " + err.message, true);
    document.getElementById("recordStatus").textContent = "";
    setAnswerEnabled(true);
  }
}

const ENDED_REASON_LABELS = {
  completed: "Interview complete.",
  user_stopped: "Interview stopped.",
  time_limit: "Time's up — interview ended at the 10-minute limit.",
};

async function handleInterviewTurnResult(data) {
  if (data.done) {
    setLevel("done");
    stopTimer();
    setStopEnabled(false);
    setAnswerEnabled(false);
    appendMessage("system", ENDED_REASON_LABELS[data.ended_reason] || "Interview complete.");
    setStatus("Generating your performance report...");
    await showReport();
    return;
  }
  setLevel(data.level);
  appendMessage("ai", data.next_question);
  setAnswerEnabled(true);
  setStatus("");
  speakQuestion(data.next_question);
}

const READINESS_CLASSES = {
  "Strong Candidate": "strong",
  "Interview Ready": "ready",
  "Needs Practice": "practice",
  "Not Ready": "not-ready",
};

async function showReport() {
  const section = document.getElementById("reportSection");
  const reportStatus = document.getElementById("reportStatus");
  const body = document.getElementById("reportBody");
  section.classList.remove("hidden");
  body.classList.add("hidden");
  reportStatus.textContent = "Generating your performance report — this can take 10-20s...";

  try {
    const res = await fetch(`/api/session/${sessionId}/report`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "Could not generate report.");
    const report = await res.json();

    document.getElementById("reportScore").textContent = report.overall_score;
    document.getElementById("reportScoreRing").style.setProperty("--pct", Math.max(0, Math.min(100, report.overall_score || 0)));
    const badge = document.getElementById("reportReadinessBadge");
    badge.textContent = report.readiness_label;
    badge.className = "readiness-badge " + (READINESS_CLASSES[report.readiness_label] || "");
    document.getElementById("reportSummary").textContent = report.summary;

    fillList("reportStrengths", report.strengths);
    fillList("reportWeaknesses", report.weaknesses);
    fillList("reportImprovementPlan", report.improvement_plan);

    const perLevelEl = document.getElementById("reportPerLevel");
    perLevelEl.innerHTML = "";
    for (const [level, fb] of Object.entries(report.per_level_feedback || {})) {
      if (!fb.questions_answered) continue;
      const li = document.createElement("li");
      li.textContent = `${level}: ${fb.questions_answered} answered, avg quality ${fb.average_quality}/5 — ${fb.feedback}`;
      perLevelEl.appendChild(li);
    }

    reportStatus.textContent = "";
    body.classList.remove("hidden");
    section.scrollIntoView({ behavior: "smooth", block: "start" });
    setStatus("Interview finished.");
  } catch (err) {
    reportStatus.textContent = "Error generating report: " + err.message;
    setStatus("Interview finished (report failed — you can retry from this page).", true);
  }
}

function fillList(elementId, items) {
  const el = document.getElementById(elementId);
  el.innerHTML = "";
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  });
}
