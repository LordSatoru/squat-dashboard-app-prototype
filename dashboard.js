const scheme = location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${scheme}://${location.host}/ws`);

const f1AccCanvas = document.getElementById("f1AccChart");
const f1GyroCanvas = document.getElementById("f1GyroChart");
const f1AngleCanvas = document.getElementById("f1AngleChart");
const f2AccCanvas = document.getElementById("f2AccChart");
const f2GyroCanvas = document.getElementById("f2GyroChart");
const f2AngleCanvas = document.getElementById("f2AngleChart");
const polarCanvas = document.getElementById("polarChart");

const f1AccCtx = f1AccCanvas.getContext("2d");
const f1GyroCtx = f1GyroCanvas.getContext("2d");
const f1AngleCtx = f1AngleCanvas.getContext("2d");
const f2AccCtx = f2AccCanvas.getContext("2d");
const f2GyroCtx = f2GyroCanvas.getContext("2d");
const f2AngleCtx = f2AngleCanvas.getContext("2d");
const polarCtx = polarCanvas.getContext("2d");

const chartState = {
  f1Acc: { ax: true, ay: true, az: true },
  f1Gyro: { gx: true, gy: true, gz: true },
  f1Angle: { angle_x: true, angle_y: true, angle_mag_disabled: true },
  f2Acc: { ax: true, ay: true, az: true },
  f2Gyro: { gx: true, gy: true, gz: true },
  f2Angle: { angle_x: true, angle_y: true, angle_mag_disabled: true },
  polar: { acc_x: true, acc_y: true, acc_z: true },
};

function setText(id, value) {
  document.getElementById(id).textContent = value ?? "-";
}

function buildLegendControls(containerId, config, stateKey) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  config.forEach(item => {
    const btn = document.createElement("button");
    btn.className = `legend-btn ${item.className}`;
    btn.textContent = item.label;
    btn.dataset.key = item.key;
    btn.onclick = () => {
      chartState[stateKey][item.key] = !chartState[stateKey][item.key];
      refreshLegendStyles();
    };
    el.appendChild(btn);
  });
}

function refreshLegendStyles() {
  document.querySelectorAll(".legend-controls").forEach(group => {
    const groupId = group.id;
    const map = {
      f1AccLegendControls: chartState.f1Acc,
      f1GyroLegendControls: chartState.f1Gyro,
      f1AngleLegendControls: chartState.f1Angle,
      f2AccLegendControls: chartState.f2Acc,
      f2GyroLegendControls: chartState.f2Gyro,
      f2AngleLegendControls: chartState.f2Angle,
      polarLegendControls: chartState.polar,
    };
    const state = map[groupId];
    if (!state) return;

    group.querySelectorAll("button").forEach(btn => {
      const key = btn.dataset.key;
      btn.classList.remove("inactive");
      if (!state[key]) btn.classList.add("inactive");
    });
  });
}

buildLegendControls("f1AccLegendControls", [
  { key: "ax", label: "F1 ACC X", className: "active-blue" },
  { key: "ay", label: "F1 ACC Y", className: "active-red" },
  { key: "az", label: "F1 ACC Z", className: "active-green" }
], "f1Acc");
buildLegendControls("f1GyroLegendControls", [
  { key: "gx", label: "F1 GYRO X", className: "active-purple" },
  { key: "gy", label: "F1 GYRO Y", className: "active-blue" },
  { key: "gz", label: "F1 GYRO Z", className: "active-red" }
], "f1Gyro");
buildLegendControls("f1AngleLegendControls", [
  { key: "angle_x", label: "F1 Angle X°", className: "active-blue" },
  { key: "angle_y", label: "F1 Angle Y°", className: "active-red" },
  { key: "angle_mag_disabled", label: "F1 Angle Mag", className: "active-green" }
], "f1Angle");

buildLegendControls("f2AccLegendControls", [
  { key: "ax", label: "F2 ACC X", className: "active-blue" },
  { key: "ay", label: "F2 ACC Y", className: "active-purple" },
  { key: "az", label: "F2 ACC Z", className: "active-green" }
], "f2Acc");
buildLegendControls("f2GyroLegendControls", [
  { key: "gx", label: "F2 GYRO X", className: "active-red" },
  { key: "gy", label: "F2 GYRO Y", className: "active-blue" },
  { key: "gz", label: "F2 GYRO Z", className: "active-purple" }
], "f2Gyro");
buildLegendControls("f2AngleLegendControls", [
  { key: "angle_x", label: "F2 Angle X°", className: "active-green" },
  { key: "angle_y", label: "F2 Angle Y°", className: "active-orange" },
  { key: "angle_mag_disabled", label: "F2 Angle Mag", className: "active-blue" }
], "f2Angle");

