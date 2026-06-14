const labels = {
  coding: "编码炼器",
  paper_reading: "参悟论文",
  experiment_run: "实验突破",
  writing: "凝练文稿",
  meeting: "同门论道",
  debugging: "排障破阵",
  browsing: "杂念游荡",
  idle: "闭关走神",
};

const state = {
  snapshot: null,
  report: null,
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
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = minutes / 60;
  return `${hours.toFixed(hours >= 10 ? 0 : 1)} 小时`;
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
    ? `下一境界：${progress.next_realm}（${formatPower(progress.upper_bound)}）`
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
    target.innerHTML = `<p class="empty">今日暂无行为数据。</p>`;
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
    target.innerHTML = `<p class="empty">今天还没有修炼记录。</p>`;
    return;
  }

  for (const item of log) {
    const metadata = item.metadata || {};
    const feedback = metadata.ai_feedback || metadata.note || minutesText(item.duration);
    const detail = metadata.note && metadata.ai_feedback ? metadata.note : minutesText(item.duration);
    const row = document.createElement("div");
    row.className = "log-row";
    row.innerHTML = `
      <time>${item.time}</time>
      <div class="log-main">
        <strong>${escapeHtml(labels[item.type] || item.type)}</strong>
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
    target.textContent = "输入一段修炼汇报后，这里会显示修为结果和评语。";
    return;
  }

  const source = analysis.source === "local_ai" ? "本地分析" : "AI 分析";
  const tagList = (analysis.tags || []).map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
  const resultDelta = Number(delta ?? analysis.estimated_delta);
  target.className = "analysis-result";
  target.innerHTML = `
    <div class="analysis-score">
      <span>本次修为</span>
      <strong class="${resultDelta < 0 ? "negative" : ""}">${signed(resultDelta)}</strong>
    </div>
    <div class="analysis-meta">
      <span>${analysis.duration_minutes} 分钟</span>
      <span>质量 ${Number(analysis.quality).toFixed(2)}</span>
      <span>把握 ${Math.round(analysis.confidence * 100)}%</span>
      <span>${escapeHtml(source)}</span>
    </div>
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

  const note = $("#note").value.trim();
  if (!note) {
    formStatus.textContent = "先说点内容";
    submitting = false;
    return;
  }

  const payload = {
    type: $("#eventType").value,
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
    formStatus.textContent = "已入账";
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
    voiceStatus.textContent = "当前浏览器不支持语音输入。";
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
    voiceButton.textContent = "停止";
    voiceStatus.textContent = "正在听你说。";
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
    voiceStatus.textContent = "语音没听清，可以直接打字。";
  };

  recognition.onend = () => {
    listening = false;
    voiceButton.textContent = "语音";
    voiceStatus.textContent = note.value.trim() ? "已转成文字。" : "";
  };

  voiceButton.addEventListener("click", () => {
    if (listening) {
      recognition.stop();
      return;
    }
    recognition.start();
  });
}
