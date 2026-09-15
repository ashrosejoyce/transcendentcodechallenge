// Community Voices frontend. No build step, no framework - talks to the
// FastAPI backend's JSON endpoints and renders everything with plain DOM APIs.
//
// Deliberately decoupled from the backend: this is a separate static
// server/process, always on its own port, talking to the API cross-origin
// over CORS rather than being proxied behind one origin. The backend is
// assumed to be reachable on port 8080 of whatever host served this page -
// true for both the Docker Compose setup and running both halves locally.
const API_BASE = `${location.protocol}//${location.hostname}:8080`;

const $ = (id) => document.getElementById(id);

async function fetchJSON(path, options) {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${url} failed with ${response.status}`);
  }
  return response.json();
}

function setText(id, value) {
  $(id).textContent = value;
}

// ---- community (which forum this deployment is configured for) --------

async function loadCommunityInfo() {
  const { community_name: communityName } = await fetchJSON("/api/community");
  document.title = `Community Voices · ${communityName}`;
  setText("community-subtitle", `${communityName} — RAG-generated digest`);
}

// ---- stats -----------------------------------------------------------

async function loadStats() {
  const stats = await fetchJSON("/api/stats");
  setText("stat-posts", stats.post_count.toLocaleString());
  setText("stat-chunks", stats.chunk_count.toLocaleString());
  setText("stat-boards", stats.board_count.toLocaleString());
  setText(
    "stat-range",
    stats.earliest_post
      ? `${formatDate(stats.earliest_post)} – ${formatDate(stats.latest_post)}`
      : "no data yet"
  );
  renderRetrievalBars(stats.most_retrieved_chunks);
  return stats;
}

function formatDate(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---- ingest ------------------------------------------------------------

$("ingest-btn").addEventListener("click", async () => {
  const button = $("ingest-btn");
  button.disabled = true;
  button.textContent = "Crawling forum …";
  try {
    const report = await fetchJSON("/api/ingest", { method: "POST" });
    $("ingest-log-panel").hidden = false;
    $("ingest-log").textContent = JSON.stringify(report, null, 2);
    await loadStats();
    await loadEmbeddingVisualization();
  } catch (error) {
    $("ingest-log-panel").hidden = false;
    $("ingest-log").textContent = `Ingest failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = "Refresh data from forum";
  }
});

// ---- generate (A/B) -----------------------------------------------------

// Possessive phrasing per timeframe, used only for button/hint copy - the
// document's own section headings come from the backend (see
// generation/timeframe.py) and always match whatever was actually used.
const TIMEFRAME_POSSESSIVE = { day: "today's", week: "this week's", month: "this month's", year: "this year's" };

function generateButtonLabel() {
  const timeframe = $("timeframe-select").value;
  const possessive = TIMEFRAME_POSSESSIVE[timeframe] || "this week's";
  return `Generate ${possessive} document`;
}

let lastReport = null; // the full /api/generate result - populated after a successful generate

$("timeframe-select").addEventListener("change", () => {
  $("generate-btn").textContent = generateButtonLabel();
});

$("generate-btn").addEventListener("click", async () => {
  const button = $("generate-btn");
  const timeframe = $("timeframe-select").value;
  button.disabled = true;
  button.textContent = "Generating …";
  try {
    const result = await fetchJSON("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timeframe }),
    });
    $("rag-doc").textContent = result.rag_document;
    $("baseline-doc").textContent = result.baseline_document;
    renderSources(result.retrieved_chunks);
    setDownloadableReport(result);
    await loadStats(); // retrieval counts just changed
    await loadEmbeddingVisualization();
  } catch (error) {
    $("rag-doc").textContent = `Generation failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = generateButtonLabel();
  }
});

function setDownloadableReport(result) {
  lastReport = result;
  $("download-report-btn").hidden = false;
}

$("download-report-btn").addEventListener("click", async () => {
  if (!lastReport) return;
  const button = $("download-report-btn");
  button.disabled = true;
  button.textContent = "Preparing PDF …";
  try {
    const response = await fetch(`${API_BASE}/api/report/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastReport),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `PDF generation failed with ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = lastReport.report_filename;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    alert(`Couldn't prepare the PDF: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "Download report";
  }
});