buildLegendControls("polarLegendControls", [
  { key: "acc_x", label: "ACC X", className: "active-blue" },
  { key: "acc_y", label: "ACC Y", className: "active-red" },
  { key: "acc_z", label: "ACC Z", className: "active-green" }
], "polar");

refreshLegendStyles();

function drawAxesOnly(ctx, left, right, top, bottom, minV, maxV, yLabel, xLabel, t) {
  for (let i = 0; i <= 4; i++) {
    const y = top + ((bottom - top) * i / 4);
    ctx.beginPath();
    ctx.strokeStyle = "#e8eef5";
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  }

  const tickCount = 6;
  for (let i = 0; i < tickCount; i++) {
    const x = left + ((right - left) * i / (tickCount - 1));
    ctx.beginPath();
    ctx.strokeStyle = "#f1f5f9";
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
  }

  ctx.beginPath();
  ctx.strokeStyle = "#94a3b8";
  ctx.lineWidth = 1;
  ctx.moveTo(left, top);
  ctx.lineTo(left, bottom);
  ctx.lineTo(right, bottom);
  ctx.stroke();

  ctx.fillStyle = "#334155";
  ctx.font = "12px Arial";
  ctx.fillText(maxV.toFixed(2), 12, top + 4);
  ctx.fillText(((maxV + minV) / 2).toFixed(2), 12, top + (bottom - top) / 2 + 4);
  ctx.fillText(minV.toFixed(2), 12, bottom + 4);
  ctx.fillText(yLabel, 12, top - 10);
  ctx.fillText(xLabel, right - 60, bottom + 34);

  if (Array.isArray(t) && t.length >= 2) {
    for (let i = 0; i < tickCount; i++) {
      const idx = Math.round((t.length - 1) * i / (tickCount - 1));
      const x = left + ((right - left) * i / (tickCount - 1));
      ctx.fillStyle = "#64748b";
      ctx.fillText(`${Number(t[idx]).toFixed(1)}s`, x - 14, bottom + 18);
    }
  }
}

