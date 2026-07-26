/*
=== NoemaForge File Header ===
File: templates/pipeline-dashboard/signal-v2-shell.js
Zone: gui/shell
Version: 0.33.0
Created: 2026-07-26
Purpose: Signal v2 shell behavior -- experience-wave switcher (persisted,
  instant re-theme via CSS custom properties) and nav-rail navigation. For
  rail items backed by real on-page content (data-rail-target) it scroll-
  anchors; for phase-2 screens (data-screen-target, e.g. Settings) it only
  dispatches a "sig:screen-change" DocumentEvent -- signal-v2-screens.js owns
  what showing/hiding a screen actually does, so this file stays ignorant of
  which screens exist. Deliberately separate from app.js: this file only
  touches the new .sig-* shell elements it adds in index.html and never
  reads or writes any existing app.js state, so a Signal v2 phase-1 rollback
  is a two-line <link>/<script> removal with zero risk to chat/pipeline/task
  logic.
Inputs: DOM elements #sig-wave-switch, #sig-rail-nav, #sig-screen-title;
  localStorage key "noemaforge.signal_v2.wave".
Outputs: body[data-wave] attribute; scroll position; "sig:screen-change" event.
Side effects: localStorage write (wave preference only, no runtime data).
Tests: manual -- open the dashboard, click each wave button and rail item.
=== End NoemaForge File Header ===
*/
(function () {
  "use strict";

  var WAVE_STORAGE_KEY = "noemaforge.signal_v2.wave";
  var VALID_WAVES = ["operator", "guided", "play"];

  function applyWave(wave) {
    if (VALID_WAVES.indexOf(wave) === -1) {
      wave = "operator";
    }
    // Set on <html> (:root), not <body>: custom properties inherit their
    // already-*computed* value, not their token text, so a --panel: var(--sig-card)
    // remap declared on :root only re-themes correctly if --sig-card's override
    // also applies at :root -- setting the attribute lower (e.g. <body>) would
    // leave :root's --panel permanently pinned to the operator-wave color.
    document.documentElement.setAttribute("data-wave", wave);
    var buttons = document.querySelectorAll("#sig-wave-switch [data-wave-value]");
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var isSelected = btn.getAttribute("data-wave-value") === wave;
      btn.classList.toggle("active", isSelected);
      btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
    }
    try {
      window.localStorage.setItem(WAVE_STORAGE_KEY, wave);
    } catch (err) {
      /* localStorage unavailable (private mode, etc.) -- wave still applies for this load */
    }
  }

  function initWaveSwitch() {
    var switcher = document.getElementById("sig-wave-switch");
    if (!switcher) {
      return;
    }
    var stored = "operator";
    try {
      stored = window.localStorage.getItem(WAVE_STORAGE_KEY) || "operator";
    } catch (err) {
      /* ignore -- default to operator */
    }
    applyWave(stored);
    switcher.addEventListener("click", function (event) {
      var target = event.target.closest("[data-wave-value]");
      if (!target) {
        return;
      }
      applyWave(target.getAttribute("data-wave-value"));
    });
  }

  function initRailNav() {
    var nav = document.getElementById("sig-rail-nav");
    var screenTitle = document.getElementById("sig-screen-title");
    if (!nav) {
      return;
    }
    nav.addEventListener("click", function (event) {
      var item = event.target.closest(".sig-rail-item");
      if (!item) {
        return;
      }
      if (item.getAttribute("aria-disabled") === "true") {
        return;
      }
      var items = nav.querySelectorAll(".sig-rail-item");
      for (var i = 0; i < items.length; i++) {
        items[i].classList.remove("active");
      }
      item.classList.add("active");
      if (screenTitle) {
        screenTitle.textContent = item.getAttribute("data-rail-label") || screenTitle.textContent;
      }
      var screenId = item.getAttribute("data-screen-target");
      if (screenId) {
        // Phase 2 screens (Settings, Persona roster) live outside #sig-app-main
        // and are shown/hidden rather than scrolled to. signal-v2-screens.js
        // owns what "showing" a screen actually does; this file only notifies
        // it, keeping the two files loosely coupled (shell.js has no idea
        // Settings/Personas exist).
        document.dispatchEvent(new CustomEvent("sig:screen-change", { detail: { screenId: screenId } }));
        return;
      }
      var targetId = item.getAttribute("data-rail-target");
      if (targetId) {
        document.dispatchEvent(new CustomEvent("sig:screen-change", { detail: { screenId: null } }));
        var targetEl = document.getElementById(targetId);
        if (targetEl && typeof targetEl.scrollIntoView === "function") {
          targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  }

  function init() {
    initWaveSwitch();
    initRailNav();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
