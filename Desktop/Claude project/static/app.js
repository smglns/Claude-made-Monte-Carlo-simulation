"use strict";

// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────
let currentResults = null;
let fanChartInstance = null;
let histChartInstance = null;

// ─────────────────────────────────────────────
// UTILS
// ─────────────────────────────────────────────
function fmt(v) {
  if (v == null || isNaN(v)) return "—";
  return "$" + Math.round(v).toLocaleString();
}

function fmtPct(v) {
  if (v == null || isNaN(v)) return "—";
  return (v * 100).toFixed(1) + "%";
}

function destroyChart(instance) {
  if (instance) instance.destroy();
}

// ─────────────────────────────────────────────
// COLLAPSIBLE FIELDSETS
// ─────────────────────────────────────────────
function toggleFieldset(fs) {
  fs.classList.toggle("collapsed");
}

// ─────────────────────────────────────────────
// SHOCK EVENTS DOM
// ─────────────────────────────────────────────
let shockCounter = 0;

function addShockEventRow(data = {}) {
  const id = ++shockCounter;
  const list = document.getElementById("shock-events-list");
  const div = document.createElement("div");
  div.className = "shock-row";
  div.dataset.shockId = id;
  div.innerHTML = `
    <div class="shock-row-header">
      <span>Shock event #${id}</span>
      <button type="button" class="btn btn-danger" onclick="removeShockRow(${id})">Remove</button>
    </div>
    <div class="shock-row-fields">
      <div class="form-row">
        <label>Label</label>
        <input type="text" class="shock-label" value="${data.label || 'market_crash'}" />
      </div>
      <div class="form-row">
        <label>Prob (%/yr)</label>
        <input type="number" class="shock-prob" value="${((data.annual_probability || 0.05) * 100).toFixed(1)}" min="0.1" max="99" step="0.5" />
      </div>
      <div class="form-row">
        <label>Impact (%)</label>
        <input type="number" class="shock-impact" value="${(((data.impact_multiplier || 0.65)) * 100).toFixed(0)}" min="1" max="99" step="5"
          title="Portfolio is multiplied by this percentage. E.g. 65 = crash to 65% of value." />
      </div>
    </div>`;
  list.appendChild(div);
}

function removeShockRow(id) {
  const el = document.querySelector(`[data-shock-id="${id}"]`);
  if (el) el.remove();
}

function getShockEventsFromDOM() {
  const rows = document.querySelectorAll(".shock-row");
  return Array.from(rows).map(row => ({
    label: row.querySelector(".shock-label").value.trim() || "shock",
    annual_probability: parseFloat(row.querySelector(".shock-prob").value) / 100,
    impact_multiplier: parseFloat(row.querySelector(".shock-impact").value) / 100,
  }));
}

// ─────────────────────────────────────────────
// FORM → CONFIG
// ─────────────────────────────────────────────
function buildConfigFromForm() {
  const mode = document.getElementById("f-mode").value;
  const seedRaw = document.getElementById("f-seed").value.trim();
  const seed = seedRaw === "" ? null : parseInt(seedRaw);

  return {
    scenario: {
      name: document.getElementById("f-name").value.trim() || "unnamed",
      description: document.getElementById("f-desc").value.trim(),
      type: "retirement",
    },
    timeline: {
      start_date: document.getElementById("f-start").value,
      end_date: document.getElementById("f-end").value,
      time_step_years: parseFloat(document.getElementById("f-step").value),
    },
    initial_state: {
      portfolio_value: parseFloat(document.getElementById("f-portfolio").value),
      annual_contribution: parseFloat(document.getElementById("f-contrib").value) || 0,
      annual_withdrawal: parseFloat(document.getElementById("f-withdraw").value) || 0,
    },
    uncertainty: {
      expected_return_mean: parseFloat(document.getElementById("f-return").value) / 100,
      volatility_std: parseFloat(document.getElementById("f-vol").value) / 100,
      distribution: "lognormal_gbm",
      correlation_matrix: null,
      shock_events: getShockEventsFromDOM(),
    },
    constraints: {
      wealth_floor: parseFloat(document.getElementById("f-floor").value) || 0,
    },
    success_criteria: {
      target_portfolio_value: parseFloat(document.getElementById("f-target").value) || 0,
      never_below_floor: document.getElementById("f-never-below").checked,
    },
    simulation_config: {
      n_paths: parseInt(document.getElementById("f-npaths").value),
      random_seed: seed,
      mode: mode,
      record_full_paths: mode === "detailed",
    },
  };
}

