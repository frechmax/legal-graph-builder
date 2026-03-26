const chartEl = document.getElementById("chart");
const dataSelect = document.getElementById("dataSelect");
const detailsBodyEl = document.getElementById("detailsBody");
let fullTreeData = null;
let currentFilterUri = "";

const palette = {
  legalresource: "#0b4f6c",
  teil: "#9a031e",
  abschnitt: "#fb8b24",
  paragraph: "#0f766e",
  absatz: "#4c1d95",
  satz: "#0ea5e9",
  nummer: "#475569",
  unknown: "#64748b",
};

function nodeColor(type) {
  return palette[type] || palette.unknown;
}

function renderDetails(nodeData) {
  if (!nodeData) {
    detailsBodyEl.innerHTML = "";
    return;
  }

  const rows = [
    ["Bezeichnung", nodeData.name || "-"],
    ["Typ", nodeData.type || "-"],
    ["Nummer", nodeData.number || "-"],
    ["Titel", nodeData.title || "-"],
    ["URI", nodeData.uri || "-"],
    ["Beschreibung (eli:description)", nodeData.description || "Keine Beschreibung vorhanden."],
  ];

  detailsBodyEl.innerHTML = rows
    .map(
      ([k, v]) =>
        `<dl class=\"details-item\"><dt>${k}</dt><dd>${String(v)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")}</dd></dl>`
    )
    .join("");
}

function findNodeByUri(tree, uri) {
  if (!tree) {
    return null;
  }
  if (tree.uri === uri) {
    return tree;
  }
  const children = tree.children || tree._children || [];
  for (const child of children) {
    const found = findNodeByUri(child, uri);
    if (found) {
      return found;
    }
  }
  return null;
}

function toggleNodeByUri(tree, uri) {
  if (!tree) {
    return false;
  }

  if (tree.uri === uri) {
    if (tree.children && tree.children.length) {
      tree._children = tree.children;
      tree.children = [];
      return true;
    }
    if (tree._children && tree._children.length) {
      tree.children = tree._children;
      tree._children = [];
      return true;
    }
    return false;
  }

  for (const child of tree.children || []) {
    if (toggleNodeByUri(child, uri)) {
      return true;
    }
  }
  for (const child of tree._children || []) {
    if (toggleNodeByUri(child, uri)) {
      return true;
    }
  }

  return false;
}

function canToggleNode(nodeData) {
  if (!nodeData || nodeData.type === "absatz" || nodeData.type === "satz") {
    return false;
  }
  const visibleChildren = Array.isArray(nodeData.children) ? nodeData.children.length : 0;
  const hiddenChildren = Array.isArray(nodeData._children) ? nodeData._children.length : 0;
  return visibleChildren > 0 || hiddenChildren > 0;
}

function populateDataSelect(treeData) {
  dataSelect.innerHTML = "";

  const allOption = document.createElement("option");
  allOption.value = treeData.uri;
  allOption.textContent = "BauO BE 2005 (Gesamt)";
  dataSelect.append(allOption);

  const teile = (treeData.children || []).filter((child) => child.type === "teil");
  for (const teil of teile) {
    const option = document.createElement("option");
    option.value = teil.uri;
    option.textContent = teil.name;
    dataSelect.append(option);
  }

  dataSelect.value = currentFilterUri || treeData.uri;
}

function getFilteredTreeRoot() {
  if (!fullTreeData) {
    return null;
  }
  return findNodeByUri(fullTreeData, currentFilterUri) || fullTreeData;
}

async function loadTree(dataFile) {
  const response = await fetch(dataFile);
  if (!response.ok) {
    throw new Error(`Cannot load ${dataFile}: ${response.status}`);
  }
  return response.json();
}

function renderTree(data, selectedUri) {
  chartEl.innerHTML = "";

  const root = d3.hierarchy(data);
  const nodeCount = root.descendants().length;
  const radius = Math.max(420, Math.min(920, 230 + nodeCount * 0.85));

  d3.tree().size([2 * Math.PI, radius]).separation((a, b) => (a.parent === b.parent ? 1 : 1.3))(root);

  const margin = 70;
  const diameter = radius * 2 + margin * 2;
  const centerX = diameter * 0.5;
  const centerY = diameter * 0.5;

  const linkRadial = d3
    .linkRadial()
    .angle((d) => d.x)
    .radius((d) => d.y);

  const svg = d3
    .select(chartEl)
    .append("svg")
    .attr("viewBox", [-centerX, -centerY, diameter, diameter])
    .attr("role", "img")
    .attr("aria-label", "Radial tree of legal document hierarchy");

  const g = svg.append("g");

  g.selectAll("path.link")
    .data(root.links())
    .join("path")
    .attr("class", "link")
    .attr("d", linkRadial);

  const node = g
    .selectAll("g.node")
    .data(root.descendants())
    .join("g")
    .attr("transform", (d) => `rotate(${(d.x * 180) / Math.PI - 90}) translate(${d.y},0)`)
    .attr("class", "node");

  node
    .append("circle")
    .attr("class", "node-dot")
    .attr("r", (d) => (d.depth === 0 ? 5 : 3))
    .attr("fill", (d) => nodeColor(d.data.type));

  node
    .append("text")
    .attr("class", (d) => (d.depth === 0 ? "node-label root" : "node-label"))
    .attr(
      "transform",
      (d) => `rotate(${d.x >= Math.PI ? 180 : 0})`
    )
    .attr("dy", "0.31em")
    .attr("x", (d) => (d.x < Math.PI ? 8 : -8))
    .attr("text-anchor", (d) => (d.x < Math.PI ? "start" : "end"))
    .attr("paint-order", "stroke")
    .text((d) => d.data.name)
    .append("title")
    .text((d) => `${d.data.name}\n${d.data.uri}`);

  node
    .style("cursor", "pointer")
    .on("click", (_, d) => {
      const targetUri = d.data.uri;
      if (canToggleNode(d.data)) {
        toggleNodeByUri(data, targetUri);
      }
      const selected = findNodeByUri(data, targetUri);
      renderDetails(selected);
      renderTree(data, targetUri);
    });

  const selectedNode = selectedUri ? findNodeByUri(data, selectedUri) : data;
  renderDetails(selectedNode);
}

function renderCurrentSelection(selectedUri) {
  const filteredRoot = getFilteredTreeRoot();
  if (!filteredRoot) {
    return;
  }

  const selectedInFiltered = selectedUri && findNodeByUri(filteredRoot, selectedUri);
  const effectiveSelectedUri = selectedInFiltered ? selectedUri : filteredRoot.uri;
  renderTree(filteredRoot, effectiveSelectedUri);
}

async function init() {
  try {
    fullTreeData = await loadTree(dataSelect.value);
    currentFilterUri = fullTreeData.uri;
    populateDataSelect(fullTreeData);
    renderCurrentSelection(fullTreeData.uri);
  } catch (err) {
    chartEl.innerHTML = `<p style=\"color:#9a031e\">${err.message}</p>`;
  }

  dataSelect.addEventListener("change", async () => {
    if (!fullTreeData) {
      return;
    }
    currentFilterUri = dataSelect.value;
    renderCurrentSelection(currentFilterUri);
  });
}

init();
