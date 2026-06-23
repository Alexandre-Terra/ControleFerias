/* Controle de Férias — interações do redesenho "Editorial Risk".
   Princípios de resiliência (lições do design): o estado em repouso é SEMPRE o
   final/visível; a animação é um luxo. Se o JS não rodar ou o rAF for limitado
   (aba em segundo plano), o conteúdo final continua à mostra. */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  /* ---- Tema (claro/escuro) + layout (sidebar/topnav) ---------------------- */
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target.closest("[data-toggle-theme]") : null;
    if (t) {
      var cur = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
      var next = cur === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      store("cf_theme", next);
      return;
    }
    var l = e.target.closest ? e.target.closest("[data-set-layout]") : null;
    if (l) {
      var lay = l.getAttribute("data-set-layout");
      root.setAttribute("data-layout", lay);
      store("cf_layout", lay);
    }
  });

  /* ---- Count-up resiliente ------------------------------------------------ */
  function countUp(el) {
    var to = parseInt(el.getAttribute("data-to"), 10);
    if (isNaN(to)) return;
    if (reduce) { el.textContent = to; return; }
    var dur = 850, start = null, done = false;
    var fallback = setTimeout(function () { if (!done) el.textContent = to; }, dur + 500);
    function tick(now) {
      if (start === null) start = now;
      var p = Math.min(1, (now - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(eased * to);
      if (p < 1) { requestAnimationFrame(tick); }
      else { done = true; el.textContent = to; clearTimeout(fallback); }
    }
    requestAnimationFrame(tick);
  }

  /* ---- Donut: anima 0 → final (server já renderizou o estado final) ------- */
  function drawDonut(seg) {
    if (reduce) return;
    var len = parseFloat(seg.getAttribute("data-len"));
    var c = parseFloat(seg.getAttribute("data-c"));
    if (isNaN(len) || isNaN(c)) return;
    seg.style.strokeDasharray = "0 " + c;
    void seg.getBoundingClientRect(); // reflow
    requestAnimationFrame(function () { seg.style.strokeDasharray = len + " " + c; });
  }

  /* ---- Máscara de data brasileira (dd/mm/aaaa) em [data-mask="data"] ----- */
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (!el || !el.matches || !el.matches('[data-mask="data"]')) return;
    var d = el.value.replace(/\D/g, "").slice(0, 8);
    var out = d.slice(0, 2);
    if (d.length > 2) out += "/" + d.slice(2, 4);
    if (d.length > 4) out += "/" + d.slice(4, 8);
    el.value = out;
  });

  /* ---- Toasts de sucesso: somem sozinhos (erros são alerts persistentes) -- */
  function autoDismiss(toast) {
    setTimeout(function () {
      toast.style.transition = "opacity .4s ease, transform .4s ease";
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px)";
      setTimeout(function () { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 420);
    }, 3200);
  }

  function init() {
    var i, els;
    els = document.querySelectorAll(".countup");
    for (i = 0; i < els.length; i++) countUp(els[i]);
    els = document.querySelectorAll(".donut-seg");
    for (i = 0; i < els.length; i++) drawDonut(els[i]);
    els = document.querySelectorAll(".toast");
    for (i = 0; i < els.length; i++) autoDismiss(els[i]);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
