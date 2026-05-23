const $ = (sel) => document.querySelector(sel);

const MSG = {
  requestFailed: "Ошибка запроса",
  noteDeleted: "Заметка удалена",
  deleteConfirm: (label) =>
    `Удалить заметку ${label}?\n\nБудут удалены текст, изображения и OCR. Это нельзя отменить.`,
  online: "в сети",
  offline: "не в сети",
  noNotes: "Заметок пока нет. Загрузите скриншот на вкладке «Загрузка».",
  loadNotesFailed: (e) => `Не удалось загрузить заметки: ${e}`,
  viewScreenshot: "Открыть скриншот",
  clickToViewScreenshot: "Нажмите, чтобы открыть скриншот",
  searching: "Поиск…",
  noResults: (q) => `Ничего не найдено по запросу «${q}».`,
  noExcerpt: "Совпадение есть, но фрагмент недоступен.",
  score: (s) => `релевантность ${s}`,
  uploading: "Загрузка и распознавание текста…",
  uploadFailed: "Ошибка загрузки",
  uploadComplete: "Загрузка завершена",
  settingsLoadFailed: (e) => `Не удалось загрузить настройки: ${e}`,
  settingsSaved: "Настройки сохранены",
  configCopied: "Конфиг MCP скопирован",
  apiKeySaved: "•••• (сохранён, оставьте пустым, чтобы не менять)",
};

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2800);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderSegments(segments) {
  return segments
    .map((seg) =>
      seg.match
        ? `<mark>${escapeHtml(seg.text)}</mark>`
        : escapeHtml(seg.text)
    )
    .join("");
}

function openImageModal(imageId, caption) {
  const modal = $("#image-modal");
  const img = $("#modal-image");
  $("#modal-caption").textContent = caption || "";
  img.src = `/api/images/${encodeURIComponent(imageId)}`;
  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeImageModal() {
  $("#image-modal").classList.add("hidden");
  $("#modal-image").removeAttribute("src");
  document.body.style.overflow = "";
}

document.querySelectorAll("[data-close-modal]").forEach((el) => {
  el.addEventListener("click", closeImageModal);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeImageModal();
});

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || res.statusText || MSG.requestFailed);
  }
  return data;
}

async function deleteNote(noteId, title) {
  const label = title ? `«${title}»` : noteId;
  if (!confirm(MSG.deleteConfirm(label))) {
    return false;
  }
  await api(`/api/notes/${encodeURIComponent(noteId)}`, { method: "DELETE" });
  toast(MSG.noteDeleted);
  return true;
}

function noteDeleteButton(noteId, title) {
  return `<button type="button" class="btn-delete" data-note-id="${escapeHtml(noteId)}" data-note-title="${escapeHtml(title)}">Удалить</button>`;
}

function bindDeleteButtons(container, onDeleted) {
  container.querySelectorAll(".btn-delete").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        const ok = await deleteNote(btn.dataset.noteId, btn.dataset.noteTitle);
        if (ok && onDeleted) await onDeleted();
      } catch (err) {
        toast(err.message);
      }
    });
  });
}

function renderNoteCardHeader(title, noteId, metaSuffix = "") {
  const metaLine = metaSuffix
    ? `${escapeHtml(noteId)} · ${metaSuffix}`
    : escapeHtml(noteId);
  return `
    <div class="note-card-header">
      <div>
        <h3>${escapeHtml(title)}</h3>
        <p class="meta">${metaLine}</p>
      </div>
      ${noteDeleteButton(noteId, title)}
    </div>`;
}

// Tabs
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#panel-${btn.dataset.tab}`).classList.add("active");
  });
});

// Health
async function checkHealth() {
  const badge = $("#health");
  try {
    await api("/api/health");
    badge.textContent = MSG.online;
    badge.classList.remove("err");
    badge.classList.add("ok");
  } catch {
    badge.textContent = MSG.offline;
    badge.classList.remove("ok");
    badge.classList.add("err");
  }
}

// Notes list
async function loadNotes() {
  const box = $("#notes-list");
  try {
    const data = await api("/api/notes?limit=20");
    if (!data.notes.length) {
      box.innerHTML = `<p class="meta">${MSG.noNotes}</p>`;
      return;
    }
    box.innerHTML = data.notes
      .map(
        (n) => `
      <article class="note-item" data-note-id="${escapeHtml(n.id)}">
        ${renderNoteCardHeader(n.title, n.id, escapeHtml(n.updated_at))}
        ${n.body ? `<p class="note-preview">${escapeHtml(n.body.slice(0, 200))}${n.body.length > 200 ? "…" : ""}</p>` : ""}
      </article>`
      )
      .join("");
    bindDeleteButtons(box, loadNotes);
  } catch (e) {
    box.innerHTML = `<p class="meta">${escapeHtml(MSG.loadNotesFailed(e.message))}</p>`;
  }
}

