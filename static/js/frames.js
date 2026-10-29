// FRAMES scripts (confirm dialogs, matrix filters)
(function () {
  "use strict";

  // Confirm dialogs: any form or link with data-confirm="message"
  document.addEventListener("submit", function (event) {
    const form = event.target;
    const submitter = event.submitter;
    const message = (submitter && submitter.dataset.confirm) || form.dataset.confirm;
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });
  document.addEventListener("click", function (event) {
    const link = event.target.closest("a[data-confirm]");
    if (link && !window.confirm(link.dataset.confirm)) {
      event.preventDefault();
    }
  });

  // Validation form: confirm reject / re-submit and require remarks client-side
  const validationForm = document.getElementById("validation-form");
  if (validationForm) {
    validationForm.addEventListener("submit", function (event) {
      const decision = validationForm.querySelector("input[name='decision']:checked");
      const remarks = validationForm.querySelector("textarea[name='remarks']");
      if (!decision) return;
      if (decision.value !== "APPROVED") {
        if (!remarks.value.trim()) {
          event.preventDefault();
          remarks.classList.add("is-invalid");
          remarks.focus();
          return;
        }
        const label = decision.value === "REJECTED" ? "REJECT" : "request RE-SUBMISSION of";
        if (!window.confirm("Are you sure you want to " + label + " this document?")) {
          event.preventDefault();
        }
      }
    });
  }

  // Upload form: show "required" marker for expiry date when the requirement expires
  const uploadForm = document.getElementById("upload-form");
  if (uploadForm) {
    const select = uploadForm.querySelector("select[name='requirement']");
    const expiryIds = JSON.parse(document.getElementById("expiry-requirement-ids").textContent || "[]");
    const expiryWrap = document.getElementById("expiry-required-note");
    const expiryInput = uploadForm.querySelector("input[name='expiry_date']");
    const sync = function () {
      const needs = expiryIds.includes(parseInt(select.value, 10));
      if (expiryWrap) expiryWrap.classList.toggle("d-none", !needs);
      if (expiryInput) expiryInput.required = needs;
    };
    select.addEventListener("change", function () {
      sync();
      // Reload with ?requirement= so the version history for that requirement is shown
      if (select.value && uploadForm.dataset.historyUrl) {
        const url = new URL(window.location.href);
        if (url.searchParams.get("requirement") !== select.value && !uploadForm.querySelector("input[type='file']").value) {
          url.searchParams.set("requirement", select.value);
          window.location.href = url.toString();
        }
      }
    });
    sync();
    const file = uploadForm.querySelector("input[type='file']");
    if (file) {
      file.addEventListener("change", function () {
        const f = file.files[0];
        const note = document.getElementById("file-note");
        if (!f || !note) return;
        const okType = ["application/pdf", "image/jpeg", "image/png"].includes(f.type);
        const okSize = f.size <= 10 * 1024 * 1024;
        note.textContent = f.name + " · " + (f.size / 1024 / 1024).toFixed(2) + " MB" + (okType ? "" : " · unsupported type") + (okSize ? "" : " · exceeds 10 MB");
        note.className = "form-text " + (okType && okSize ? "text-success" : "text-danger");
      });
    }
  }

  // Matrix: quick text filter on faculty names
  const matrixSearch = document.getElementById("matrix-search");
  if (matrixSearch) {
    matrixSearch.addEventListener("input", function () {
      const term = matrixSearch.value.trim().toLowerCase();
      document.querySelectorAll("#matrix-table tbody tr").forEach(function (row) {
        row.style.display = !term || row.dataset.name.includes(term) ? "" : "none";
      });
    });
  }

  // Bootstrap tooltips
  if (window.bootstrap) {
    document.querySelectorAll("[data-bs-toggle='tooltip']").forEach(function (el) {
      new bootstrap.Tooltip(el);
    });
  }
})();
