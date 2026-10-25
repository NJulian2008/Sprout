/* Small progressive enhancements for onboarding, skill chips and tabs. */
(function () {
  function setSelectValue(form, name, value) {
    var field = form.querySelector('[data-select-value="' + name + '"]');
    if (field) field.value = value;
  }

  function selectedValues(group) {
    return Array.from(group.querySelectorAll('[data-value][aria-pressed="true"]'))
      .map(function (button) { return button.getAttribute("data-value"); });
  }

  function updateSelection(group) {
    var name = group.getAttribute("data-select-group");
    var form = group.closest("form");
    var values = selectedValues(group);
    setSelectValue(form, name, values.join(","));
    var counter = form.querySelector('[data-counter="' + name + '"]');
    if (counter) counter.textContent = String(values.length);
  }

  function validatePanel(form, panel) {
    var valid = true;
    panel.querySelectorAll("[data-select-group]").forEach(function (group) {
      var values = selectedValues(group);
      var min = Number(group.getAttribute("data-min") || 0);
      var max = Number(group.getAttribute("data-max") || 0);
      var invalid = values.length < min || (max > 0 && values.length > max);
      var error = panel.querySelector('[data-select-error="' + group.getAttribute("data-select-group") + '"]');
      if (error) error.hidden = !invalid;
      if (invalid) {
        valid = false;
        var first = group.querySelector("button");
        if (first) first.focus();
      }
    });
    var fields = panel.querySelectorAll('input:not([type="hidden"]), select, textarea');
    for (var i = 0; i < fields.length; i += 1) {
      if (!fields[i].checkValidity()) {
        fields[i].reportValidity();
        valid = false;
        break;
      }
    }
    return valid;
  }

  function initWizards() {
    document.querySelectorAll("form[data-wizard]").forEach(function (form) {
      var panels = Array.from(form.querySelectorAll("[data-step-panel]"));
      var total = Number(form.getAttribute("data-total-steps") || panels.length);
      var current = Number(form.getAttribute("data-initial-step") || 0);
      var count = form.parentElement.querySelector("[data-step-count]");
      var progress = form.parentElement.querySelectorAll("[data-progress]");

      function showStep(index) {
        current = Math.max(0, Math.min(index, total - 1));
        panels.forEach(function (panel, panelIndex) { panel.hidden = panelIndex !== current; });
        progress.forEach(function (segment) {
          segment.classList.toggle("done", Number(segment.getAttribute("data-progress")) <= current);
        });
        if (count) count.textContent = "Step " + (current + 1) + " of " + total;
        var heading = panels[current].querySelector("h2, h1");
        if (heading) {
          heading.setAttribute("tabindex", "-1");
          if (arguments.length > 1 && arguments[1]) heading.focus();
        }
        if (arguments.length > 1 && arguments[1]) {
          window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        }
      }

      form.addEventListener("click", function (event) {
        var option = event.target.closest("[data-select-group] [data-value]");
        if (option) {
          var group = option.closest("[data-select-group]");
          var selected = option.getAttribute("aria-pressed") === "true";
          var values = selectedValues(group);
          var max = Number(group.getAttribute("data-max") || 0);
          if (selected) option.setAttribute("aria-pressed", "false");
          else if (!max || values.length < max) option.setAttribute("aria-pressed", "true");
          updateSelection(group);
          var selectionError = group.parentElement.querySelector('[data-select-error="' + group.getAttribute("data-select-group") + '"]');
          if (selectionError) selectionError.hidden = true;
          return;
        }
        var next = event.target.closest("[data-wizard-next]");
        var back = event.target.closest("[data-wizard-back]");
        if (next) {
          if (validatePanel(form, panels[current])) showStep(current + 1, true);
        } else if (back) {
          showStep(current - 1, true);
        }
      });

      form.addEventListener("submit", function (event) {
        if (current < total - 1) {
          event.preventDefault();
          if (validatePanel(form, panels[current])) showStep(current + 1, true);
          return;
        }
        if (!validatePanel(form, panels[current])) {
          event.preventDefault();
          return;
        }
        var stage = form.querySelector('[name="stage"]');
        var submit = form.querySelector('button[type="submit"]');
        if (stage && stage.value === "review" && submit) {
          submit.classList.add("loading", "reading");
          submit.disabled = true;
          submit.textContent = "Reading your resume…";
        }
      });

      form.querySelectorAll("[data-select-group]").forEach(function (group) {
        var name = group.getAttribute("data-select-group");
        var hidden = form.querySelector('[data-select-value="' + name + '"]');
        var initial = hidden && hidden.value ? hidden.value.split(",") : [];
        group.querySelectorAll("[data-value]").forEach(function (button) {
          button.setAttribute("aria-pressed", initial.indexOf(button.getAttribute("data-value")) >= 0 ? "true" : "false");
        });
        updateSelection(group);
      });
      showStep(current);
    });
  }

  function syncSkills(editor, markReviewed) {
    var scores = {};
    var levels = {};
    editor.querySelectorAll("[data-skill-item]").forEach(function (item) {
      var id = item.getAttribute("data-skill-id");
      if (!id) return;
      scores[id] = Number(item.getAttribute("data-confidence")) / 100;
      levels[id] = item.getAttribute("data-level") || "intermediate";
    });
    var scoresField = editor.querySelector("[data-skill-scores]");
    var levelsField = editor.querySelector("[data-skill-levels]");
    var reviewedField = editor.querySelector("[data-skill-reviewed]");
    if (scoresField) scoresField.value = JSON.stringify(scores);
    if (levelsField) levelsField.value = JSON.stringify(levels);
    if (markReviewed && reviewedField) reviewedField.value = "1";
    var empty = editor.querySelector("[data-empty-skills]");
    var list = editor.querySelector("[data-skill-list]");
    if (empty && list) empty.hidden = list.querySelectorAll("[data-skill-item]").length > 0;
  }

  function showSkillToast(editor, message, removed) {
    var toast = editor.querySelector("[data-skill-toast]");
    if (!toast) return;
    var label = toast.querySelector("[data-toast-message]");
    if (label) label.textContent = message;
    toast.hidden = false;
    editor._sproutRemoved = removed || null;
    window.clearTimeout(editor._sproutToastTimer);
    editor._sproutToastTimer = window.setTimeout(function () { toast.hidden = true; }, 5000);
  }

  function createSkillId(label, input) {
    var datalist = input.list;
    if (datalist) {
      var options = Array.from(datalist.options);
      var exact = options.find(function (option) { return option.value.toLowerCase() === label.toLowerCase(); });
      if (exact && exact.getAttribute("data-skill-id")) return exact.getAttribute("data-skill-id");
    }
    return label.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  }

  function addSkill(editor) {
    var input = editor.querySelector("[data-add-skill]");
    var template = editor.querySelector("[data-skill-template]");
    var list = editor.querySelector("[data-skill-list]");
    if (!input || !template || !list) return;
    var label = input.value.trim();
    if (!label) { input.focus(); return; }
    var id = createSkillId(label, input);
    var existing = Array.from(list.querySelectorAll("[data-skill-item]")).find(function (item) { return item.getAttribute("data-skill-id") === id; });
    if (existing) {
      existing.querySelector("[data-skill-toggle]").focus();
      input.value = "";
      return;
    }
    var item = template.content.firstElementChild.cloneNode(true);
    var editorId = "skill-editor-new-" + Math.random().toString(36).slice(2, 9);
    item.setAttribute("data-skill-id", id);
    item.setAttribute("data-confidence", "100");
    item.setAttribute("data-level", "intermediate");
    item.querySelector("[data-skill-name]").textContent = label;
    item.querySelector("[data-confidence-label]").textContent = "100%";
    item.querySelector("[data-level-label]").textContent = "Intermediate";
    item.querySelector("[data-skill-toggle]").setAttribute("aria-controls", editorId);
    item.querySelector("[data-skill-panel]").id = editorId;
    item.querySelector("[data-remove-skill]").setAttribute("aria-label", "Remove " + label);
    item.querySelector("[data-confidence-slider]").value = "100";
    item.querySelector("[data-confidence-output]").textContent = "100%";
    item.querySelectorAll("[data-set-level]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-set-level") === "intermediate" ? "true" : "false");
    });
    var slider = item.querySelector("[data-confidence-slider]");
    slider.id = editorId + "-confidence";
    item.querySelector(".slider-label").setAttribute("for", slider.id);
    list.appendChild(item);
    input.value = "";
    syncSkills(editor, true);
    item.querySelector("[data-skill-toggle]").focus();
  }

  function initSkillEvents() {
    document.addEventListener("click", function (event) {
      var toggle = event.target.closest("[data-skill-toggle]");
      if (toggle) {
        var item = toggle.closest("[data-skill-item]");
        var panel = item.querySelector("[data-skill-panel]");
        var open = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", open ? "false" : "true");
        panel.hidden = open;
        return;
      }

      var remove = event.target.closest("[data-remove-skill]");
      if (remove) {
        var itemToRemove = remove.closest("[data-skill-item]");
        var editor = remove.closest("[data-skill-editor]");
        var name = itemToRemove.querySelector("[data-skill-name]").textContent;
        var snapshot = { item: itemToRemove.cloneNode(true), next: itemToRemove.nextElementSibling };
        itemToRemove.remove();
        syncSkills(editor, true);
        showSkillToast(editor, "Removed " + name + ".", snapshot);
        return;
      }

      var undo = event.target.closest("[data-undo-remove]");
      if (undo) {
        var editorForUndo = undo.closest("[data-skill-editor]");
        var removed = editorForUndo._sproutRemoved;
        if (removed) {
          var list = editorForUndo.querySelector("[data-skill-list]");
          if (removed.next && removed.next.parentElement === list) list.insertBefore(removed.item, removed.next);
          else list.appendChild(removed.item);
          syncSkills(editorForUndo, true);
          removed.item.querySelector("[data-skill-toggle]").focus();
        }
        var toast = undo.closest("[data-skill-toast]");
        if (toast) toast.hidden = true;
        editorForUndo._sproutRemoved = null;
        return;
      }

      var levelButton = event.target.closest("[data-set-level]");
      if (levelButton) {
        var levelItem = levelButton.closest("[data-skill-item]");
        var level = levelButton.getAttribute("data-set-level");
        levelItem.setAttribute("data-level", level);
        levelItem.querySelector("[data-level-label]").textContent = level.charAt(0).toUpperCase() + level.slice(1);
        levelItem.querySelectorAll("[data-set-level]").forEach(function (button) {
          button.setAttribute("aria-pressed", button === levelButton ? "true" : "false");
        });
        syncSkills(levelButton.closest("[data-skill-editor]"), true);
      }

      var addButton = event.target.closest("[data-add-skill-button]");
      if (addButton) addSkill(addButton.closest("[data-skill-editor]"));
    });

    document.addEventListener("input", function (event) {
      var slider = event.target.closest("[data-confidence-slider]");
      if (!slider) return;
      var item = slider.closest("[data-skill-item]");
      var value = Number(slider.value);
      item.setAttribute("data-confidence", String(value));
      item.querySelector("[data-confidence-label]").textContent = value + "%";
      item.querySelector("[data-confidence-output]").textContent = value + "%";
      syncSkills(slider.closest("[data-skill-editor]"), true);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      var input = event.target.closest("[data-add-skill]");
      if (input) {
        event.preventDefault();
        addSkill(input.closest("[data-skill-editor]"));
      }
    });
  }

  function initDropzones() {
    document.querySelectorAll("[data-dropzone]").forEach(function (dropzone) {
      var input = dropzone.querySelector('input[type="file"]');
      var name = dropzone.querySelector("[data-file-label]");
      var help = dropzone.querySelector("[data-file-help]");
      var error = dropzone.parentElement.querySelector("[data-file-error]");
      if (!input) return;

      function showFile(file) {
        if (!file) return;
        var extension = file.name.split(".").pop().toLowerCase();
        if (["txt", "pdf", "docx"].indexOf(extension) < 0) {
          if (error) { error.textContent = "We couldn’t read that file. Please upload a PDF, DOCX or TXT file."; error.hidden = false; }
          input.setAttribute("aria-invalid", "true");
          input.value = "";
          return;
        }
        dropzone.classList.add("is-selected");
        if (name) name.textContent = file.name;
        if (help) help.textContent = "Selected · tap to change";
        if (error) error.hidden = true;
        input.removeAttribute("aria-invalid");
      }

      input.addEventListener("change", function () { showFile(input.files && input.files[0]); });
      ["dragenter", "dragover"].forEach(function (type) {
        dropzone.addEventListener(type, function (event) { event.preventDefault(); dropzone.classList.add("drag"); });
      });
      ["dragleave", "drop"].forEach(function (type) {
        dropzone.addEventListener(type, function (event) { event.preventDefault(); dropzone.classList.remove("drag"); });
      });
      dropzone.addEventListener("drop", function (event) {
        var file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
        if (!file) return;
        try {
          var transfer = new DataTransfer();
          transfer.items.add(file);
          input.files = transfer.files;
          showFile(file);
        } catch (errorSettingFile) {
          if (error) { error.textContent = "Use the upload button to select your resume."; error.hidden = false; }
        }
      });
    });
  }

  function initResumeExtractField() {
    document.querySelectorAll("[data-resume-text]").forEach(function (textarea) {
      var form = textarea.closest("form");
      var hidden = form && form.querySelector("[data-resume-extract]");
      if (!hidden) return;
      hidden.value = textarea.value;
      textarea.addEventListener("input", function () { hidden.value = textarea.value; });
    });
  }

  function initTabs() {
    document.querySelectorAll('[role="tablist"]').forEach(function (list) {
      var tabs = Array.from(list.querySelectorAll('[role="tab"]'));

      function activate(tab, focus) {
        tabs.forEach(function (item) {
          var selected = item === tab;
          item.classList.toggle("active", selected);
          item.setAttribute("aria-selected", selected ? "true" : "false");
          item.tabIndex = selected ? 0 : -1;
          var panel = document.getElementById(item.getAttribute("aria-controls"));
          if (panel) {
            panel.hidden = !selected;
            panel.classList.toggle("active", selected);
          }
        });
        if (focus) tab.focus();
      }

      list.addEventListener("click", function (event) {
        var tab = event.target.closest('[role="tab"]');
        if (tab) activate(tab, false);
      });
      list.addEventListener("keydown", function (event) {
        var index = tabs.indexOf(event.target.closest('[role="tab"]'));
        if (index < 0) return;
        var next = null;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = tabs.length - 1;
        if (next !== null) { event.preventDefault(); activate(tabs[next], true); }
      });
      var hashTab = tabs.find(function (tab) { return window.location.hash === "#" + tab.getAttribute("data-tab"); });
      if (hashTab) activate(hashTab, false);
    });
  }

  function initExtract() {
    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var button = event.detail.elt && event.detail.elt.closest("[data-extract-button]");
      if (!button) return;
      button.classList.add("loading");
      button.setAttribute("aria-busy", "true");
      var target = document.querySelector(button.getAttribute("hx-target"));
      if (target) {
        button._sproutPrevious = target.innerHTML;
        target.innerHTML = '<div class="skill-loading" role="status" aria-live="polite">Finding your skills…</div>';
      }
    });

    document.body.addEventListener("htmx:afterRequest", function (event) {
      var button = event.detail.elt && event.detail.elt.closest("[data-extract-button]");
      if (!button) return;
      button.classList.remove("loading");
      button.removeAttribute("aria-busy");
      if (event.detail.failed) {
        var target = document.querySelector(button.getAttribute("hx-target"));
        if (target) target.innerHTML = '<p class="field-error" role="alert">We couldn’t find skills right now. You can add them below.</p>' + (button._sproutPrevious || "");
      }
    });
  }

  function initOtherControls() {
    document.addEventListener("click", function (event) {
      var show = event.target.closest("[data-show-schedule]");
      if (show) {
        var panel = document.getElementById(show.getAttribute("aria-controls"));
        var open = show.getAttribute("aria-expanded") === "true";
        show.setAttribute("aria-expanded", open ? "false" : "true");
        if (panel) {
          panel.hidden = open;
          if (!open) {
            var radio = panel.querySelector('input[type="radio"]');
            if (radio) radio.focus();
          }
        }
      }

      if (event.target.closest("[data-history-back]")) {
        if (window.history.length > 1) window.history.back();
        else window.location.href = "/student/signup";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initWizards();
    initSkillEvents();
    initDropzones();
    initResumeExtractField();
    initTabs();
    initExtract();
    initOtherControls();
  });
})();
