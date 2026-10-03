(function () {
  "use strict";

  function legacyCopy(text, button) {
    var field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "readonly");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    var copied = document.execCommand("copy");
    document.body.removeChild(field);
    if (copied) showCopied(button);
  }

  function showCopied(button) {
    var original = button.dataset.originalLabel || button.textContent;
    button.dataset.originalLabel = original;
    button.textContent = "Copied";
    window.setTimeout(function () {
      button.textContent = original;
    }, 1600);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-phone]");
    if (!button) return;

    var phone = button.dataset.copyPhone || "";
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(phone).then(function () {
        showCopied(button);
      }).catch(function () {
        legacyCopy(phone, button);
      });
    } else {
      legacyCopy(phone, button);
    }
  });
})();
