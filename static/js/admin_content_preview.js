(function () {
  "use strict";

  function updatePreviews() {
    document.querySelectorAll("[data-rsa-preview]").forEach(function (preview) {
      var titleInput = document.querySelector('[name="' + preview.dataset.titleField + '"]');
      var textInput = document.querySelector('[name="' + preview.dataset.textField + '"]');
      var title = preview.querySelector("[data-preview-title]");
      var text = preview.querySelector("[data-preview-text]");
      if (titleInput && title) title.textContent = titleInput.value;
      if (textInput && text) text.textContent = textInput.value;
    });
  }

  document.addEventListener("input", updatePreviews);
  document.addEventListener("DOMContentLoaded", updatePreviews);
})();
