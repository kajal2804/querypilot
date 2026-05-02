/* QueryPilot — app.js */

// ── tab switching ─────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('[id^="tab-"]').forEach(t => t.style.display = 'none');
  document.getElementById(`tab-${name}`).style.display = 'block';
  event.target.classList.add('active');
  if (name === 'docs') loadDocs();
}

// ── docs tab ─────────────────────────────────────────────────────────────────
async function loadDocs() {
  const list = document.getElementById('docsList');
  list.innerHTML = '<div class="doc-empty">Loading…</div>';
  try {
    const data = await (await fetch('/docs-list')).json();
    if (!data.documents.length) {
      list.innerHTML = '<div class="doc-empty">No documents ingested yet. Upload a PDF or text file above.</div>';
    } else {
      list.innerHTML = data.documents.map(d =>
        `<div class="doc-row">📄 ${d}</div>`
      ).join('') + `<div class="doc-empty" style="margin-top:.5rem">${data.total_chunks} total chunks indexed</div>`;
    }
  } catch { list.innerHTML = '<div class="doc-empty" style="color:var(--error)">Failed to load.</div>'; }
}

async function uploadDoc() {
  const fileInput = document.getElementById('docFile');
  const status    = document.getElementById('uploadStatus');
  if (!fileInput.files[0]) { status.textContent = 'Please select a file first.'; status.className = 'upload-status err'; return; }

  const btn  = document.getElementById('uploadBtn');
  btn.disabled = true;
  status.textContent = 'Uploading…'; status.className = 'upload-status';

  const form = new FormData();
  form.append('file', fileInput.files[0]);

  try {
    const resp = await fetch('/upload-doc', { method: 'POST', body: form });
    const data = await resp.json();
    if (resp.ok) {
      status.textContent = `✅ ${data.message} (${data.chunks} chunks indexed)`;
      status.className = 'upload-status ok';
      loadDocs();
    } else {
      status.textContent = `❌ ${data.detail}`;
      status.className = 'upload-status err';
    }
  } catch (err) {
    status.textContent = `❌ ${err.message}`; status.className = 'upload-status err';
  } finally { btn.disabled = false; }
}

// ── run tests ─────────────────────────────────────────────────────────────────
async function runTests() {
  const btn = document.getElementById('runTestsBtn');
  btn.disabled  = true;
  btn.textContent = '⏳ Running…';

  document.getElementById('testSummary').style.display = 'none';
  document.getElementById('logDetails').style.display = 'none';
  document.getElementById('testResults').innerHTML = `
    <div class="test-row" style="justify-content:center;gap:.75rem;color:var(--muted)">
      <div class="dot-pulse"><span></span><span></span><span></span></div>
      Running tests… this may take 20–30s (live Groq API calls)
    </div>`;

  try {
    const resp = await fetch('/run-tests');
    const data = await resp.json();

    // Summary bar
    document.getElementById('passCount').textContent  = `✅ ${data.passed} passed`;
    document.getElementById('failCount').textContent  = data.failed > 0 ? `❌ ${data.failed} failed` : '';
    document.getElementById('totalCount').textContent = `/ ${data.total} total`;
    document.getElementById('summaryTime').textContent = data.summary;
    document.getElementById('testSummary').style.display = 'flex';

    // Individual rows
    const container = document.getElementById('testResults');
    data.tests.forEach(t => {
      const isPassed = t.status === 'PASSED';
      const row = document.createElement('div');
      row.className = `test-row ${isPassed ? 'pass' : 'fail'}`;
      row.innerHTML = `
        <span class="test-badge ${isPassed ? 'pass' : 'fail'}">${t.status}</span>
        <span class="test-name">${t.name}</span>
      `;
      container.appendChild(row);
    });

    // Raw log
    document.getElementById('rawLog').textContent = data.log;
    document.getElementById('logDetails').style.display = 'block';

  } catch (err) {
    document.getElementById('testResults').innerHTML =
      `<div class="test-row fail"><span class="test-badge fail">ERROR</span><span class="test-name">${err.message}</span></div>`;
  } finally {
    btn.disabled    = false;
    btn.textContent = '▶ Run Tests';
  }
}

const input  = document.getElementById('question');
const askBtn = document.getElementById('askBtn');

// ── agent node refs ───────────────────────────────────────────────────────────
const NODES  = ['schema', 'sql', 'retriever', 'synth'];
const ARROWS = [1, 2, 3];
const LABELS = {
  schema:    { active: 'Identifying tables…', done: 'Tables identified ✓' },
  sql:       { active: 'Generating SQL…',     done: 'SQL generated ✓'     },
  retriever: { active: 'Executing query…',    done: 'Rows retrieved ✓'    },
  synth:     { active: 'Synthesizing answer…',done: 'Answer ready ✓'      },
};