function renderSources(chunks) {
  setText("sources-count", String(chunks.length));
  const tbody = $("sources-body");
  tbody.replaceChildren();
  for (const chunk of chunks) {
    const row = document.createElement("tr");
    row.append(
      cell(chunk.board),
      cell(chunk.subject),
      cell(chunk.author),
      cell(formatDate(chunk.posted_at)),
      cell(chunk.distance.toFixed(3))
    );
    tbody.appendChild(row);
  }
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

// ---- retrieval bar chart -------------------------------------------------

const MIN_BAR_FILL_PERCENT = 6;
const BAR_LABEL_INSIDE_THRESHOLD_PERCENT = 15;

function renderRetrievalBars(rows) {
  const container = $("retrieval-bars");
  container.replaceChildren();
  if (!rows || rows.length === 0) {
    container.appendChild(emptyState("No retrievals logged yet - generate a document first."));
    return;
  }
  const max = Math.max(...rows.map((r) => r.retrieval_count), 1);
  for (const row of rows) {
    container.appendChild(buildBarRow(row, max));
  }
}

function buildBarRow(row, max) {
  const wrapper = document.createElement("div");
  wrapper.className = "bar-row";

  const label = document.createElement("div");
  label.className = "bar-label";
  label.textContent = `${row.subject} — ${row.board}`;
  label.title = row.subject;

  const fillPercent =
    row.retrieval_count > 0 ? Math.max((row.retrieval_count / max) * 100, MIN_BAR_FILL_PERCENT) : 0;

  wrapper.append(label, buildBarTrack(row.retrieval_count, fillPercent));
  return wrapper;
}

function buildBarTrack(value, fillPercent) {
  const track = document.createElement("div");
  track.className = "bar-track";

  const fill = document.createElement("div");
  fill.className = "bar-fill";
  fill.style.width = `${fillPercent}%`;

  const valueLabel = document.createElement("span");
  valueLabel.className = "bar-value";
  valueLabel.textContent = String(value);

  if (fillPercent < BAR_LABEL_INSIDE_THRESHOLD_PERCENT) {
    // Not enough room inside the fill for the number - put it just past
    // the bar's end instead of letting it clip (marks-and-anatomy.md:
    // "a value pushed off its mark lives" beside it, never hidden).
    valueLabel.classList.add("bar-value-outside");
    valueLabel.style.left = `calc(${fillPercent}% + 6px)`;
    track.append(fill, valueLabel);
  } else {
    fill.appendChild(valueLabel);
    track.appendChild(fill);
  }
  return track;
}

function emptyState(message) {
  const div = document.createElement("div");
  div.className = "empty-state";
  div.textContent = message;
  return div;
}

// ---- embedding scatter plot ----------------------------------------------

const SERIES_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
const OTHER_COLOR = "var(--series-other)";
const SVG_NS = "http://www.w3.org/2000/svg";
const VIEW_W = 480;
const VIEW_H = 380;
const PAD = 28;

async function loadEmbeddingVisualization() {
  const points = await fetchJSON("/api/embeddings/visualization");
  renderEmbeddingScatter(points);
}

function renderEmbeddingScatter(points) {
  const svg = $("embedding-svg");
  svg.replaceChildren();

  if (!points || points.length === 0) {
    $("embedding-legend").replaceChildren(emptyState("No embeddings yet - refresh data first."));
    return;
  }

  const boardCounts = new Map();
  for (const p of points) boardCounts.set(p.board, (boardCounts.get(p.board) || 0) + 1);
  const topBoards = [...boardCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([board]) => board);
  const colorFor = (board) => {
    const index = topBoards.indexOf(board);
    return index === -1 ? OTHER_COLOR : SERIES_COLORS[index];
  };

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const scaleX = makeScale(Math.min(...xs), Math.max(...xs), PAD, VIEW_W - PAD);
  const scaleY = makeScale(Math.min(...ys), Math.max(...ys), VIEW_H - PAD, PAD);

  const tooltip = $("embedding-tooltip");

  for (const point of points) {
    const cx = scaleX(point.x);
    const cy = scaleY(point.y);
    const color = colorFor(point.board);

    const hit = document.createElementNS(SVG_NS, "circle");
    hit.setAttribute("cx", cx);
    hit.setAttribute("cy", cy);
    hit.setAttribute("r", "12");
    hit.setAttribute("class", "viz-hit");

    const dot = document.createElementNS(SVG_NS, "circle");
    dot.setAttribute("cx", cx);
    dot.setAttribute("cy", cy);
    dot.setAttribute("r", "5");
    dot.setAttribute("fill", color);
    dot.setAttribute("stroke", "var(--surface-1)");
    dot.setAttribute("stroke-width", "2");
    dot.setAttribute("class", "viz-dot");

    const showTooltip = (evt) => {
      tooltip.hidden = false;
      tooltip.style.left = `${evt.offsetX}px`;
      tooltip.style.top = `${evt.offsetY}px`;
      tooltip.replaceChildren();
      const title = document.createElement("div");
      title.className = "tooltip-value";
      title.textContent = point.subject;
      const meta = document.createElement("div");
      meta.textContent = `${point.board} · retrieved ${point.retrieval_count}×`;
      const snippet = document.createElement("div");
      snippet.textContent = point.snippet;
      tooltip.append(title, meta, snippet);
    };
    const hideTooltip = () => { tooltip.hidden = true; };

    for (const el of [hit, dot]) {
      el.addEventListener("pointerenter", showTooltip);
      el.addEventListener("pointermove", showTooltip);
      el.addEventListener("pointerleave", hideTooltip);
    }

    svg.appendChild(hit);
    svg.appendChild(dot);
  }

  renderLegend(topBoards, boardCounts.size > topBoards.length);
}

function renderLegend(topBoards, hasOther) {
  const legend = $("embedding-legend");
  legend.replaceChildren();
  topBoards.forEach((board, i) => legend.appendChild(legendItem(board, SERIES_COLORS[i])));
  if (hasOther) legend.appendChild(legendItem("Other boards", OTHER_COLOR));
}

function legendItem(label, color) {
  const item = document.createElement("div");
  item.className = "legend-item";
  const swatch = document.createElement("span");
  swatch.className = "legend-swatch";
  swatch.style.background = color;
  const text = document.createElement("span");
  text.textContent = label;
  item.append(swatch, text);
  return item;
}

function makeScale(domainMin, domainMax, rangeMin, rangeMax) {
  const domainSpan = domainMax - domainMin || 1;
  return (value) => rangeMin + ((value - domainMin) / domainSpan) * (rangeMax - rangeMin);
}

// ---- boot ----------------------------------------------------------------

(async function init() {
  try {
    await loadCommunityInfo();
    await loadStats();
    await loadEmbeddingVisualization();
  } catch (error) {
    console.error("Initial load failed", error);
  }
})();
