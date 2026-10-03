(function () {
  "use strict";

  function initializeGalleryPreview() {
    var input = document.querySelector('input[name="image"]');
    var preview = document.querySelector("[data-rsa-gallery-preview]");
    if (!input || !preview) return;

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file || !file.type.startsWith("image/")) return;

      var image = preview.querySelector(".rsa-gallery-preview-image");
      if (!image) {
        image = document.createElement("img");
        image.className = "rsa-gallery-preview-image";
        image.alt = "Selected gallery image preview";
        preview.replaceChildren(image);
      }

      if (image.dataset.previewUrl) URL.revokeObjectURL(image.dataset.previewUrl);
      image.dataset.previewUrl = URL.createObjectURL(file);
      image.src = image.dataset.previewUrl;
    });
  }

  document.addEventListener("DOMContentLoaded", initializeGalleryPreview);
})();