// ─────────────────────────────────────────────
// FORM ← CONFIG (for load)
// ─────────────────────────────────────────────
function populateFormFromConfig(cfg) {
  const s = cfg.scenario || {};
  const tl = cfg.timeline || {};
  const st = cfg.initial_state || {};
  const unc = cfg.uncertainty || {};
  const con = cfg.constraints || {};
  const sc = cfg.success_criteria || {};
  const sim = cfg.simulation_config || {};

  document.getElementById("f-name").value = s.name || "";
  document.getElementById("f-desc").value = s.description || "";
  document.getElementById("f-start").value = tl.start_date || "";
  document.getElementById("f-end").value = tl.end_date || "";
  document.getElementById("f-step").value = tl.time_step_years || 1;
  document.getElementById("f-portfolio").value = st.portfolio_value || 0;
  document.getElementById("f-contrib").value = st.annual_contribution || 0;
  document.getElementById("f-withdraw").value = st.annual_withdrawal || 0;
  document.getElementById("f-return").value = ((unc.expected_return_mean || 0.07) * 100).toFixed(1);
  document.getElementById("f-vol").value = ((unc.volatility_std || 0.15) * 100).toFixed(1);
  document.getElementById("f-floor").value = con.wealth_floor || 0;
  document.getElementById("f-target").value = sc.target_portfolio_value || 0;
  document.getElementById("f-never-below").checked = sc.never_below_floor !== false;
  document.getElementById("f-npaths").value = sim.n_paths || 1000;
  document.getElementById("f-mode").value = sim.mode || "fast";
  document.getElementById("f-seed").value = sim.random_seed != null ? sim.random_seed : "";

  // Rebuild shock events
  document.getElementById("shock-events-list").innerHTML = "";
  shockCounter = 0;
  (unc.shock_events || []).forEach(addShockEventRow);
}

// ─────────────────────────────────────────────
// STATUS BAR
// ─────────────────────────────────────────────
function setStatus(msg, type = "") {
  const bar = document.getElementById("status-bar");
  const txt = document.getElementById("status-text");
  bar.className = type;
  txt.innerHTML = msg;
}

// ─────────────────────────────────────────────
// API
// ─────────────────────────────────────────────
async function runSimulation(config) {
  const res = await fetch("/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail = data.detail || JSON.stringify(data);
    throw new Error(detail);
  }
  return data;
}