function renderExcerpt(ex, noteTitle) {
  const imageBtn =
    ex.image_id
      ? `<button type="button" class="view-image-btn" data-image-id="${escapeHtml(ex.image_id)}" data-caption="${escapeHtml(noteTitle)}">${MSG.viewScreenshot}</button>`
      : "";
  const isOcr = ex.image_id && ex.source === "ocr";
  const extraClass = isOcr ? " excerpt-ocr-clickable" : "";
  const dataAttrs = isOcr
    ? ` data-image-id="${escapeHtml(ex.image_id)}" data-caption="${escapeHtml(noteTitle)}" title="${MSG.clickToViewScreenshot}"`
    : "";

  return `
    <div class="excerpt${extraClass}"${dataAttrs}>
      <div class="excerpt-header">
        <span class="excerpt-label">${escapeHtml(ex.label)}</span>
        ${imageBtn}
      </div>
      <p class="excerpt-paragraph">${renderSegments(ex.segments)}</p>
    </div>`;
}

function bindImageButtons(container) {
  container.querySelectorAll(".view-image-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      openImageModal(btn.dataset.imageId, btn.dataset.caption);
    });
  });

  container.querySelectorAll(".excerpt-ocr-clickable").forEach((block) => {
    block.addEventListener("click", (e) => {
      if (e.target.closest(".view-image-btn")) return;
      const id = block.dataset.imageId;
      if (id) openImageModal(id, block.dataset.caption);
    });
  });
}

// Search
$("#search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#search-query").value.trim();
  const box = $("#search-results");
  box.innerHTML = `<p class="meta">${MSG.searching}</p>`;
  try {
    const data = await api(`/api/search?${new URLSearchParams({ q })}`);
    if (!data.hits.length) {
      box.innerHTML = `<p class="meta">${escapeHtml(MSG.noResults(q))}</p>`;
      return;
    }
    box.innerHTML = data.hits
      .map((hit) => {
        const excerpts = (hit.excerpts || [])
          .map((ex) => renderExcerpt(ex, hit.title))
          .join("");

        return `
        <article class="hit" data-note-id="${escapeHtml(hit.note_id)}">
          ${renderNoteCardHeader(hit.title, hit.note_id, MSG.score(hit.score))}
          ${excerpts || `<p class="meta">${MSG.noExcerpt}</p>`}
        </article>`;
      })
      .join("");

    bindImageButtons(box);
    bindDeleteButtons(box, async () => {
      await loadNotes();
      if (q) $("#search-form").requestSubmit();
    });
  } catch (err) {
    box.innerHTML = `<p class="meta">${escapeHtml(err.message)}</p>`;
  }
});

// Upload
$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  const out = $("#upload-result");
  out.classList.remove("hidden");
  out.textContent = MSG.uploading;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || MSG.uploadFailed);
    out.textContent = JSON.stringify(data, null, 2);
    toast(data.upload?.message || MSG.uploadComplete);
    form.reset();
    $("#upload-ocr-lang").value = $("#ocr-lang-setting").value || "rus+eng";
    loadNotes();
  } catch (err) {
    out.textContent = err.message;
    toast(err.message);
  }
});

// Settings
let cursorConfig = {};

async function loadSettings() {
  try {
    const data = await api("/api/settings");
    const s = data.settings;
    cursorConfig = data.cursor_mcp;
    $("#model-provider").value = s.model_provider || "openai";
    $("#model-name").value = s.model_name || "";
    $("#openai-base-url").value = s.openai_base_url || "";
    $("#openai-api-key").value = "";
    $("#openai-api-key").placeholder = s.openai_api_key_set ? MSG.apiKeySaved : "sk-…";
    $("#ocr-lang-setting").value = s.ocr_lang || "rus+eng";
    $("#mcp-public-url").value = s.mcp_public_url || "";
    $("#upload-ocr-lang").value = s.ocr_lang || "rus+eng";
    $("#cursor-config").textContent = JSON.stringify(cursorConfig, null, 2);
  } catch (e) {
    toast(MSG.settingsLoadFailed(e.message));
  }
}

$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    model_provider: $("#model-provider").value,
    model_name: $("#model-name").value,
    openai_base_url: $("#openai-base-url").value,
    ocr_lang: $("#ocr-lang-setting").value,
    mcp_public_url: $("#mcp-public-url").value,
  };
  const key = $("#openai-api-key").value.trim();
  if (key) payload.openai_api_key = key;

  try {
    const data = await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    cursorConfig = data.cursor_mcp;
    $("#cursor-config").textContent = JSON.stringify(cursorConfig, null, 2);
    $("#upload-ocr-lang").value = data.settings.ocr_lang || "rus+eng";
    toast(MSG.settingsSaved);
  } catch (err) {
    toast(err.message);
  }
});

$("#copy-config").addEventListener("click", async () => {
  const text = JSON.stringify(cursorConfig, null, 2);
  await navigator.clipboard.writeText(text);
  toast(MSG.configCopied);
});

checkHealth();
setInterval(checkHealth, 10_000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") checkHealth();
});
loadNotes();
loadSettings();
