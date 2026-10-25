/* Weekly availability buttons stay in sync with the form field they submit. */
(function () {
  function fieldFor(grid) {
    var name = grid.getAttribute("data-target") || "availability";
    var form = grid.closest("form");
    return (form || document).querySelector('[name="' + name + '"]');
  }

  function sync(grid) {
    var field = fieldFor(grid);
    if (!field) return;
    var selected = Array.from(grid.querySelectorAll('.time-slot[aria-pressed="true"]'))
      .map(function (button) { return button.getAttribute("data-slot"); });
    field.value = selected.join(",");
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest(".time-slot");
    if (!button) return;
    var grid = button.closest(".availability-grid");
    var pressed = button.getAttribute("aria-pressed") === "true";
    button.setAttribute("aria-pressed", pressed ? "false" : "true");
    sync(grid);
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".availability-grid").forEach(sync);
  });
})();
