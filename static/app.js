const labels = {
  coding: "符阵炼器",
  paper_reading: "玉简参悟",
  experiment_run: "丹炉试炼",
  writing: "道卷成章",
  meeting: "同门论道",
  debugging: "破阵除障",
  browsing: "心猿游荡",
  idle: "神游太虚",
};

const trackLabels = {
  master: "硕士一程",
  phd: "博士一程",
  direct_phd: "直博玄门",
  master_phd: "硕博连修",
};

const defaultTrackYears = {
  master: 3,
  phd: 4,
  direct_phd: 5,
  master_phd: 6,
};

const state = {
  snapshot: null,
  report: null,
  track: null,
  trackYears: null,
  editingTrack: null,
};

const $ = (selector) => document.querySelector(selector);
let submitting = false;

function formatPower(value) {
  return Number(value || 0).toLocaleString("zh-CN", {
    maximumFractionDigits: 1,
  });
}

function signed(value) {
  const number = Number(value || 0);
  const prefix = number >= 0 ? "+" : "";
  return `${prefix}${number.toFixed(1)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function minutesText(seconds) {
  const minutes = Math.round(Number(seconds || 0) / 60);
  return cultivationTime(minutes);
}

function cultivationTime(minutes) {
  const value = Math.round(Number(minutes || 0));
  if (value === 15) return "一炷香";
  if (value > 0 && value < 120 && value % 15 === 0) return `${value / 15} 刻`;
  if (value >= 120) {
    const shichen = value / 120;
    return value % 120 === 0 ? `${shichen} 个时辰` : `约 ${shichen.toFixed(1)} 个时辰`;
  }
  return `约 ${value} 分`;
}

function validTrack(track) {
  return Object.prototype.hasOwnProperty.call(trackLabels, track);
}

function normalizeYears(value, track = getCurrentTrack() || "master") {
  const fallback = defaultTrackYears[track] || defaultTrackYears.master;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.round(Math.min(10, Math.max(1, parsed)) * 10) / 10;
}

function yearsText(value) {
  const years = Number(value || 0);
  return Number.isInteger(years) ? `${years} 年` : `${years.toFixed(1)} 年`;
}

function getCurrentTrack() {
  return validTrack(state.track) ? state.track : null;
}

function getCurrentTrackYears() {
  const track = getCurrentTrack();
  if (!track) return null;
  return normalizeYears(state.trackYears, track);
}

function setCurrentTrack(track, years) {
  if (!validTrack(track)) return;
  state.track = track;
  state.trackYears = normalizeYears(years, track);
  localStorage.setItem("cultivationTrack", track);
  localStorage.setItem("cultivationTrackYears", String(state.trackYears));
  renderTrack();
}

function renderTrack() {
  const track = getCurrentTrack();
  $("#currentTrackLabel").textContent = track ? trackLabels[track] : "未择定";
  $("#currentTrackYears").textContent = track ? `标准 ${yearsText(getCurrentTrackYears())}` : "未定年限";
  renderTrackDialog();
}

function renderTrackDialog() {
  const activeTrack = validTrack(state.editingTrack) ? state.editingTrack : getCurrentTrack();
  for (const button of document.querySelectorAll("[data-track-choice]")) {
    button.classList.toggle("is-active", button.dataset.trackChoice === activeTrack);
  }
  if (activeTrack && $("#trackYears")) {
    const currentYears = activeTrack === getCurrentTrack() ? getCurrentTrackYears() : defaultTrackYears[activeTrack];
    if (!$("#trackYears").value || Number($("#trackYears").value) !== currentYears) {
      $("#trackYears").value = currentYears;
    }
    $("#trackYearsHint").textContent = `${trackLabels[activeTrack]}常用 ${yearsText(defaultTrackYears[activeTrack])}，可按你的学制改。`;
  }
}

function openTrackDialog(required = false) {
  const dialog = $("#trackDialog");
  state.editingTrack = getCurrentTrack() || "master";
  $("#trackYears").value = getCurrentTrackYears() || defaultTrackYears[state.editingTrack];
  renderTrackDialog();
  dialog.classList.remove("is-hidden");
  dialog.dataset.required = required ? "true" : "false";
  $("#closeTrackDialog").hidden = required;
}

function closeTrackDialog() {
  $("#trackDialog").classList.add("is-hidden");
  $("#trackDialog").dataset.required = "false";
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function refresh() {
  const [snapshot, report] = await Promise.all([
    fetchJson("/state"),
    fetchJson("/report/daily"),
  ]);
  state.snapshot = snapshot;
  state.report = report;
  renderState(snapshot);
  renderReport(report);
}

function renderState(snapshot) {
  const progress = snapshot.realm_progress || {};
  const percent = Math.round((progress.progress || 0) * 100);

  $("#realm").textContent = snapshot.realm;
  $("#power").textContent = formatPower(snapshot.cultivation_power);
  $("#dailyDelta").textContent = signed(snapshot.daily_delta);
  $("#dailyDelta").className = Number(snapshot.daily_delta) < 0 ? "negative" : "";
  $("#risk").textContent = `${Math.round((snapshot.heart_demon_risk || 0) * 100)}%`;
  $("#riskBar").style.width = `${Math.round((snapshot.heart_demon_risk || 0) * 100)}%`;
  $("#progressText").textContent = `${percent}%`;
  $("#progressBar").style.width = `${percent}%`;
  $("#nextRealm").textContent = progress.next_realm
    ? `下一重天：${progress.next_realm}（${formatPower(progress.upper_bound)}）`
    : "已达飞升期";

  const warnings = $("#warnings");
  warnings.innerHTML = "";
  for (const warning of snapshot.warnings || []) {
    const item = document.createElement("li");
    item.textContent = warning;
    warnings.appendChild(item);
  }
}

function renderReport(report) {
  $("#narrative").textContent = report.narrative;
  $("#eventCount").textContent = `${report.event_count} 条`;
  $("#reportDate").textContent = report.date;
  renderSummary(report.summary || []);
  renderLog(report.log || []);
}

function renderSummary(summary) {
  const target = $("#summary");
  target.innerHTML = "";
  if (!summary.length) {
    target.innerHTML = `<p class="empty">今日修行谱尚未落墨。</p>`;
    return;
  }

  const max = Math.max(...summary.map((item) => Math.abs(item.delta)), 1);
  for (const item of summary) {
    const row = document.createElement("div");
    row.className = `summary-row ${item.delta < 0 ? "negative" : ""}`;
    row.innerHTML = `
      <span>${escapeHtml(item.label)}</span>
      <div class="mini-track"><div style="width:${Math.max(6, (Math.abs(item.delta) / max) * 100)}%"></div></div>
      <strong class="delta ${item.delta < 0 ? "negative" : ""}">${signed(item.delta)}</strong>
    `;
    target.appendChild(row);
  }
}

function renderLog(log) {
  const target = $("#log");
  target.innerHTML = "";
  if (!log.length) {
    target.innerHTML = `<p class="empty">今日玉简尚空，静候第一缕灵机。</p>`;
    return;
  }

  for (const item of log) {
    const metadata = item.metadata || {};
    const feedback = metadata.ai_feedback || metadata.note || minutesText(item.duration);
    const milestone = metadata.milestone || null;
    const detailText = milestone?.description || (metadata.tags || []).slice(0, 3).join(" · ") || minutesText(item.duration);
    const yearDetail = metadata.track_years ? `标准 ${yearsText(metadata.track_years)}` : "";
    const detail = [metadata.track_label, yearDetail, detailText].filter(Boolean).join(" · ");
    const milestoneHtml = milestone
      ? `<b class="log-milestone">${escapeHtml(milestone.title || metadata.milestone_title || "天机显化")}</b>`
      : "";
    const row = document.createElement("div");
    row.className = `log-row ${milestone ? "has-milestone" : ""}`;
    row.innerHTML = `
      <time>${item.time}</time>
      <div class="log-main">
        <strong>${escapeHtml(labels[item.type] || item.type)}${milestoneHtml}</strong>
        <span>${escapeHtml(feedback)}</span>
        <small>${escapeHtml(detail)}</small>
      </div>
      <strong class="delta ${item.delta < 0 ? "negative" : ""}">${signed(item.delta)}</strong>
    `;
    target.appendChild(row);
  }
}

function renderAnalysis(analysis, delta) {
  const target = $("#analysisResult");
  if (!analysis) {
    target.className = "analysis-result empty";
    target.textContent = "呈上修行经过后，天机盘会显出灵力涨落与长老判词。";
    return;
  }

  const source = analysis.source === "local_ai" ? "本地灵签" : "天机判词";
  const trackName = analysis.track_label || trackLabels[analysis.track] || trackLabels[getCurrentTrack()];
  const trackYearText = analysis.track_years ? yearsText(analysis.track_years) : yearsText(getCurrentTrackYears());
  const tagList = (analysis.tags || []).map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
  const resultDelta = Number(delta ?? analysis.estimated_delta);
  const milestone = analysis.milestone || null;
  const yearFactorText =
    milestone && Number(milestone.year_factor || 1) !== 1
      ? ` · 年限 ${Number(milestone.year_factor).toFixed(2)}x`
      : "";
  const milestoneBlock = milestone
    ? `
      <div class="milestone-banner">
        <div>
          <span>天机显化</span>
          <strong>${escapeHtml(milestone.title || "有所感")}</strong>
        </div>
        <p>${escapeHtml(milestone.description || milestone.feedback || "")}</p>
        <small>
          ${milestone.realm_target ? `直指 ${escapeHtml(milestone.realm_target)} · ` : ""}
          额外灵力 ${signed(milestone.bonus_power || 0)}${yearFactorText}
        </small>
      </div>
    `
    : "";
  target.className = "analysis-result";
  target.innerHTML = `
    <div class="analysis-score">
      <span>本次灵力</span>
      <strong class="${resultDelta < 0 ? "negative" : ""}">${signed(resultDelta)}</strong>
    </div>
    <div class="analysis-meta">
      <span>${cultivationTime(analysis.duration_minutes)}</span>
      <span>火候 ${Number(analysis.quality).toFixed(2)}</span>
      <span>灵验 ${Math.round(analysis.confidence * 100)}%</span>
      <span>${escapeHtml(trackName)}</span>
      <span>标准 ${escapeHtml(trackYearText)}</span>
      <span>${escapeHtml(source)}</span>
    </div>
    ${milestoneBlock}
    <p>${escapeHtml(analysis.feedback)}</p>
    <div class="tag-row">${tagList}</div>
  `;
}

async function submitEvent(event) {
  event.preventDefault();
  if (submitting) return;
  submitting = true;

  const formStatus = $("#formStatus");
  formStatus.textContent = "推演中";

  const track = getCurrentTrack();
  if (!track) {
    formStatus.textContent = "请先择定本命道途";
    openTrackDialog(true);
    submitting = false;
    return;
  }

  const note = $("#note").value.trim();
  if (!note) {
    formStatus.textContent = "请先呈上修行经过";
    submitting = false;
    return;
  }

  const payload = {
    type: $("#eventType").value,
    track,
    track_years: getCurrentTrackYears(),
    note,
    timestamp: Math.floor(Date.now() / 1000),
  };

  try {
    const result = await fetchJson("/event/from-note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderAnalysis(result.analysis, result.accepted?.delta);
    $("#note").value = "";
    formStatus.textContent = "已入玉简";
    await refresh();
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    submitting = false;
  }
}

function applyTemplate(event) {
  const button = event.target.closest("[data-template]");
  if (!button) return;
  $("#eventType").value = button.dataset.type;
  $("#note").value = button.dataset.template;
  $("#note").focus();
  $("#formStatus").textContent = "";
  renderAnalysis(null);
}

const eventForm = $("#eventForm");
const savedTrack = localStorage.getItem("cultivationTrack");
const savedTrackYears = localStorage.getItem("cultivationTrackYears");
if (trackLabels[savedTrack]) {
  state.track = savedTrack;
  state.trackYears = normalizeYears(savedTrackYears, savedTrack);
} else {
  localStorage.removeItem("cultivationTrack");
  localStorage.removeItem("cultivationTrackYears");
}
renderTrack();
$("#changeTrackButton").addEventListener("click", () => openTrackDialog(false));
$("#closeTrackDialog").addEventListener("click", closeTrackDialog);
$("#saveTrackButton").addEventListener("click", () => {
  const track = validTrack(state.editingTrack) ? state.editingTrack : getCurrentTrack() || "master";
  setCurrentTrack(track, $("#trackYears").value);
  closeTrackDialog();
  $("#formStatus").textContent = "";
});
$("#trackDialog").addEventListener("click", (event) => {
  if (event.target === $("#trackDialog") && $("#trackDialog").dataset.required !== "true") {
    closeTrackDialog();
  }
  const button = event.target.closest("[data-track-choice]");
  if (!button) return;
  state.editingTrack = button.dataset.trackChoice;
  $("#trackYears").value = defaultTrackYears[state.editingTrack] || defaultTrackYears.master;
  renderTrackDialog();
});
if (!getCurrentTrack()) {
  openTrackDialog(true);
}
eventForm.addEventListener("submit", submitEvent);
eventForm.querySelector('button[type="submit"]').addEventListener("click", submitEvent);
$("#promptRow").addEventListener("click", applyTemplate);
setupVoiceInput();
renderAnalysis(null);
refresh().catch((error) => {
  $("#narrative").textContent = error.message;
});

function setupVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const voiceButton = $("#voiceButton");
  const voiceStatus = $("#voiceStatus");
  const note = $("#note");

  if (!SpeechRecognition) {
    voiceButton.disabled = true;
    voiceStatus.textContent = "此境暂无法传音，可改以手书。";
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "zh-CN";
  recognition.interimResults = true;
  recognition.continuous = false;
  let listening = false;
  let voiceBaseValue = "";

  recognition.onstart = () => {
    listening = true;
    voiceBaseValue = note.value.trim();
    voiceButton.textContent = "止音";
    voiceStatus.textContent = "传音阵已启。";
  };

  recognition.onresult = (event) => {
    let finalTranscript = "";
    let interimTranscript = "";
    for (let index = 0; index < event.results.length; index += 1) {
      const transcript = event.results[index][0].transcript;
      if (event.results[index].isFinal) {
        finalTranscript += transcript;
      } else {
        interimTranscript += transcript;
      }
    }
    const addition = `${finalTranscript}${interimTranscript}`.trim();
    if (addition) {
      note.value = voiceBaseValue ? `${voiceBaseValue} ${addition}` : addition;
    }
  };

  recognition.onerror = () => {
    voiceStatus.textContent = "传音受扰，可改以手书。";
  };

  recognition.onend = () => {
    listening = false;
    voiceButton.textContent = "传音";
    voiceStatus.textContent = note.value.trim() ? "传音已落入玉简。" : "";
  };

  voiceButton.addEventListener("click", () => {
    if (listening) {
      recognition.stop();
      return;
    }
    recognition.start();
  });
}