// ─────────────────────────────────────────────
// RENDER — STATS
// ─────────────────────────────────────────────
function renderStats(results) {
  const st = results.statistics;
  const sp = st.success_probability;

  // KPI values + color coding
  const spEl = document.getElementById("kpi-success");
  spEl.textContent = fmtPct(sp);
  spEl.className = "kpi-value " + (sp >= 0.8 ? "good" : sp >= 0.5 ? "warn" : "bad");

  document.getElementById("kpi-median").textContent = fmt(st.median_final);
  document.getElementById("kpi-mean").textContent = fmt(st.mean_final);
  document.getElementById("kpi-es").textContent = fmt(st.expected_shortfall_5pct);

  // Percentile table
  const tbody = document.getElementById("pct-table-body");
  tbody.innerHTML = "";
  const pcts = [
    ["5th", "p5"], ["10th", "p10"], ["25th", "p25"], ["50th (Median)", "p50"],
    ["75th", "p75"], ["90th", "p90"], ["95th", "p95"],
  ];
  const median = st.percentiles.p50;
  pcts.forEach(([label, key]) => {
    const val = st.percentiles[key];
    const ratio = median ? ((val / median - 1) * 100).toFixed(0) : 0;
    const sign = ratio >= 0 ? "+" : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${label}</td><td>${fmt(val)}</td><td style="color:${ratio >= 0 ? '#10b981' : '#ef4444'}">${sign}${ratio}%</td>`;
    tbody.appendChild(tr);
  });
}

// ─────────────────────────────────────────────
// RENDER — FAN CHART
// ─────────────────────────────────────────────
function renderFanChart(results) {
  const ctx = document.getElementById("fan-chart").getContext("2d");
  destroyChart(fanChartInstance);

  const labels = results.time_axis.map(y => `Yr ${Math.round(y)}`);
  const fcd = results.fan_chart_data;

  let title = "Portfolio Paths Over Time";
  let datasets;

  if (fcd) {
    title = "Portfolio Fan Chart (Detailed Mode)";
    datasets = [
      {
        label: "p5–p95",
        data: fcd.p95,
        borderColor: "transparent",
        backgroundColor: "rgba(99,102,241,0.08)",
        fill: { target: { value: fcd.p5 }, above: "rgba(99,102,241,0.08)" },
        pointRadius: 0, tension: 0.3,
      },
      { label: "p5",  data: fcd.p5,  borderColor: "rgba(99,102,241,0.25)", borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      { label: "p95", data: fcd.p95, borderColor: "rgba(99,102,241,0.25)", borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      {
        label: "p25–p75",
        data: fcd.p75,
        borderColor: "transparent",
        backgroundColor: "rgba(99,102,241,0.18)",
        fill: { target: { value: fcd.p25 }, above: "rgba(99,102,241,0.18)" },
        pointRadius: 0, tension: 0.3,
      },
      { label: "p25", data: fcd.p25, borderColor: "rgba(99,102,241,0.4)", borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      { label: "p75", data: fcd.p75, borderColor: "rgba(99,102,241,0.4)", borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      { label: "Median", data: fcd.p50, borderColor: "#6366f1", borderWidth: 2.5, pointRadius: 0, tension: 0.3, fill: false },
    ];
  } else {
    // Fast mode: single median-approximated line from final value (no time series)
    title = "Final Value Distribution (Fast Mode — run Detailed for fan chart)";
    datasets = [];
  }

  document.getElementById("fan-chart-title").textContent = title;

  fanChartInstance = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: fcd !== null, position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${fmt(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: { ticks: { font: { size: 11 }, maxTicksLimit: 10 } },
        y: {
          ticks: {
            font: { size: 11 },
            callback: v => "$" + (v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : (v / 1e3).toFixed(0) + "k"),
          },
        },
      },
    },
  });
}

// ─────────────────────────────────────────────
// RENDER — HISTOGRAM
// ─────────────────────────────────────────────
function buildHistogramBins(values, nBins = 40) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = (max - min) / nBins || 1;
  const counts = new Array(nBins).fill(0);
  values.forEach(v => {
    const idx = Math.min(nBins - 1, Math.floor((v - min) / width));
    counts[idx]++;
  });
  const labels = counts.map((_, i) => min + (i + 0.5) * width);
  return { labels, counts, width, min };
}

function renderHistogram(results) {
  const ctx = document.getElementById("hist-chart").getContext("2d");
  destroyChart(histChartInstance);

  const vals = results.final_values;
  const { labels, counts } = buildHistogramBins(vals, 40);
  const st = results.statistics;
  const target = results.statistics.percentiles.p50; // use median as reference line

  histChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels.map(v => fmt(v)),
      datasets: [{
        label: "Paths",
        data: counts,
        backgroundColor: labels.map(v => {
          const floor = results.statistics.expected_shortfall_5pct;
          return v < floor ? "rgba(239,68,68,0.5)" : "rgba(99,102,241,0.5)";
        }),
        borderColor: "transparent",
        borderWidth: 0,
        barPercentage: 1,
        categoryPercentage: 1,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        annotation: {
          annotations: {
            mean: {
              type: "line",
              scaleID: "x",
              value: labels.findIndex(v => v >= st.mean_final),
              borderColor: "#f59e0b",
              borderWidth: 2,
              label: { content: "Mean", enabled: true, position: "start", font: { size: 10 } },
            },
            median: {
              type: "line",
              scaleID: "x",
              value: labels.findIndex(v => v >= st.median_final),
              borderColor: "#10b981",
              borderWidth: 2,
              label: { content: "Median", enabled: true, position: "end", font: { size: 10 } },
            },
          },
        },
        tooltip: {
          callbacks: {
            title: (items) => `~${items[0].label}`,
            label: (item) => `${item.raw} paths`,
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 6, font: { size: 10 }, maxRotation: 0 } },
        y: { ticks: { font: { size: 11 } }, title: { display: true, text: "# Paths", font: { size: 11 } } },
      },
    },
  });
}

// ─────────────────────────────────────────────
// HANDLERS
// ─────────────────────────────────────────────
async function onRun() {
  const btn = document.getElementById("run-btn");
  btn.disabled = true;

  const config = buildConfigFromForm();

  setStatus('<span class="spinner"></span>Running simulation…');

  try {
    const results = await runSimulation(config);
    currentResults = results;

    const dur = results.run_metadata.duration_seconds;
    const n = results.n_paths.toLocaleString();
    setStatus(`Done in ${dur}s &nbsp;|&nbsp; ${n} paths &nbsp;|&nbsp; seed: ${results.run_metadata.random_seed ?? "random"}`, "success");

    document.getElementById("placeholder").classList.add("hidden");
    document.getElementById("results-content").classList.remove("hidden");

    renderStats(results);
    renderFanChart(results);
    renderHistogram(results);

  } catch (err) {
    setStatus("Error: " + err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

function onSave() {
  const config = buildConfigFromForm();
  const name = (config.scenario.name || "scenario").replace(/\s+/g, "_").toLowerCase();
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function onLoad(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const cfg = JSON.parse(e.target.result);
      populateFormFromConfig(cfg);
      setStatus("Scenario loaded: " + (cfg.scenario?.name || file.name));
    } catch {
      setStatus("Failed to parse scenario file — is it valid JSON?", "error");
    }
  };
  reader.readAsText(file);
  input.value = "";  // reset so same file can be loaded again
}

function onDownloadResults() {
  if (!currentResults) return;
  const name = (currentResults.scenario_name || "results").replace(/\s+/g, "_").toLowerCase();
  const blob = new Blob([JSON.stringify(currentResults, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}_results.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Register annotation plugin
  if (window.ChartjsPluginAnnotation) {
    Chart.register(window.ChartjsPluginAnnotation);
  }

  // Wire Enter key on Run button
  document.getElementById("run-btn").addEventListener("keydown", e => {
    if (e.key === "Enter") onRun();
  });
});
