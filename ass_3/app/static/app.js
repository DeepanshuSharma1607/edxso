let sessionId = null;

// Thrown when the backend no longer recognizes our session_id — happens after
// a dev-server restart (e.g. uvicorn --reload) if this tab was left open with
// a session_id from before the restart. Caught once by the click handler,
// which mints a fresh session and replays the whole flow instead of just
// showing an error forever.
class StaleSessionError extends Error {}

function esc(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

async function ensureSession(forceNew = false) {
  if (sessionId && !forceNew) return sessionId;
  const res = await fetch("/api/session/new", { method: "POST" });
  const data = await res.json();
  sessionId = data.session_id;
  return sessionId;
}

function setStatus(msg, isError = false) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.classList.toggle("error", isError);
}

// Wraps fetch for any /api/session/{sid}/... call. A 404 here means the
// session itself is gone (not "field missing" — that's 400), so it's always
// a stale-session signal, never a normal validation error.
async function sessionFetch(url, options) {
  const res = await fetch(url, options);
  if (res.status === 404) {
    throw new StaleSessionError("Session expired — starting a new one.");
  }
  return res;
}

function setStep(stepId, state) {
  const el = document.getElementById(stepId);
  el.classList.remove("active", "done");
  if (state) el.classList.add(state);
}

// Purely cosmetic: reflects filled-in fields on the stepper as the user
// works through the form. Does not gate anything — validation still happens
// in submitJD/submitResume exactly as before.
function refreshStepperFromInputs() {
  const hasJD = document.getElementById("jd_text").value.trim() || document.getElementById("jd_file").files.length > 0;
  const hasResume = document.getElementById("resume_text").value.trim() || document.getElementById("resume_file").files.length > 0;
  setStep("stepJD", hasJD ? "done" : "active");
  setStep("stepResume", hasResume ? "done" : (hasJD ? "active" : ""));
}

function wireFileDrop(inputId, labelId, dropId) {
  const input = document.getElementById(inputId);
  const label = document.getElementById(labelId);
  const drop = document.getElementById(dropId);
  input.addEventListener("change", () => {
    if (input.files.length > 0) {
      label.textContent = input.files[0].name;
      drop.classList.add("has-file");
    } else {
      label.textContent = "Upload .pdf, .docx or .txt";
      drop.classList.remove("has-file");
    }
    refreshStepperFromInputs();
  });
}

wireFileDrop("jd_file", "jd_file_label", "jd_file_drop");
wireFileDrop("resume_file", "resume_file_label", "resume_file_drop");
document.getElementById("jd_text").addEventListener("input", refreshStepperFromInputs);
document.getElementById("resume_text").addEventListener("input", refreshStepperFromInputs);
refreshStepperFromInputs();

async function submitJD(sid) {
  const text = document.getElementById("jd_text").value.trim();
  const fileInput = document.getElementById("jd_file");
  const form = new FormData();
  if (fileInput.files.length > 0) {
    form.append("jd_file", fileInput.files[0]);
  } else if (text) {
    form.append("jd_text", text);
  } else {
    throw new Error("Provide a Job Description (paste or upload).");
  }
  const res = await sessionFetch(`/api/session/${sid}/jd`, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail || "JD submission failed.");
}

async function submitResume(sid) {
  const text = document.getElementById("resume_text").value.trim();
  const fileInput = document.getElementById("resume_file");
  const form = new FormData();
  if (fileInput.files.length > 0) {
    form.append("resume_file", fileInput.files[0]);
  } else if (text) {
    form.append("resume_text", text);
  } else {
    throw new Error("Provide a Resume (paste or upload).");
  }
  const res = await sessionFetch(`/api/session/${sid}/resume`, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail || "Resume submission failed.");
}

/* ---------------- Rendering ---------------- */

function chipGroup(items, variant) {
  if (!items || items.length === 0) return `<p class="empty-note">None identified.</p>`;
  const cls = variant ? ` chip-${variant}` : "";
  return `<div class="chip-group">${items.map((i) => `<span class="chip${cls}">${esc(i)}</span>`).join("")}</div>`;
}

