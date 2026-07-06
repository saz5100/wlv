try {
(function() {
  "use strict";
  function hideChrome() {
    try {
      [].forEach.call(
        document.querySelectorAll(".navbar,footer,.navbar-spacing"),
        function(e) { e.style.display = "none"; }
      );
      [].forEach.call(document.querySelectorAll("h2"), function(e) {
        if (e.textContent.indexOf("Subfolders") !== -1) e.style.display = "none";
      });
      [].forEach.call(document.querySelectorAll("a,button,span,small"), function(el) {
        var t = (el.textContent || "").trim();
        if (t.indexOf("Created by") !== -1 || t.indexOf("Edit deck") !== -1) {
          el.style.display = "none";
        }
      });
    } catch(e) {}
  }
  // Run immediately
  hideChrome();
  // Run after DOM settle
  setTimeout(hideChrome, 100);
  // Watch for Angular rendering mutations
  var observer = new MutationObserver(function() { hideChrome(); });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  // Stop observing after 5s to avoid perf issues
  setTimeout(function() { observer.disconnect(); }, 5000);
})();
} catch(e) {}
