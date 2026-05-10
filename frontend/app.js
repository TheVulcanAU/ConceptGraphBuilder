'use strict';

const API = '';  // same origin

// ── Edge / node colours (mirror CSS vars) ──────────────────────────────────
const EDGE_COLORS = {
  'supports':    '#4caf7d',
  'contradicts': '#e05a5a',
  'depends-on':  '#7c9ef8',
  'example-of':  '#f5a623',
  'defines':     '#c77dff',
  'refines':     '#4fc3f7',
};
const NODE_COLORS = {
  'concept':    '#7c9ef8',
  'claim':      '#4caf7d',
  'assumption': '#f5a623',
  'entity':     '#c77dff',
};

// ── State ──────────────────────────────────────────────────────────────────
let cy = null;
let currentGraph = null;
let activeNodeId = null;
let ctxTargetId = null;
let activeFilters = new Set(Object.keys(EDGE_COLORS));

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initCytoscape();
  loadDocumentList();
  wireUI();
});

function initCytoscape() {
  cy = cytoscape({
    container: document.getElementById('graph-container'),
    style: [
      {
        selector: 'node',
        style: {
          'label': 'data(label)',
          'background-color': 'data(color)',
          'color': '#0f1117',
          'font-size': '11px',
          'font-weight': '700',
          'text-valign': 'center',
          'text-halign': 'center',
          'text-wrap': 'wrap',
          'text-max-width': '90px',
          'width': 'label',
          'height': 'label',
          'padding': '10px',
          'shape': 'roundrectangle',
          'border-width': 2,
          'border-color': 'data(color)',
          'border-opacity': 0.5,
          'transition-property': 'border-width, border-opacity, opacity',
          'transition-duration': '120ms',
        }
      },
      {
        selector: 'node:selected, node.highlighted',
        style: {
          'border-width': 3,
          'border-opacity': 1,
          'border-color': '#ffffff',
        }
      },
      {
        selector: 'node.dimmed',
        style: { 'opacity': 0.25 }
      },
      {
        selector: 'edge',
        style: {
          'width': 1.5,
          'line-color': 'data(color)',
          'target-arrow-color': 'data(color)',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(label)',
          'font-size': '10px',
          'color': 'data(color)',
          'text-rotation': 'autorotate',
          'text-margin-y': -8,
          'opacity': 0.75,
          'transition-property': 'opacity',
          'transition-duration': '120ms',
        }
      },
      {
        selector: 'edge.dimmed',
        style: { 'opacity': 0.08 }
      },
      {
        selector: 'edge.highlighted',
        style: { 'opacity': 1, 'width': 2.5 }
      },
    ],
    layout: { name: 'cose', animate: false },
  });

  cy.on('tap', 'node', (e) => selectNode(e.target.id()));
  cy.on('tap', (e) => { if (e.target === cy) clearSelection(); });
  cy.on('cxttap', 'node', (e) => showCtxMenu(e, e.target.id()));
}

// ── Document list ─────────────────────────────────────────────────────────
async function loadDocumentList() {
  const docs = await apiFetch('/documents');
  const sel = document.getElementById('doc-select');
  // Keep the placeholder
  sel.innerHTML = '<option value="">— select document —</option>';
  for (const doc of docs) {
    const opt = document.createElement('option');
    opt.value = doc.id;
    opt.textContent = doc.title;
    sel.appendChild(opt);
  }
}

// ── Load graph ────────────────────────────────────────────────────────────
async function loadGraph(docId) {
  const graph = await apiFetch(`/documents/${docId}/graph`);
  currentGraph = graph;
  renderGraph(graph);
}

