// agent-team site: copy buttons, the light/dark switch, the dashboard gallery, the mobile menu.
(function () {
  "use strict";

  // Light / dark: follow the system until the visitor chooses; remember their choice.
  var root = document.documentElement;
  try { var saved = localStorage.getItem("at-theme"); if (saved) root.setAttribute("data-theme", saved); } catch (e) {}
  function currentTheme() {
    var set = root.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function paintToggle() {
    document.querySelectorAll(".theme-toggle").forEach(function (b) {
      var dark = currentTheme() === "dark";
      b.textContent = dark ? "☀" : "☾";
      b.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    });
  }
  document.addEventListener("click", function (ev) {
    var t = ev.target.closest(".theme-toggle");
    if (!t) return;
    var next = currentTheme() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("at-theme", next); } catch (e) {}
    paintToggle();
  });

  document.addEventListener("DOMContentLoaded", function () {
    paintToggle();

    // Copy buttons: on the install line, on .code blocks, and on every code block in the guides.
    document.querySelectorAll(".prose pre").forEach(function (pre) {
      var b = document.createElement("button");
      b.className = "copy"; b.type = "button"; b.textContent = "Copy";
      pre.appendChild(b);
    });
    document.addEventListener("click", function (ev) {
      var b = ev.target.closest(".copy");
      if (!b) return;
      var box = b.closest(".install, .code, pre");
      var source = b.getAttribute("data-copy") || (box && (box.querySelector("code") || box).innerText.replace(/\s*Copy(ied)?\s*$/, ""));
      var text = (source || "").split("\n").filter(function (l) { return l.trim() && !/^\s*#/.test(l); })
        .map(function (l) { return l.replace(/^\$\s*/, "").replace(/\s+#.*$/, ""); }).join("\n");
      if (b.hasAttribute("data-copy")) text = b.getAttribute("data-copy");
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () {
        b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1500);
      }, function () { b.textContent = "Select it"; });
    });

    // Dashboard gallery tabs.
    document.querySelectorAll("[data-gallery]").forEach(function (gallery) {
      var buttons = gallery.querySelectorAll("[data-shot]");
      var images = gallery.querySelectorAll("img[data-name]");
      var caption = gallery.querySelector(".caption");
      var url = gallery.querySelector(".chrome span");
      buttons.forEach(function (btn) {
        btn.addEventListener("click", function () {
          buttons.forEach(function (b) { b.setAttribute("aria-selected", String(b === btn)); });
          images.forEach(function (img) { img.hidden = img.getAttribute("data-name") !== btn.getAttribute("data-shot"); });
          if (caption) caption.textContent = btn.getAttribute("data-caption");
          if (url) url.textContent = "127.0.0.1:8790/#" + btn.getAttribute("data-shot");
        });
      });
    });

    // Mobile menu.
    var menu = document.querySelector(".menu-toggle"), nav = document.querySelector(".site-nav");
    if (menu && nav) menu.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      menu.setAttribute("aria-expanded", String(open));
    });
  });
})();