function resetPipeline() {
  NODES.forEach(id => {
    const node = document.getElementById(`node-${id}`);
    node.classList.remove('active', 'done', 'error');
    document.getElementById(`status-${id}`).textContent = '';
  });
  ARROWS.forEach(i => {
    document.getElementById(`arrow-${i}`).classList.remove('lit');
  });
}

function activateNode(id) {
  const node = document.getElementById(`node-${id}`);
  node.classList.add('active');
  document.getElementById(`status-${id}`).innerHTML =
    `<span class="spinner-dot"></span>${LABELS[id].active}`;
}

function doneNode(id, arrowAfter) {
  const node = document.getElementById(`node-${id}`);
  node.classList.remove('active');
  node.classList.add('done');
  document.getElementById(`status-${id}`).textContent = LABELS[id].done;
  if (arrowAfter) {
    document.getElementById(`arrow-${arrowAfter}`).classList.add('lit');
  }
}

function errorNode(id) {
  const node = document.getElementById(`node-${id}`);
  node.classList.remove('active');
  node.classList.add('error');
  document.getElementById(`status-${id}`).textContent = 'Failed ✗';
}

// ── example chips ─────────────────────────────────────────────────────────────
function setQ(el) {
  input.value = el.textContent.trim();
  input.focus();
}

input.addEventListener('keydown', e => { if (e.key === 'Enter') askQuestion(); });

// ── main flow ─────────────────────────────────────────────────────────────────
async function askQuestion() {
  const q = input.value.trim();
  if (!q) return;

  document.getElementById('result').classList.remove('visible');
  askBtn.disabled = true;
  resetPipeline();

  // Animate pipeline step by step with delays to show the flow
  const STEP_MS = 400;

  activateNode('schema');

  try {
    // Small delay so viewer sees each step light up
    await delay(STEP_MS);
    doneNode('schema', 1);
    activateNode('sql');

    await delay(STEP_MS);
    doneNode('sql', 2);
    activateNode('retriever');

    await delay(STEP_MS);
    doneNode('retriever', 3);
    activateNode('synth');

    // Now actually call the API
    const res  = await fetch('/ask', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ question: q }),
    });
    const data = await res.json();

    doneNode('synth');
    render(data);

  } catch (err) {
    errorNode('synth');
    renderError('Network error: ' + err.message);
  } finally {
    askBtn.disabled = false;
  }
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── chart ─────────────────────────────────────────────────────────────────────
let _chart     = null;
let _chartData = null;
let _chartType = 'bar';

const PALETTE = [
  '#6c63ff','#a78bfa','#34d399','#fbbf24','#f87171',
  '#60a5fa','#fb923c','#a3e635','#e879f9','#2dd4bf',
];

function detectChartable(columns, rows) {
  if (!columns || columns.length < 2 || !rows || rows.length < 2) return null;
  for (let vi = 1; vi < columns.length; vi++) {
    const sample = rows.slice(0, 5).map(r => r[vi]);
    if (sample.every(v => v !== null && !isNaN(Number(v)))) {
      return { labelCol: columns[0], valueCol: columns[vi], labelIdx: 0, valueIdx: vi };
    }
  }
  return null;
}

function renderChart(columns, rows, type) {
  const info = detectChartable(columns, rows);
  const card = document.getElementById('chartCard');
  if (!info) { card.style.display = 'none'; return; }

  _chartData = {
    labels:   rows.map(r => String(r[info.labelIdx])),
    values:   rows.map(r => Number(r[info.valueIdx])),
    labelCol: info.labelCol,
    valueCol: info.valueCol,
  };
  _chartType = type || _chartType;
  document.getElementById('chartTitle').textContent =
    `📊 ${info.valueCol} by ${info.labelCol}`;
  card.style.display = 'block';
  _drawChart();
}

