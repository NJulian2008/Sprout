// Availability grid toggle (progressive enhancement, no HTMX required).
// Each .avail-cell has data-slot="Day-Part". Clicking toggles .selected and
// updates a hidden input (name supplied by data-target on the grid container)
// with a comma-separated list of selected slots.
(function () {
  function initGrid(grid) {
    var targetName = grid.getAttribute("data-target") || "availability";
    var hidden = document.querySelector('input[name="' + targetName + '"]');

    function sync() {
      if (!hidden) return;
      var selected = [];
      grid.querySelectorAll(".avail-cell.selected").forEach(function (c) {
        selected.push(c.getAttribute("data-slot"));
      });
      hidden.value = selected.join(",");
    }

    grid.querySelectorAll(".avail-cell").forEach(function (cell) {
      cell.addEventListener("click", function () {
        cell.classList.toggle("selected");
        sync();
      });
    });

    sync();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".avail-grid").forEach(initGrid);
  });
})();
