/* Host-first moonshot tiles — include after agent.html loads or inline */
(function () {
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c =>
      ({ "&": "&", "<": "<", ">": ">", '"': """, "'": "&#39;" }[c])
    );
  }
  window.renderMoonshots = function (moonshots) {
    const el = document.getElementById("moonshotBoard");
    if (!el) return;
    const tiles = (moonshots && moonshots.tiles) || [];
    if (!tiles.length) {
      el.innerHTML = '<div class="m-card"><div class="label">Moonshots</div><div class="val">—</div><div class="sub">waiting measure_tick</div></div>';
      return;
    }
    el.innerHTML = tiles
      .map(t => {
        let cls = "m-card";
        if (t.good === true) cls += " good";
        else if (t.good === false || t.warn) cls += " bad";
        else if (t.warn) cls += " warn";
        const val = t.value === true ? "OK" : t.value === false ? "NO" : t.value;
        return (
          '<div class="' +
          cls +
          '" id="ms_' +
          esc(t.id) +
          '">' +
          '<div class="label">' +
          esc(t.label) +
          "</div>" +
          '<div class="val">' +
          esc(val) +
          "</div>" +
          '<div class="sub">' +
          esc(t.sub || "") +
          "</div></div>"
        );
      })
      .join("");
  };
})();
