/**
 * D3.js Force-Directed Graph für eli:cites Querverweise
 */

const chartEl = document.getElementById("chart");
const filterSelect = document.getElementById("filterParagraph");
const strengthSlider = document.getElementById("layoutStrength");
const resetZoomBtn = document.getElementById("resetZoom");
const detailsBodyEl = document.getElementById("detailsBody");

let fullData = null;
let simulation = null;
let svg = null;
let g = null;
let zoom = null;
let currentFilter = "";

// Farben basierend auf Knotenrolle
const nodeRoleColor = (node, links) => {
    const isSource = links.some(l => l.source.id === node.id || l.source === node.id);
    const isTarget = links.some(l => l.target.id === node.id || l.target === node.id);
    if (isSource && isTarget) return "both";
    if (isSource) return "source";
    if (isTarget) return "target";
    return "source";
};

// Paragraph aus URI extrahieren
const getParagraph = (uri) => {
    const match = uri.match(/par_(\d+[a-z]?)/);
    return match ? `§ ${match[1]}` : null;
};

// Details anzeigen
function renderDetails(node, links) {
    if (!node) {
        detailsBodyEl.innerHTML = "";
        return;
    }

    const outgoing = links.filter(l => (l.source.id || l.source) === node.id);
    const incoming = links.filter(l => (l.target.id || l.target) === node.id);

    const outgoingHtml = outgoing.length > 0
        ? outgoing.map(l => `<li title="${l.label}">${(l.target.label || l.target)}</li>`).join("")
        : "<li><em>Keine</em></li>";

    const incomingHtml = incoming.length > 0
        ? incoming.map(l => `<li title="${l.label}">${(l.source.label || l.source)}</li>`).join("")
        : "<li><em>Keine</em></li>";

    // Beschreibung escapen für HTML
    const escapeHtml = (str) => str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\n/g, "<br>");

    const descriptionHtml = node.description 
        ? `<div class="description-box">${escapeHtml(node.description)}</div>`
        : "<em>Keine Beschreibung vorhanden</em>";

    detailsBodyEl.innerHTML = `
        <dl>
            <dt>URI</dt>
            <dd>${node.id}</dd>
            <dt>Label</dt>
            <dd>${node.label}</dd>
            <dt>Paragraph</dt>
            <dd>${getParagraph(node.id) || "-"}</dd>
        </dl>
        <h4 style="margin-top: 1rem; color: var(--accent-blue);">eli:description</h4>
        ${descriptionHtml}
        <h4 style="margin-top: 1rem; color: var(--accent-orange);">Verweist auf (${outgoing.length})</h4>
        <ul style="font-size: 0.85rem; margin-left: 1rem;">${outgoingHtml}</ul>
        <h4 style="margin-top: 1rem; color: var(--accent-purple);">Wird referenziert von (${incoming.length})</h4>
        <ul style="font-size: 0.85rem; margin-left: 1rem;">${incomingHtml}</ul>
    `;
}

// Statistik aktualisieren
function updateStats(nodes, links, visibleNodes, visibleLinks) {
    document.getElementById("statNodes").textContent = nodes.length;
    document.getElementById("statLinks").textContent = links.length;
    document.getElementById("statVisibleNodes").textContent = visibleNodes;
    document.getElementById("statVisibleLinks").textContent = visibleLinks;
}

// Filter-Optionen befüllen
function populateFilter(data) {
    const paragraphs = new Set();
    data.nodes.forEach(n => {
        const par = getParagraph(n.id);
        if (par) paragraphs.add(par);
    });

    // Nach Nummer sortieren
    const sorted = [...paragraphs].sort((a, b) => {
        const numA = parseInt(a.replace(/\D/g, ""), 10);
        const numB = parseInt(b.replace(/\D/g, ""), 10);
        return numA - numB;
    });

    sorted.forEach(par => {
        const opt = document.createElement("option");
        opt.value = par;
        opt.textContent = par;
        filterSelect.appendChild(opt);
    });
}

