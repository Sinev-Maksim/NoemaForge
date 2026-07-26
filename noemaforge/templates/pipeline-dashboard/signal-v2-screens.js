/*
=== NoemaForge File Header ===
File: templates/pipeline-dashboard/signal-v2-screens.js
Zone: gui/shell
Version: 0.33.0
Created: 2026-07-26
Purpose: Signal v2 phase 2 -- Persona roster (7d) and Settings (7c) screens.
  Listens for the "sig:screen-change" event dispatched by signal-v2-shell.js
  and shows/hides #sig-app-main vs. the new #sig-screen-* sections.
Inputs: GET /api/persona/catalog (real endpoint, already used by the classic
  persona-select dropdown); existing DOM elements #locale-select,
  #device-policy, #device-policy-reset, #persona-select, #persona-rules,
  #admin-execute, #admin-prepare-media, #gui-shutdown (all already wired by
  app.js).
Outputs: Persona card grid; a rail avatar stack; a Settings screen built from
  *relocated* (not duplicated) real controls -- moving a DOM node preserves
  its id and any addEventListener bound to it by app.js, so every control
  keeps working exactly as before, just in a new location. No new toggle or
  control is invented here: everything on the Settings screen already existed
  and was already wired before this file ran.
Side effects: none beyond normal fetch + DOM moves; no writes.
Tests: manual -- open Settings, confirm locale/device/persona controls still
  work exactly as in the classic header; open the persona roster, confirm all
  catalog personas render with a working portrait.
=== End NoemaForge File Header ===
*/
(function () {
  "use strict";

  var personaCatalogPromise = null;
  var settingsRelocated = false;

  function fetchPersonaCatalog() {
    if (!personaCatalogPromise) {
      personaCatalogPromise = fetch("/api/persona/catalog")
        .then(function (res) { return res.json(); })
        .then(function (data) { return (data && data.personas) || []; })
        .catch(function () { return []; });
    }
    return personaCatalogPromise;
  }

  function groupLabel(roleKey) {
    // "system.guard/ssr" -> "SYSTEM.GUARD"; falls back to the whole key.
    var slash = roleKey.indexOf("/");
    return (slash > -1 ? roleKey.slice(0, slash) : roleKey).toUpperCase();
  }

  function renderPersonaGrid(personas) {
    var grid = document.getElementById("sig-persona-grid");
    if (!grid) {
      return;
    }
    if (!personas.length) {
      grid.innerHTML = '<p class="muted">No personas returned by /api/persona/catalog.</p>';
      return;
    }
    var frag = document.createDocumentFragment();
    personas.forEach(function (p) {
      var card = document.createElement("div");
      card.className = "sig-persona-card";

      var portrait = document.createElement("div");
      portrait.className = "sig-persona-portrait";
      var img = document.createElement("img");
      img.src = p.portrait_url || "";
      img.alt = (p.codename || p.role_key || "persona") + " portrait";
      // Deliberately eager, not loading="lazy": these are ~20 small SVGs
      // (a few KB each), and native lazy-loading was observed to leave
      // below-the-fold images permanently unloaded in this project's
      // automated browser test harness (no request ever issued, even after
      // scrolling the image fully into view) -- not worth the correctness
      // risk for a negligible perf gain at this asset size/count.
      var label = document.createElement("span");
      label.className = "sig-persona-style-label";
      label.textContent = groupLabel(String(p.role_key || ""));
      portrait.appendChild(img);
      portrait.appendChild(label);

      var body = document.createElement("div");
      body.className = "sig-persona-body";
      var name = document.createElement("p");
      name.className = "sig-persona-name";
      name.textContent = p.codename || p.role_key || "Unnamed";
      var role = document.createElement("p");
      role.className = "sig-persona-role";
      role.textContent = p.description || "";
      body.appendChild(name);
      body.appendChild(role);

      card.appendChild(portrait);
      card.appendChild(body);
      frag.appendChild(card);
    });
    grid.innerHTML = "";
    grid.appendChild(frag);
  }

  function renderRailPersonaStack(personas) {
    var stack = document.getElementById("sig-rail-personas");
    if (!stack || !personas.length) {
      return;
    }
    var shown = personas.slice(0, 5);
    var frag = document.createDocumentFragment();
    shown.forEach(function (p) {
      var img = document.createElement("img");
      img.className = "sig-rail-persona-avatar";
      img.src = p.portrait_url || "";
      img.alt = p.codename || p.role_key || "persona";
      img.title = p.codename || p.role_key || "";
      frag.appendChild(img);
    });
    var count = document.createElement("span");
    count.className = "sig-rail-persona-count";
    count.textContent = String(personas.length);
    frag.appendChild(count);
    stack.innerHTML = "";
    stack.appendChild(frag);
    stack.addEventListener("click", function () {
      document.dispatchEvent(new CustomEvent("sig:screen-change", { detail: { screenId: "sig-screen-personas" } }));
      var screenTitle = document.getElementById("sig-screen-title");
      if (screenTitle) {
        screenTitle.textContent = "Personas";
      }
      var navItems = document.querySelectorAll(".sig-rail-item");
      for (var i = 0; i < navItems.length; i++) {
        navItems[i].classList.remove("active");
      }
    });
  }

  function initPersonaScreen() {
    fetchPersonaCatalog().then(function (personas) {
      renderPersonaGrid(personas);
      renderRailPersonaStack(personas);
    });
  }

  /**
   * Move one existing element (by id) into a new container, wrapping it with
   * its adjacent <label>/text if the original markup paired them, so the
   * relocated control still reads sensibly. Idempotent: if the element is
   * already inside `containerId`, this is a no-op.
   */
  function relocate(elementId, containerId, wrapLabel) {
    var el = document.getElementById(elementId);
    var container = document.getElementById(containerId);
    if (!el || !container || el.parentElement === container) {
      return;
    }
    if (wrapLabel) {
      var wrap = document.createElement("label");
      wrap.className = "sig-relocated-field";
      wrap.appendChild(document.createTextNode(wrapLabel + " "));
      wrap.appendChild(el);
      container.appendChild(wrap);
    } else {
      container.appendChild(el);
    }
  }

  function initSettingsScreen() {
    if (settingsRelocated) {
      return;
    }
    settingsRelocated = true;
    relocate("locale-select", "sig-settings-locale-row", "Locale");
    relocate("persona-select", "sig-settings-persona-row", "Active persona");
    relocate("persona-rules", "sig-settings-persona-row", null);
    relocate("admin-execute", "sig-settings-session-row", null);
    relocate("label-execute", "sig-settings-session-row", null);
    relocate("admin-prepare-media", "sig-settings-session-row", null);
    relocate("label-media-plan", "sig-settings-session-row", null);
    relocate("device-policy", "sig-settings-device-row", "Device");
    relocate("device-policy-reset", "sig-settings-device-row", null);
    relocate("gui-shutdown", "sig-settings-shutdown-row", null);
  }

  function showScreen(screenId) {
    var mainApp = document.getElementById("sig-app-main");
    var screens = document.querySelectorAll(".sig-screen");
    if (!screenId) {
      if (mainApp) {
        mainApp.classList.remove("hidden");
      }
      for (var i = 0; i < screens.length; i++) {
        screens[i].classList.add("hidden");
      }
      return;
    }
    if (mainApp) {
      mainApp.classList.add("hidden");
    }
    for (var j = 0; j < screens.length; j++) {
      screens[j].classList.toggle("hidden", screens[j].id !== screenId);
    }
    if (screenId === "sig-screen-settings") {
      initSettingsScreen();
    } else if (screenId === "sig-screen-personas") {
      initPersonaScreen();
    }
  }

  function init() {
    document.addEventListener("sig:screen-change", function (event) {
      showScreen(event.detail && event.detail.screenId);
    });
    fetchPersonaCatalog().then(renderRailPersonaStack);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
