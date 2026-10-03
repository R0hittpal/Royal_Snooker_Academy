(function () {
  "use strict";

  function displayTime(value) {
    var match = /^(\d{1,2}):(\d{2})/.exec(value || "");
    if (!match) return value || "";

    var hour = Number(match[1]);
    var period = hour >= 12 ? "PM" : "AM";
    var displayHour = hour % 12 || 12;
    return displayHour + ":" + match[2] + " " + period;
  }

  function initializeOpeningHoursPreview() {
    var preview = document.querySelector("[data-rsa-hours-preview]");
    if (!preview) return;

    var openingInput = document.querySelector('[name="' + preview.dataset.openField + '"]');
    var closingInput = document.querySelector('[name="' + preview.dataset.closeField + '"]');
    var range = preview.querySelector("[data-hours-range]");
    if (!openingInput || !closingInput || !range) return;

    function update() {
      range.textContent = displayTime(openingInput.value) + " to " + displayTime(closingInput.value);
    }

    openingInput.addEventListener("input", update);
    closingInput.addEventListener("input", update);
    openingInput.addEventListener("change", update);
    closingInput.addEventListener("change", update);
  }

  document.addEventListener("DOMContentLoaded", initializeOpeningHoursPreview);
})();