// Daten filtern
function filterData(data, filterPar) {
    if (!filterPar) return data;

    // Alle Knoten, die zum gewählten Paragraph gehören
    const relevantNodes = new Set();
    data.nodes.forEach(n => {
        if (getParagraph(n.id) === filterPar) {
            relevantNodes.add(n.id);
        }
    });

    // Links, die von/zu diesen Knoten gehen
    const relevantLinks = data.links.filter(l =>
        relevantNodes.has(l.source) || relevantNodes.has(l.target)
    );

    // Alle Knoten, die an diesen Links beteiligt sind
    const allRelevantNodes = new Set();
    relevantLinks.forEach(l => {
        allRelevantNodes.add(l.source);
        allRelevantNodes.add(l.target);
    });

    return {
        nodes: data.nodes.filter(n => allRelevantNodes.has(n.id)),
        links: relevantLinks
    };
}

// Graph rendern
function renderGraph(data) {
    chartEl.innerHTML = "";
    
    const width = chartEl.clientWidth;
    const height = chartEl.clientHeight || 500;

    // Kopien erstellen für D3
    const nodes = data.nodes.map(d => ({ ...d }));
    const links = data.links.map(d => ({ ...d }));

    updateStats(fullData.nodes, fullData.links, nodes.length, links.length);

    svg = d3.select(chartEl)
        .append("svg")
        .attr("viewBox", [0, 0, width, height]);

    // Pfeilmarker definieren
    svg.append("defs").append("marker")
        .attr("id", "arrowhead")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 20)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("class", "link-arrow");

    svg.append("defs").append("marker")
        .attr("id", "arrowhead-highlighted")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 20)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("class", "link-arrow highlighted");

    g = svg.append("g");

    // Zoom
    zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    // Force Simulation
    simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id(d => d.id).distance(80))
        .force("charge", d3.forceManyBody().strength(parseInt(strengthSlider.value, 10)))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(25));

    // Links zeichnen
    const link = g.append("g")
        .selectAll("line")
        .data(links)
        .join("line")
        .attr("class", "link")
        .attr("marker-end", "url(#arrowhead)");

    // Knoten zeichnen
    const node = g.append("g")
        .selectAll("g")
        .data(nodes)
        .join("g")
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended));

    node.append("circle")
        .attr("r", d => {
            const outCount = links.filter(l => l.source === d || l.source.id === d.id).length;
            const inCount = links.filter(l => l.target === d || l.target.id === d.id).length;
            return 5 + Math.sqrt(outCount + inCount) * 2;
        })
        .attr("class", d => `node-circle ${nodeRoleColor(d, links)}`);

    node.append("text")
        .attr("class", "node-label")
        .attr("dy", -12)
        .text(d => d.label);

    // Interaktion
    node.on("click", (event, d) => {
        // Auswahl markieren
        node.selectAll("circle").classed("selected", false);
        d3.select(event.currentTarget).select("circle").classed("selected", true);

        // Links hervorheben
        link.classed("highlighted", l =>
            l.source.id === d.id || l.target.id === d.id
        ).attr("marker-end", l =>
            (l.source.id === d.id || l.target.id === d.id)
                ? "url(#arrowhead-highlighted)"
                : "url(#arrowhead)"
        );

        renderDetails(d, links);
    });

    // Tick-Funktion
    simulation.on("tick", () => {
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

    function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
    }

    function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
    }

    function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
    }
}

// Daten laden und initialisieren
async function init() {
    try {
        const response = await fetch("../citations.json");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        fullData = await response.json();

        populateFilter(fullData);
        renderGraph(fullData);

    } catch (err) {
        chartEl.innerHTML = `<p style="color: var(--accent-red); padding: 2rem;">${err.message}</p>`;
    }

    // Event Listener
    filterSelect.addEventListener("change", () => {
        currentFilter = filterSelect.value;
        const filtered = filterData(fullData, currentFilter);
        renderGraph(filtered);
    });

    strengthSlider.addEventListener("input", () => {
        if (simulation) {
            simulation.force("charge").strength(parseInt(strengthSlider.value, 10));
            simulation.alpha(0.5).restart();
        }
    });

    resetZoomBtn.addEventListener("click", () => {
        if (svg && zoom) {
            svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
        }
    });

    // Responsive
    window.addEventListener("resize", () => {
        if (fullData) {
            const filtered = filterData(fullData, currentFilter);
            renderGraph(filtered);
        }
    });
}

init();