function renderGraph(graph) {
  cy.elements().remove();

  const elements = [];

  for (const node of graph.nodes) {
    elements.push({
      data: {
        id: node.id,
        label: node.label,
        color: NODE_COLORS[node.type] || '#aaa',
        nodeType: node.type,
      }
    });
  }

  for (const edge of graph.edges) {
    elements.push({
      data: {
        id: edge.id,
        source: edge.source_id,
        target: edge.target_id,
        label: edge.type,
        color: EDGE_COLORS[edge.type] || '#aaa',
        edgeType: edge.type,
      }
    });
  }

  cy.add(elements);
  applyEdgeFilters();

  cy.layout({
    name: 'cose',
    animate: false,
    nodeRepulsion: 8000,
    idealEdgeLength: 120,
    edgeElasticity: 0.45,
    gravity: 0.25,
    numIter: 1000,
  }).run();
}

// ── Edge filter ───────────────────────────────────────────────────────────
function applyEdgeFilters() {
  if (!cy) return;
  cy.edges().forEach(edge => {
    const t = edge.data('edgeType');
    if (activeFilters.has(t)) {
      edge.style('display', 'element');
    } else {
      edge.style('display', 'none');
    }
  });
}

// ── Selection ─────────────────────────────────────────────────────────────
function selectNode(nodeId) {
  if (!currentGraph) return;
  activeNodeId = nodeId;

  const node = currentGraph.nodes.find(n => n.id === nodeId);
  if (!node) return;

  // Highlight neighbourhood
  const connectedEdges = cy.getElementById(nodeId).connectedEdges();
  const connectedNodes = connectedEdges.connectedNodes();
  cy.elements().addClass('dimmed');
  cy.getElementById(nodeId).removeClass('dimmed').addClass('highlighted');
  connectedEdges.removeClass('dimmed').addClass('highlighted');
  connectedNodes.removeClass('dimmed');

  renderSidebar(node);
  hideCtxMenu();
}

function clearSelection() {
  activeNodeId = null;
  cy.elements().removeClass('dimmed highlighted');
  document.getElementById('sidebar-empty').classList.remove('hidden');
  document.getElementById('node-detail').classList.add('hidden');
  hideCtxMenu();
}

// ── Sidebar ───────────────────────────────────────────────────────────────
function renderSidebar(node) {
  document.getElementById('sidebar-empty').classList.add('hidden');
  const detail = document.getElementById('node-detail');
  detail.classList.remove('hidden');

  const badge = document.getElementById('node-type-badge');
  badge.textContent = node.type;
  badge.className = `badge-${node.type}`;

  document.getElementById('node-label').textContent = node.label;
  document.getElementById('node-description').textContent = node.description;

  // Source passages
  const ul = document.getElementById('passages-list');
  ul.innerHTML = '';
  for (const p of node.source_passages.slice(0, 4)) {
    const li = document.createElement('li');
    li.textContent = `"${p}"`;
    ul.appendChild(li);
  }

  // Connected edges
  const edgesUl = document.getElementById('edges-list');
  edgesUl.innerHTML = '';
  if (currentGraph) {
    const connected = currentGraph.edges.filter(
      e => e.source_id === node.id || e.target_id === node.id
    );
    for (const edge of connected) {
      const isSource = edge.source_id === node.id;
      const otherId = isSource ? edge.target_id : edge.source_id;
      const other = currentGraph.nodes.find(n => n.id === otherId);
      if (!other) continue;

      const li = document.createElement('li');
      li.className = 'edge-item';
      li.innerHTML = `
        <span class="edge-type-pill pill-${edge.type}">${edge.type}</span>
        <span class="edge-target">
          ${isSource ? '→' : '←'} ${other.label}
          <small>${edge.description}</small>
        </span>
      `;
      li.addEventListener('click', () => selectNode(otherId));
      edgesUl.appendChild(li);
    }
  }

  // Clear dep results
  document.getElementById('dep-results').classList.add('hidden');
}

// ── Dependency query ──────────────────────────────────────────────────────
async function queryDependencies(nodeId, direction) {
  const data = await apiFetch(`/nodes/${nodeId}/dependencies`, {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId, direction }),
  });

  const results = document.getElementById('dep-results');
  const summary = document.getElementById('dep-summary');
  const list = document.getElementById('dep-list');

  results.classList.remove('hidden');
  const label = direction === 'upstream' ? 'depends on' : 'is depended on by';
  summary.textContent = `"${data.root_node.label}" ${label} ${data.related_nodes.length} node(s):`;

  list.innerHTML = '';
  for (const n of data.related_nodes) {
    const li = document.createElement('li');
    li.textContent = n.label;
    li.addEventListener('click', () => selectNode(n.id));
    list.appendChild(li);
  }
}

