/*
=== NoemaForge File Header ===
File: templates/pipeline-dashboard/signal-v2-pipelines.js
Zone: gui/shell
Version: 0.33.0
Created: 2026-07-27
Purpose: Signal v2 phase 4 -- Pipelines card grid (5a) and the pipeline detail
  pop-up (6a). Renders every pipeline the backend actually publishes, grouped
  by the backend's own group list, and opens a per-pipeline pop-up with the
  real stage diagram and the real run statistics. Follows the phase-2 pattern:
  listens for the "sig:screen-change" DocumentEvent dispatched by
  signal-v2-shell.js and owns only what rendering this one screen means;
  signal-v2-screens.js still owns the generic show/hide of .sig-screen
  sections, so this file never touches #sig-app-main itself.
Inputs: GET /api/pipelines/catalog (id, description, group, stages, team,
  persona_codename, pipeline_scope -- all real catalog fields, nothing
  invented), GET /api/pipelines/<id>/diagram (stages + mermaid source),
  GET /api/pipelines/<id>/stats (runs_total, last_runs; runs_passed,
  runs_failed and avg_duration_sec are currently always null server-side and
  are therefore reported as "not yet tracked" rather than rendered as zeros).
Outputs: #sig-screen-pipelines group filter bar + card grid; the
  #sig-pipeline-modal detail pop-up (description, stage-flow SVG, stats,
  mermaid source).
Side effects: none beyond fetch + DOM writes. The "Run this pipeline" button
  does NOT start anything by itself: it navigates back to the Chat screen and
  delegates to app.js's existing global startPipeline(), i.e. the exact
  classic D-005 confirm flow (editable request inserted into the chat input,
  nothing runs until the operator presses Send). No run logic is duplicated
  here, and if that global is unavailable the button reports it visibly
  instead of failing silently (U-002: no silent no-ops).
Tests: manual -- open Pipelines from the rail, filter by group, open a card
  (mouse and keyboard), confirm the diagram/stats match the endpoint payload
  for that id, close with the button/backdrop/Escape.
=== End NoemaForge File Header ===
*/
(function () {
  "use strict";

  var SCREEN_ID = "sig-screen-pipelines";
  var STAGE_PREVIEW = 4;

  var catalogPromise = null;
  var catalogItems = [];
  var activeGroup = "All";
  var lastFocused = null;
  var modalBound = false;
  var gridBound = false;

  function fetchCatalog() {
    if (!catalogPromise) {
      catalogPromise = fetch("/api/pipelines/catalog")
        .then(function (res) { return res.json(); })
        .then(function (data) {
          return {
            pipelines: (data && data.pipelines) || [],
            groups: (data && data.groups) || []
          };
        })
        .catch(function () { return { pipelines: [], groups: [], failed: true }; });
    }
    return catalogPromise;
  }

  function pipelineById(id) {
    for (var i = 0; i < catalogItems.length; i++) {
      if (catalogItems[i].id === id) {
        return catalogItems[i];
      }
    }
    return null;
  }

  function makeNode(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  /* --- Card grid (5a) --- */

  function renderFilters(groups) {
    var bar = document.getElementById("sig-pipeline-filters");
    if (!bar) {
      return;
    }
    var frag = document.createDocumentFragment();
    ["All"].concat(groups).forEach(function (group) {
      var btn = makeNode("button", "sig-pipeline-filter", group);
      btn.type = "button";
      btn.setAttribute("data-group", group);
      btn.setAttribute("aria-pressed", group === activeGroup ? "true" : "false");
      btn.classList.toggle("active", group === activeGroup);
      frag.appendChild(btn);
    });
    bar.innerHTML = "";
    bar.appendChild(frag);
  }

  function syncFilterState() {
    var buttons = document.querySelectorAll("#sig-pipeline-filters .sig-pipeline-filter");
    for (var i = 0; i < buttons.length; i++) {
      var selected = buttons[i].getAttribute("data-group") === activeGroup;
      buttons[i].classList.toggle("active", selected);
      buttons[i].setAttribute("aria-pressed", selected ? "true" : "false");
    }
  }

  function buildStageStrip(stages) {
    var strip = makeNode("div", "sig-pipeline-stages");
    var shown = stages.slice(0, STAGE_PREVIEW);
    shown.forEach(function (stage) {
      strip.appendChild(makeNode("span", "sig-stage-chip", stage));
    });
    if (stages.length > STAGE_PREVIEW) {
      strip.appendChild(makeNode("span", "sig-stage-chip more", "+" + (stages.length - STAGE_PREVIEW)));
    }
    return strip;
  }

  function buildCard(item) {
    var stages = Array.isArray(item.stages) ? item.stages : [];
    var card = makeNode("article", "sig-pipeline-card");
    card.setAttribute("data-pipeline-id", item.id);
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.setAttribute("aria-label", "Pipeline " + item.id + ", open details");

    var head = makeNode("div", "sig-pipeline-card-head");
    head.appendChild(makeNode("p", "sig-pipeline-id", item.id));
    head.appendChild(makeNode("span", "sig-pipeline-group", item.group || "—"));
    card.appendChild(head);

    var desc = item.description
      ? makeNode("p", "sig-pipeline-desc", item.description)
      : makeNode("p", "sig-pipeline-desc empty", "No description in the catalog entry.");
    card.appendChild(desc);

    card.appendChild(buildStageStrip(stages));

    var meta = makeNode("p", "sig-pipeline-meta");
    meta.appendChild(makeNode("span", "", stages.length + (stages.length === 1 ? " stage" : " stages")));
    if (item.persona_codename) {
      meta.appendChild(makeNode("span", "sig-meta-sep", "·"));
      meta.appendChild(makeNode("span", "", item.persona_codename));
    }
    card.appendChild(meta);

    if (item.pipeline_scope) {
      var scope = makeNode("span", "sig-pipeline-scope", item.pipeline_scope);
      scope.classList.toggle("launchable", item.pipeline_scope === "prod_launchable");
      card.appendChild(scope);
    }
    return card;
  }

  function renderGrid() {
    var grid = document.getElementById("sig-pipeline-grid");
    var countEl = document.getElementById("sig-pipeline-count");
    if (!grid) {
      return;
    }
    if (!catalogItems.length) {
      grid.innerHTML = '<p class="muted">No pipelines returned by /api/pipelines/catalog.</p>';
      if (countEl) {
        countEl.textContent = "";
      }
      return;
    }
    var visible = catalogItems.filter(function (item) {
      return activeGroup === "All" || item.group === activeGroup;
    });
    if (countEl) {
      countEl.textContent = visible.length + " of " + catalogItems.length + " pipelines";
    }
    if (!visible.length) {
      grid.innerHTML = '<p class="muted">No pipelines in this group.</p>';
      return;
    }
    var frag = document.createDocumentFragment();
    visible.forEach(function (item) {
      frag.appendChild(buildCard(item));
    });
    grid.innerHTML = "";
    grid.appendChild(frag);
  }

  function bindGrid() {
    if (gridBound) {
      return;
    }
    var grid = document.getElementById("sig-pipeline-grid");
    var filters = document.getElementById("sig-pipeline-filters");
    if (!grid || !filters) {
      return;
    }
    gridBound = true;

    filters.addEventListener("click", function (event) {
      var btn = event.target.closest(".sig-pipeline-filter");
      if (!btn) {
        return;
      }
      activeGroup = btn.getAttribute("data-group") || "All";
      syncFilterState();
      renderGrid();
    });

    grid.addEventListener("click", function (event) {
      var card = event.target.closest(".sig-pipeline-card");
      if (card) {
        openPipeline(card.getAttribute("data-pipeline-id"), card);
      }
    });
    // Cards are custom clickable elements (not <button>), so Enter/Space have
    // to be handled explicitly to keep them keyboard-operable -- same pattern
    // as the rail persona stack in signal-v2-screens.js.
    grid.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") {
        return;
      }
      var card = event.target.closest(".sig-pipeline-card");
      if (card) {
        event.preventDefault();
        openPipeline(card.getAttribute("data-pipeline-id"), card);
      }
    });
  }

  /* --- Detail pop-up (6a) --- */

  function buildDiagram(stages) {
    var NS = "http://www.w3.org/2000/svg";
    var BOX_H = 42;
    var GAP = 34;
    var MARGIN = 10;
    var HEIGHT = 66;
    var cy = 33;
    var widths = stages.map(function (stage) {
      return Math.max(104, String(stage).length * 7.4 + 24);
    });
    var total = MARGIN * 2;
    widths.forEach(function (w) { total += w; });
    total += GAP * Math.max(stages.length - 1, 0);

    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + Math.round(total) + " " + HEIGHT);
    svg.setAttribute("width", String(Math.round(total)));
    svg.setAttribute("height", String(HEIGHT));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Stage flow: " + stages.join(", then "));

    var defs = document.createElementNS(NS, "defs");
    var marker = document.createElementNS(NS, "marker");
    marker.setAttribute("id", "sig-pipe-arrow");
    marker.setAttribute("markerWidth", "8");
    marker.setAttribute("markerHeight", "8");
    marker.setAttribute("refX", "6");
    marker.setAttribute("refY", "3");
    marker.setAttribute("orient", "auto");
    var head = document.createElementNS(NS, "path");
    head.setAttribute("d", "M0,0 L0,6 L8,3 z");
    head.setAttribute("class", "sig-diagram-arrow");
    marker.appendChild(head);
    defs.appendChild(marker);
    svg.appendChild(defs);

    var x = MARGIN;
    stages.forEach(function (stage, index) {
      var w = widths[index];
      var rect = document.createElementNS(NS, "rect");
      rect.setAttribute("x", String(Math.round(x)));
      rect.setAttribute("y", String(cy - BOX_H / 2));
      rect.setAttribute("width", String(Math.round(w)));
      rect.setAttribute("height", String(BOX_H));
      rect.setAttribute("rx", "10");
      rect.setAttribute("class", "sig-diagram-box");
      svg.appendChild(rect);

      var text = document.createElementNS(NS, "text");
      text.setAttribute("x", String(Math.round(x + w / 2)));
      text.setAttribute("y", String(cy + 4));
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("class", "sig-diagram-label");
      text.textContent = stage;
      svg.appendChild(text);

      if (index < stages.length - 1) {
        var line = document.createElementNS(NS, "line");
        line.setAttribute("x1", String(Math.round(x + w)));
        line.setAttribute("y1", String(cy));
        line.setAttribute("x2", String(Math.round(x + w + GAP - 8)));
        line.setAttribute("y2", String(cy));
        line.setAttribute("class", "sig-diagram-link");
        line.setAttribute("marker-end", "url(#sig-pipe-arrow)");
        svg.appendChild(line);
      }
      x += w + GAP;
    });
    return svg;
  }

  function renderDiagram(data) {
    var host = document.getElementById("sig-pipeline-modal-diagram");
    if (!host) {
      return;
    }
    host.innerHTML = "";
    var stages = (data && Array.isArray(data.stages)) ? data.stages : [];
    if (!stages.length) {
      host.appendChild(makeNode("p", "muted", "No stage diagram returned for this pipeline."));
      return;
    }
    var scroller = makeNode("div", "sig-diagram-scroll");
    scroller.appendChild(buildDiagram(stages));
    host.appendChild(scroller);

    if (data.mermaid) {
      // The backend ships a mermaid source string, but this GUI is
      // offline-first and deliberately bundles no charting library (see
      // CLAUDE.md: no new external runtime deps) -- the flow above is drawn
      // as plain SVG, exactly like the classic dock's diagram modal does.
      // The source is still exposed verbatim, collapsed, for operators who
      // want to paste it elsewhere.
      var details = makeNode("details", "sig-diagram-source");
      details.appendChild(makeNode("summary", "", "Mermaid source (from /diagram)"));
      details.appendChild(makeNode("pre", "", data.mermaid));
      host.appendChild(details);
    }
  }

  function renderStats(data) {
    var host = document.getElementById("sig-pipeline-modal-stats");
    if (!host) {
      return;
    }
    host.innerHTML = "";
    var stats = (data && data.stats) || {};
    var runsTotal = typeof stats.runs_total === "number" ? stats.runs_total : 0;

    var row = makeNode("div", "sig-stat-row");
    var tile = makeNode("div", "sig-stat-tile");
    tile.appendChild(makeNode("span", "sig-stat-value", String(runsTotal)));
    tile.appendChild(makeNode("span", "sig-stat-label", "recorded runs"));
    row.appendChild(tile);
    host.appendChild(row);

    var lastRuns = Array.isArray(stats.last_runs) ? stats.last_runs : [];
    if (lastRuns.length) {
      var list = makeNode("ul", "sig-run-list");
      lastRuns.forEach(function (path) {
        var text = String(path);
        var name = text.split(/[\\/]/).pop() || text;
        var li = makeNode("li", "", name);
        li.title = text;
        list.appendChild(li);
      });
      host.appendChild(makeNode("p", "sig-stat-caption", "Last runs on disk"));
      host.appendChild(list);
    } else {
      host.appendChild(makeNode("p", "sig-stat-caption", "No run directories on disk for this pipeline yet."));
    }

    // runs_passed / runs_failed / avg_duration_sec are null in every current
    // response: the pipeline event store does not record them yet. Reporting
    // the gap honestly beats rendering invented zeros or a fake pass-rate
    // chart (same call as phase 3 made for Tasks/Artifacts).
    var untracked = ["runs_passed", "runs_failed", "avg_duration_sec"].filter(function (key) {
      return stats[key] === null || stats[key] === undefined;
    });
    if (untracked.length) {
      var note = makeNode("p", "sig-stat-untracked");
      note.appendChild(makeNode("strong", "", "Not yet tracked: "));
      note.appendChild(document.createTextNode(untracked.join(", ") + ". "));
      note.appendChild(document.createTextNode(
        stats.note || "These fields are not populated by the backend yet."
      ));
      host.appendChild(note);
    }
  }

  function setRunNotice(message) {
    var notice = document.getElementById("sig-pipeline-modal-notice");
    if (!notice) {
      return;
    }
    notice.textContent = message || "";
    notice.classList.toggle("hidden", !message);
  }

  function goToChatScreen() {
    document.dispatchEvent(new CustomEvent("sig:screen-change", { detail: { screenId: null } }));
    var items = document.querySelectorAll("#sig-rail-nav .sig-rail-item");
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle("active", items[i].getAttribute("data-rail-target") === "chat-log");
    }
    var title = document.getElementById("sig-screen-title");
    if (title) {
      title.textContent = "Chat";
    }
  }

  /**
   * Hand the run off to the classic flow instead of re-implementing it.
   * app.js's startPipeline() opens the existing #pipeline-confirm dialog
   * (D-005: editable request, nothing starts until the operator presses Send
   * in the chat composer). That dialog lives outside #sig-app-main so it is
   * visible from any screen, but the request it stages lands in #admin-message
   * *inside* #sig-app-main -- so return to the Chat screen first, otherwise
   * the staged request would be inserted into a hidden input and the operator
   * would see nothing happen.
   */
  function handOffRun(pipelineId) {
    if (!pipelineId) {
      return;
    }
    if (typeof window.startPipeline !== "function") {
      setRunNotice("The classic pipeline launcher is not available on this page; open the pipeline dock on the Chat screen to start a run.");
      return;
    }
    closeModal();
    goToChatScreen();
    window.startPipeline(pipelineId);
  }

  function closeModal() {
    var modal = document.getElementById("sig-pipeline-modal");
    if (!modal || modal.classList.contains("hidden")) {
      return;
    }
    modal.classList.add("hidden");
    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
    lastFocused = null;
  }

  function bindModal() {
    if (modalBound) {
      return;
    }
    var modal = document.getElementById("sig-pipeline-modal");
    if (!modal) {
      return;
    }
    modalBound = true;

    var closeBtn = document.getElementById("sig-pipeline-modal-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", closeModal);
    }
    var runBtn = document.getElementById("sig-pipeline-modal-run");
    if (runBtn) {
      runBtn.addEventListener("click", function () {
        handOffRun(runBtn.getAttribute("data-pipeline-id"));
      });
    }
    modal.addEventListener("click", function (event) {
      if (event.target === modal) {
        closeModal();
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeModal();
      }
    });
  }

  function openPipeline(pipelineId, sourceCard) {
    var item = pipelineById(pipelineId);
    var modal = document.getElementById("sig-pipeline-modal");
    if (!item || !modal) {
      return;
    }
    bindModal();
    lastFocused = sourceCard || document.activeElement;
    setRunNotice("");

    var title = document.getElementById("sig-pipeline-modal-title");
    if (title) {
      title.textContent = item.id;
    }
    var desc = document.getElementById("sig-pipeline-modal-desc");
    if (desc) {
      desc.textContent = item.description || "No description in the catalog entry.";
    }
    var meta = document.getElementById("sig-pipeline-modal-meta");
    if (meta) {
      meta.innerHTML = "";
      var facts = [
        ["Group", item.group],
        ["Persona", item.persona_codename],
        ["Team", item.team],
        ["Scope", item.pipeline_scope]
      ];
      facts.forEach(function (pair) {
        if (!pair[1]) {
          return;
        }
        var chip = makeNode("span", "sig-modal-fact");
        chip.appendChild(makeNode("span", "sig-modal-fact-key", pair[0]));
        chip.appendChild(makeNode("span", "sig-modal-fact-value", pair[1]));
        meta.appendChild(chip);
      });
    }
    var runBtn = document.getElementById("sig-pipeline-modal-run");
    if (runBtn) {
      runBtn.setAttribute("data-pipeline-id", item.id);
    }

    var diagramHost = document.getElementById("sig-pipeline-modal-diagram");
    var statsHost = document.getElementById("sig-pipeline-modal-stats");
    if (diagramHost) {
      diagramHost.innerHTML = '<p class="muted">Loading stage diagram&hellip;</p>';
    }
    if (statsHost) {
      statsHost.innerHTML = '<p class="muted">Loading stats&hellip;</p>';
    }
    modal.classList.remove("hidden");
    var closeBtn = document.getElementById("sig-pipeline-modal-close");
    if (closeBtn) {
      closeBtn.focus();
    }

    var encoded = encodeURIComponent(item.id);
    fetch("/api/pipelines/" + encoded + "/diagram")
      .then(function (res) { return res.json(); })
      .then(renderDiagram)
      .catch(function () {
        if (diagramHost) {
          diagramHost.innerHTML = '<p class="muted">Stage diagram unavailable (/diagram request failed).</p>';
        }
      });
    fetch("/api/pipelines/" + encoded + "/stats")
      .then(function (res) { return res.json(); })
      .then(renderStats)
      .catch(function () {
        if (statsHost) {
          statsHost.innerHTML = '<p class="muted">Stats unavailable (/stats request failed).</p>';
        }
      });
  }

  function initScreen() {
    fetchCatalog().then(function (data) {
      catalogItems = data.pipelines;
      var grid = document.getElementById("sig-pipeline-grid");
      if (data.failed && grid) {
        grid.innerHTML = '<p class="muted">Pipeline catalog unavailable (/api/pipelines/catalog request failed).</p>';
        return;
      }
      renderFilters(data.groups);
      renderGrid();
      bindGrid();
    });
  }

  function init() {
    document.addEventListener("sig:screen-change", function (event) {
      var screenId = event.detail && event.detail.screenId;
      if (screenId === SCREEN_ID) {
        initScreen();
      } else {
        closeModal();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