function drawSeries(ctx, canvas, t, series, options = {}) {
  const w = canvas.width;
  const h = canvas.height;
  const left = 72;
  const right = w - 24;
  const top = 34;
  const bottom = h - 54;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);

  const activeSeries = series.filter(s => s.visible);
  const flat = [];
  activeSeries.forEach(s => {
    (s.values || []).forEach(v => {
      if (v !== null && v !== undefined && !Number.isNaN(v)) flat.push(Number(v));
    });
  });

  if (!Array.isArray(t) || t.length < 2 || flat.length === 0) {
    drawAxesOnly(ctx, left, right, top, bottom, -1, 1, options.yLabel || "value", options.xLabel || "time", []);
    ctx.fillStyle = "#64748b";
    ctx.font = "14px Arial";
    ctx.fillText("toggle a line on, or wait for data...", left + 12, top + 24);
    return;
  }

  const minV = Math.min(...flat);
  const maxRaw = Math.max(...flat);
  const maxV = maxRaw === minV ? minV + 1 : maxRaw;
  drawAxesOnly(ctx, left, right, top, bottom, minV, maxV, options.yLabel || "value", options.xLabel || "time", t);

  const xSpan = Math.max(t.length - 1, 1);
  const ySpan = maxV - minV;

  activeSeries.forEach(s => {
    if (!Array.isArray(s.values) || s.values.length === 0) return;
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 2.5;
    ctx.setLineDash(s.dashed ? [10, 7] : []);
    ctx.beginPath();
    s.values.forEach((rawV, i) => {
      const v = rawV ?? minV;
      const x = left + (i / xSpan) * (right - left);
      const y = bottom - ((v - minV) / ySpan) * (bottom - top);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  ctx.setLineDash([]);
}

ws.onopen = () => console.log("ws connected");
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  setText("ready", data.ready ? "READY" : "WAITING");
  setText("hr", data.hr);
  setText("updated", data.last_update ?? "-");

  setText("polar_status", data.polar_status);
  setText("f1_status", data.flex1_status);
  setText("f2_status", data.flex2_status);

  setText("px", data.polar?.acc_x);
  setText("py", data.polar?.acc_y);
  setText("pz", data.polar?.acc_z);

  setText("f1_ax", data.flex1?.ax);
  setText("f1_ay", data.flex1?.ay);
  setText("f1_az", data.flex1?.az);
  setText("f1_gx", data.flex1?.gx);
  setText("f1_gy", data.flex1?.gy);
  setText("f1_gz", data.flex1?.gz);
  setText("f1_anglex", data.flex1?.angle_x);
  setText("f1_angley", data.flex1?.angle_y);
  setText("f1_gesture", data.flex1_gesture);

  setText("f2_ax", data.flex2?.ax);
  setText("f2_ay", data.flex2?.ay);
  setText("f2_az", data.flex2?.az);
  setText("f2_gx", data.flex2?.gx);
  setText("f2_gy", data.flex2?.gy);
  setText("f2_gz", data.flex2?.gz);
  setText("f2_anglex", data.flex2?.angle_x);
  setText("f2_angley", data.flex2?.angle_y);
  setText("f2_gesture", data.flex2_gesture);

  document.getElementById("log").innerHTML = (data.log || []).map(x => `<div>${x}</div>`).join("");

  const h = data.history || {};
  const f1 = h.flex1 || {};
  const f2 = h.flex2 || {};
  const p = h.polar || {};

  drawSeries(f1AccCtx, f1AccCanvas, f1.t || [], [
    { values: f1.ax || [], color: "#2563eb", visible: chartState.f1Acc.ax, dashed: false },
    { values: f1.ay || [], color: "#dc2626", visible: chartState.f1Acc.ay, dashed: false },
    { values: f1.az || [], color: "#16a34a", visible: chartState.f1Acc.az, dashed: false },
  ], { yLabel: "acceleration", xLabel: "time" });

  drawSeries(f1GyroCtx, f1GyroCanvas, f1.t || [], [
    { values: f1.gx || [], color: "#9333ea", visible: chartState.f1Gyro.gx, dashed: false },
    { values: f1.gy || [], color: "#0ea5e9", visible: chartState.f1Gyro.gy, dashed: false },
    { values: f1.gz || [], color: "#ef4444", visible: chartState.f1Gyro.gz, dashed: false },
  ], { yLabel: "gyro", xLabel: "time" });

  drawSeries(f1AngleCtx, f1AngleCanvas, f1.t || [], [
    { values: f1.angle_x || [], color: "#2563eb", visible: chartState.f1Angle.angle_x, dashed: false },
    { values: f1.angle_y || [], color: "#dc2626", visible: chartState.f1Angle.angle_y, dashed: false },
    { values: f1.angle_mag_disabled || [], color: "#16a34a", visible: chartState.f1Angle.angle_mag_disabled, dashed: false },
  ], { yLabel: "angle (deg)", xLabel: "time" });

  drawSeries(f2AccCtx, f2AccCanvas, f2.t || [], [
    { values: f2.ax || [], color: "#2563eb", visible: chartState.f2Acc.ax, dashed: true },
    { values: f2.ay || [], color: "#9333ea", visible: chartState.f2Acc.ay, dashed: true },
    { values: f2.az || [], color: "#16a34a", visible: chartState.f2Acc.az, dashed: true },
  ], { yLabel: "acceleration", xLabel: "time" });

  drawSeries(f2GyroCtx, f2GyroCanvas, f2.t || [], [
    { values: f2.gx || [], color: "#ef4444", visible: chartState.f2Gyro.gx, dashed: true },
    { values: f2.gy || [], color: "#0ea5e9", visible: chartState.f2Gyro.gy, dashed: true },
    { values: f2.gz || [], color: "#a855f7", visible: chartState.f2Gyro.gz, dashed: true },
  ], { yLabel: "gyro", xLabel: "time" });

  drawSeries(f2AngleCtx, f2AngleCanvas, f2.t || [], [
    { values: f2.angle_x || [], color: "#22c55e", visible: chartState.f2Angle.angle_x, dashed: true },
    { values: f2.angle_y || [], color: "#f97316", visible: chartState.f2Angle.angle_y, dashed: true },
    { values: f2.angle_mag_disabled || [], color: "#1d4ed8", visible: chartState.f2Angle.angle_mag_disabled, dashed: true },
  ], { yLabel: "angle (deg)", xLabel: "time" });

  drawSeries(polarCtx, polarCanvas, p.t || [], [
    { values: p.acc_x || [], color: "#2563eb", visible: chartState.polar.acc_x, dashed: false },
    { values: p.acc_y || [], color: "#dc2626", visible: chartState.polar.acc_y, dashed: false },
    { values: p.acc_z || [], color: "#16a34a", visible: chartState.polar.acc_z, dashed: false },
  ], { yLabel: "acceleration (g)", xLabel: "time" });
};

ws.onerror = (e) => console.log("ws error", e);
ws.onclose = () => console.log("ws closed");