// ── Context menu ──────────────────────────────────────────────────────────
function showCtxMenu(e, nodeId) {
  ctxTargetId = nodeId;
  const menu = document.getElementById('ctx-menu');
  menu.style.left = `${e.originalEvent.clientX}px`;
  menu.style.top  = `${e.originalEvent.clientY}px`;
  menu.classList.remove('hidden');
}

function hideCtxMenu() {
  document.getElementById('ctx-menu').classList.add('hidden');
  ctxTargetId = null;
}

// ── Focus neighbourhood ───────────────────────────────────────────────────
function focusNeighbourhood(nodeId) {
  if (!cy) return;
  const node = cy.getElementById(nodeId);
  const neighbourhood = node.closedNeighbourhood();
  cy.elements().addClass('dimmed');
  neighbourhood.removeClass('dimmed');
}

// ── Wire UI ───────────────────────────────────────────────────────────────
function wireUI() {
  // Document select
  document.getElementById('doc-select').addEventListener('change', (e) => {
    if (e.target.value) loadGraph(e.target.value);
  });

  // Edge filters
  document.querySelectorAll('.edge-filter').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) activeFilters.add(cb.value);
      else activeFilters.delete(cb.value);
      applyEdgeFilters();
    });
  });

  // Ingest modal
  document.getElementById('btn-ingest').addEventListener('click', () => {
    document.getElementById('modal-overlay').classList.remove('hidden');
  });
  document.getElementById('btn-cancel').addEventListener('click', () => {
    document.getElementById('modal-overlay').classList.add('hidden');
  });
  document.getElementById('btn-submit').addEventListener('click', submitIngest);

  // Dependency query buttons
  document.querySelectorAll('.dep-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (activeNodeId) queryDependencies(activeNodeId, btn.dataset.dir);
    });
  });
  document.getElementById('dep-close').addEventListener('click', () => {
    document.getElementById('dep-results').classList.add('hidden');
  });

  // Context menu
  document.getElementById('ctx-depends-up').addEventListener('click', () => {
    if (ctxTargetId) { selectNode(ctxTargetId); queryDependencies(ctxTargetId, 'upstream'); }
    hideCtxMenu();
  });
  document.getElementById('ctx-depends-down').addEventListener('click', () => {
    if (ctxTargetId) { selectNode(ctxTargetId); queryDependencies(ctxTargetId, 'downstream'); }
    hideCtxMenu();
  });
  document.getElementById('ctx-focus').addEventListener('click', () => {
    if (ctxTargetId) focusNeighbourhood(ctxTargetId);
    hideCtxMenu();
  });
  document.addEventListener('click', (e) => {
    if (!document.getElementById('ctx-menu').contains(e.target)) hideCtxMenu();
  });
}

// ── Ingest ────────────────────────────────────────────────────────────────
async function submitIngest() {
  const title = document.getElementById('ingest-title').value.trim();
  const text  = document.getElementById('ingest-text').value.trim();
  const status = document.getElementById('modal-status');

  if (!title || !text) { status.textContent = 'Title and text are required.'; return; }

  const btn = document.getElementById('btn-submit');
  btn.disabled = true;
  status.textContent = 'Extracting graph… this may take a minute.';

  try {
    const result = await apiFetch('/documents', {
      method: 'POST',
      body: JSON.stringify({ title, text }),
    });
    status.textContent = `Done: ${result.node_count} nodes, ${result.edge_count} edges.`;
    await loadDocumentList();
    document.getElementById('doc-select').value = result.document_id;
    await loadGraph(result.document_id);
    setTimeout(() => document.getElementById('modal-overlay').classList.add('hidden'), 1200);
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

// ── API helper ────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const res = await fetch(API + path, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}