function _drawChart() {
  if (!_chartData) return;
  const ctx = document.getElementById('resultChart').getContext('2d');
  if (_chart) { _chart.destroy(); _chart = null; }
  const isDoughnut = _chartType === 'doughnut';
  _chart = new Chart(ctx, {
    type: _chartType,
    data: {
      labels:   _chartData.labels,
      datasets: [{
        label:           _chartData.valueCol,
        data:            _chartData.values,
        backgroundColor: isDoughnut ? PALETTE : PALETTE[0] + 'cc',
        borderColor:     isDoughnut ? PALETTE : PALETTE[0],
        borderWidth:     isDoughnut ? 2 : 1.5,
        borderRadius:    _chartType === 'bar' ? 6 : 0,
        tension:         0.4,
        fill:            _chartType === 'line',
        pointBackgroundColor: PALETTE[0],
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: isDoughnut, labels: { color: '#94a3b8', font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => {
              const num = isDoughnut ? ctx.raw : ctx.parsed.y;
              return ` ${Number(num).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
            },
          },
        },
      },
      scales: isDoughnut ? {} : {
        x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#2e3147' } },
        y: { ticks: { color: '#94a3b8', font: { size: 10 },
               callback: v => v >= 1000 ? (v/1000).toFixed(1)+'k' : v },
             grid: { color: '#2e3147' } },
      },
    },
  });
}

function setChartType(type, btn) {
  document.querySelectorAll('.chart-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _chartType = type;
  _drawChart();
}

// ── render ────────────────────────────────────────────────────────────────────
function render(data) {
  const card = document.getElementById('answerCard');

  if (data.error) {
    card.classList.add('error-card');
    card.querySelector('.tag').textContent = 'Error';
    document.getElementById('answerText').textContent = data.error;
  } else {
    card.classList.remove('error-card');
    card.querySelector('.tag').textContent = 'Answer';
    document.getElementById('answerText').textContent = data.answer || '—';
  }

  // Retried badge
  const badge = document.getElementById('retriedBadge');
  badge.style.display = data.retried ? 'block' : 'none';

  // Cache badge
  document.getElementById('cacheBadge').style.display = data.from_cache ? 'block' : 'none';
  if (data.retried) {
    errorNode('retriever');
    document.getElementById('status-retriever').textContent = 'Failed → Auto-fixed ✓';
    document.getElementById(`node-retriever`).classList.remove('error');
    document.getElementById(`node-retriever`).classList.add('done');
  }

  // Step 1 — relevant tables
  document.getElementById('schemaTables').textContent =
    (data.relevant_tables || []).join(', ') || '—';

  // Step 2 — SQL
  document.getElementById('sqlBlock').textContent = data.sql_query || '—';

  // Step 3 — rows
  const table = document.getElementById('rowsTable');
  table.innerHTML = '';
  if (data.columns && data.columns.length) {
    const thead = table.createTHead();
    const hrow  = thead.insertRow();
    data.columns.forEach(col => {
      const th = document.createElement('th');
      th.textContent = col;
      hrow.appendChild(th);
    });
    const tbody = table.createTBody();
    (data.rows || []).forEach(row => {
      const tr = tbody.insertRow();
      row.forEach(val => {
        const td = tr.insertCell();
        td.textContent = (val === null || val === undefined) ? 'NULL' : val;
      });
    });
  } else {
    table.innerHTML = '<tr><td style="color:var(--muted)">No rows returned.</td></tr>';
  }

  document.getElementById('rowCount').textContent =
    data.row_count != null ? `${data.row_count} row(s) returned` : '';

  // Doc context
  const docDetails = document.getElementById('docContextDetails');
  const docBody    = document.getElementById('docContextBody');
  if (data.doc_context && data.doc_context.length) {
    docBody.innerHTML = data.doc_context.map(d =>
      `<div style="margin-bottom:.75rem">
        <div style="font-size:.75rem;color:var(--accent2);margin-bottom:.25rem">📄 ${d.source} (score: ${d.score})</div>
        <pre style="white-space:pre-wrap;font-size:.78rem">${d.text}</pre>
      </div>`
    ).join('');
    docDetails.style.display = 'block';
  } else {
    docDetails.style.display = 'none';
  }

  // Chart
  renderChart(data.columns, data.rows, 'bar');
  // Reset chart type buttons to Bar
  document.querySelectorAll('.chart-btn').forEach((b,i) => b.classList.toggle('active', i===0));

  document.getElementById('result').classList.add('visible');
}

function renderError(msg) {
  const card = document.getElementById('answerCard');
  card.classList.add('error-card');
  card.querySelector('.tag').textContent = 'Error';
  document.getElementById('answerText').textContent = msg;
  document.getElementById('schemaTables').textContent = '—';
  document.getElementById('sqlBlock').textContent     = '—';
  document.getElementById('rowsTable').innerHTML      = '';
  document.getElementById('rowCount').textContent     = '';
  document.getElementById('chartCard').style.display  = 'none';
  document.getElementById('result').classList.add('visible');
}
