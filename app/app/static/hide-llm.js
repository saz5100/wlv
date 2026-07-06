(function(){
  var s = document.createElement("style");
  s.textContent = [
    "header, nav, footer { display: none !important; }",
    ".drag-region, .sticky { display: none !important; }",
    ".sidebar, [class*=sidebar], [class*=side-menu] { display: none !important; }",
    "[data-testid*=sidebar], [data-testid*=header], [data-testid*=nav] { display: none !important; }",
    "[id*=sidebar], [id*=side-menu] { display: none !important; }",
    "[class*=chat-header], [class*=title-bar] { display: none !important; }"
  ].join(" ");
  document.head.appendChild(s);

  setInterval(function() {
    try {
      // Model selector: find by text containing model name
      [].forEach.call(document.querySelectorAll("*"), function(e) {
        if (e.offsetParent === null) return;
        var t = (e.textContent || "").trim();
        if (t.indexOf("GCSE Computer") > -1 ||
            t.indexOf("Select a model") > -1 ||
            t.indexOf("gcse-computer-science") > -1) {
          e.style.display = "none";
          // Hide closest button/div container
          var p = e.closest("[class*=model],button,div[class*=select],div[class*=dropdown]");
          if (p) p.style.display = "none";
        }
      });
      // Also try to find the entire model selector panel area
      [].forEach.call(document.querySelectorAll("[class*=model]"), function(e) {
        if (e.offsetParent !== null) e.style.display = "none";
      });
      [].forEach.call(document.querySelectorAll("[class*=llm], [class*=select]"), function(e) {
        if (e.offsetParent !== null &&
            e.offsetHeight > 0 &&
            (e.textContent || "").toLowerCase().indexOf("model") > -1) {
          e.style.display = "none";
        }
      });
    } catch(e) {}
  }, 300);
})();