function listBlock(items) {
  if (!items || items.length === 0) return `<p class="empty-note">None identified.</p>`;
  return `<ul class="list-plain">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
}

function renderRoleAnalysis(role) {
  const card = document.getElementById("roleAnalysisCard");
  card.innerHTML = `
    <div class="role-title">${esc(role.role_title || "Role")}</div>
    ${role.experience_expectations ? `<p class="text-block">${esc(role.experience_expectations)}</p>` : ""}

    <div class="subcard-grid">
      <div>
        <div class="field-label">Required Skills</div>
        ${chipGroup(role.required_skills, "good")}
        <div class="field-label">Preferred Skills</div>
        ${chipGroup(role.preferred_skills)}
        <div class="field-label">Technical Competencies</div>
        ${chipGroup(role.technical_competencies)}
        <div class="field-label">Behavioural Competencies</div>
        ${chipGroup(role.behavioural_competencies)}
      </div>
      <div>
        <div class="field-label">Key Responsibilities</div>
        ${listBlock(role.key_responsibilities)}
        <div class="field-label">Key Qualifications</div>
        ${listBlock(role.key_qualifications)}
      </div>
    </div>

    <div class="divider"></div>
    <div class="field-label">Important Keywords</div>
    ${chipGroup(role.important_keywords)}
    <div class="field-label">Important Concepts</div>
    ${chipGroup(role.important_concepts)}
  `;
}

function renderCandidateAnalysis(cand) {
  const card = document.getElementById("candidateAnalysisCard");
  card.innerHTML = `
    <div class="field-label">Key Skills</div>
    ${chipGroup(cand.key_skills)}

    <div class="divider"></div>
    <div class="subcard-grid">
      <div>
        <div class="field-label">Relevant Experience</div>
        ${listBlock(cand.relevant_experience)}
        <div class="field-label">Relevant Projects</div>
        ${listBlock(cand.relevant_projects)}
        <div class="field-label">Relevant Achievements</div>
        ${listBlock(cand.relevant_achievements)}
      </div>
      <div>
        <div class="field-label">Strengths vs JD</div>
        ${chipGroup(cand.strengths_vs_jd, "good")}
        <div class="field-label">Missing Skills</div>
        ${chipGroup(cand.missing_skills, "bad")}
        <div class="field-label">Weak Areas</div>
        ${chipGroup(cand.weak_areas, "warn")}
      </div>
    </div>

    <div class="divider"></div>
    <div class="field-label">Resume Claims Worth Probing in Interview</div>
    ${listBlock(cand.claims_to_probe)}
    <div class="field-label">Suggested Prep Focus Areas</div>
    ${listBlock(cand.prep_focus_areas)}
  `;
}

function renderJobFit(fit) {
  const card = document.getElementById("jobFitCard");
  const pct = Math.max(0, Math.min(100, fit.score || 0));
  card.innerHTML = `
    <div class="fit-header">
      <div class="score-ring" style="--pct:${pct}">
        <div class="score-ring-inner">
          <div class="score-ring-num">${pct}%</div>
          <div class="score-ring-label">Job Fit</div>
        </div>
      </div>
      <p class="fit-rationale">${esc(fit.rationale || "")}</p>
    </div>
    <div class="fit-groups">
      <div class="fit-group good">
        <h4>✓ Strong Match</h4>
        ${chipGroup(fit.strong_match, "good")}
      </div>
      <div class="fit-group warn">
        <h4>~ Partial Match</h4>
        ${chipGroup(fit.partial_match, "warn")}
      </div>
      <div class="fit-group bad">
        <h4>✕ Missing / Weak</h4>
        ${chipGroup(fit.missing_or_weak, "bad")}
      </div>
    </div>
  `;
}

async function runAnalysisFlow(forceNewSession) {
  setStatus(forceNewSession ? "Session expired — starting a new one..." : "Creating session...");
  const sid = await ensureSession(forceNewSession);

  setStatus("Submitting job description...");
  await submitJD(sid);
  setStep("stepJD", "done");

  setStatus("Submitting resume...");
  await submitResume(sid);
  setStep("stepResume", "done");

  setStep("stepAnalysis", "active");
  setStatus("Analysing role and candidate fit — this can take 10-20s...");
  const res = await sessionFetch(`/api/session/${sid}/analyse`, { method: "POST" });
  if (!res.ok) throw new Error((await res.json()).detail || "Analysis failed.");
  const data = await res.json();

  renderRoleAnalysis(data.role_analysis || {});
  renderCandidateAnalysis(data.candidate_analysis || {});
  renderJobFit(data.job_fit || {});
  setStep("stepAnalysis", "done");

  document.getElementById("results").classList.remove("hidden");
  document.getElementById("startInterviewLink").href = `/interview?session_id=${sid}`;
  document.getElementById("results").scrollIntoView({ behavior: "smooth", block: "start" });
  setStatus("Analysis complete — session " + sid);
}

document.getElementById("analyseBtn").addEventListener("click", async () => {
  const btn = document.getElementById("analyseBtn");
  btn.disabled = true;
  const originalLabel = btn.textContent;
  btn.innerHTML = `<span class="spinner"></span>Working...`;
  try {
    try {
      await runAnalysisFlow(false);
    } catch (err) {
      if (!(err instanceof StaleSessionError)) throw err;
      // Session died server-side (e.g. dev server restarted) — retry once
      // with a brand-new session instead of leaving the user stuck on a
      // 404 loop. The JD/resume text is still sitting in the form fields,
      // so this replay is transparent.
      await runAnalysisFlow(true);
    }
  } catch (err) {
    setStatus("Error: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
});
