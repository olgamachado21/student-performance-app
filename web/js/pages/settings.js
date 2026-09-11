// ============================================================
// Página: Configurações (Temas)
// Duas secções independentes: seleção de tema/fonte visual da app, e
// limiares configuráveis dos alertas automáticos (Ideia 6).
// ============================================================

registerPage("settings", async () => {
  await loadThemesTab();
  loadLanguageTab();
  await loadAlertSettingsTab();
  await loadBackupsTab();
  wireReviewTourButton();
});

// ------------------------------------------------------------
// Idioma: alterna o texto estático da interface (menu lateral, cabeçalhos
// de página, assistente) entre português e inglês europeu — ver
// web/js/i18n.js (getLanguage/setLanguage/applyTranslations). A escolha
// fica guardada em localStorage, tal como o tema de cores; não depende do
// backend, por isso não há chamada à API aqui.
// ------------------------------------------------------------
function loadLanguageTab() {
  const grid = document.getElementById("language-grid");
  if (!grid) return; // secção não presente nesta versão do HTML

  const markSelected = () => {
    const current = getLanguage();
    grid.querySelectorAll("[data-lang-id]").forEach((el) => {
      el.classList.toggle("selected", el.dataset.langId === current);
    });
  };
  markSelected();

  grid.querySelectorAll("[data-lang-id]").forEach((el) => {
    el.addEventListener("click", () => {
      setLanguage(el.dataset.langId); // troca o idioma e reaplica as traduções de imediato
      markSelected();
    });
  });
}

// ------------------------------------------------------------
// Ajuda: botão para reabrir o tour de boas-vindas (ver showOnboarding em
// main.js) sob pedido, mesmo depois de já ter sido visto automaticamente.
// ------------------------------------------------------------
function wireReviewTourButton() {
  const btn = document.getElementById("settings-review-tour-btn");
  if (!btn) return;
  // Evita registar o listener várias vezes se a página for revisitada.
  if (btn.dataset.wired === "true") return;
  btn.dataset.wired = "true";
  btn.addEventListener("click", () => showOnboarding(true));
}

// ------------------------------------------------------------
// Temas
// ------------------------------------------------------------
async function loadThemesTab() {
  // Pede em paralelo a lista de temas/fontes disponíveis e as definições atuais guardadas.
  const [themesData, current] = await Promise.all([Api.themes(), Api.getSettings()]);
  window.APP_THEMES = themesData.themes; // manter sincronizado com a cache usada globalmente em main.js
  renderThemeGrid(themesData.themes, current.theme);
  renderFontSelect(themesData.fonts, current.font);
}

function renderThemeGrid(themes, selectedId) {
  const grid = document.getElementById("theme-grid");
  // Gera um cartão de pré-visualização por tema, com 3 amostras de cor (primária, fundo, cartão).
  grid.innerHTML = themes.map((t) => `
    <div class="theme-option ${t.id === selectedId ? "selected" : ""}" data-theme-id="${t.id}">
      <div class="theme-swatch-row">
        <span class="theme-swatch" style="background:${t.colors["--primary"]};"></span>
        <span class="theme-swatch" style="background:${t.colors["--bg"]};"></span>
        <span class="theme-swatch" style="background:${t.colors["--card-bg"]}; border:1px solid var(--border);"></span>
      </div>
      <div class="theme-option-name">${t.name}</div>
      <div class="theme-option-mode">${t.mode}</div>
    </div>
  `).join("");

  // Ao clicar num cartão de tema: marca-o como selecionado, aplica-o
  // imediatamente (feedback instantâneo) e depois tenta guardar no backend.
  grid.querySelectorAll("[data-theme-id]").forEach((el) => {
    el.addEventListener("click", async () => {
      const themeId = el.dataset.themeId;
      grid.querySelectorAll(".theme-option").forEach((o) => o.classList.remove("selected"));
      el.classList.add("selected");
      applyTheme(themeId); // aplica visualmente já, sem esperar pela resposta da API
      try { await Api.saveSettings({ theme: themeId }); } catch (err) { console.error(err); }
    });
  });
}

function renderFontSelect(fonts, selected) {
  const select = document.getElementById("font-select");
  // Popula o <select> com uma <option> por fonte, marcando a atualmente escolhida.
  select.innerHTML = fonts.map((f) => `<option value="${f}" ${f === selected ? "selected" : ""}>${f}</option>`).join("");
  select.addEventListener("change", async () => {
    applyFont(select.value); // aplica logo visualmente
    try { await Api.saveSettings({ font: select.value }); } catch (err) { console.error(err); }
  });
}

// ------------------------------------------------------------
// Alertas configuráveis (Ideia 6): limiares usados por generate_alerts no
// backend (ver src/alerts.py) — o utilizador pode personalizá-los em vez de
// ficarem fixos no código.
// ------------------------------------------------------------
async function loadAlertSettingsTab() {
  const riskInput = document.getElementById("alert-risk-threshold");
  const absInput = document.getElementById("alert-min-absences");
  if (!riskInput || !absInput) return; // secção não presente nesta versão do HTML

  const current = await Api.getSettings();
  // O limiar de risco é guardado como fração (0-1) no backend, mas mostrado como percentagem.
  riskInput.value = Math.round(current.alert_risk_threshold * 100);
  // "??" trata tanto null como undefined -> mostra campo vazio (cálculo automático).
  absInput.value = current.alert_min_absences ?? "";

  const messageBox = document.getElementById("alert-settings-message");

  document.getElementById("alert-settings-save-btn").addEventListener("click", async () => {
    const riskPct = parseInt(riskInput.value, 10);
    const absValue = absInput.value.trim();
    const payload = {};
    // Só inclui no payload os campos que têm um valor válido/preenchido.
    if (!Number.isNaN(riskPct)) payload.alert_risk_threshold = riskPct / 100;
    if (absValue !== "") payload.alert_min_absences = parseInt(absValue, 10);

    messageBox.classList.remove("hidden");
    try {
      await Api.saveSettings(payload);
      delete AppCache.alerts; // força recálculo dos avisos com os novos limiares
      messageBox.textContent = t("settings_alerts_saved");
      showToast(t("settings_alerts_saved"), { type: "success" });
    } catch (err) {
      console.error(err);
      messageBox.textContent = err.message || t("settings_alerts_save_error");
      showToast(t("settings_alerts_save_error"), { type: "error" });
    }
  });

  document.getElementById("alert-settings-reset-btn").addEventListener("click", async () => {
    // Repõe o campo de faltas mínimas para vazio (= cálculo automático no backend).
    absInput.value = "";
    messageBox.classList.remove("hidden");
    try {
      // -1 é o valor sentinela que o backend interpreta como "repor para automático".
      await Api.saveSettings({ alert_min_absences: -1 });
      delete AppCache.alerts;
      messageBox.textContent = t("settings_alerts_absences_reset");
    } catch (err) {
      console.error(err);
      messageBox.textContent = err.message || t("settings_alerts_reset_error");
    }
  });
}

// ------------------------------------------------------------
// Cópias de segurança (ver src/backup.py + endpoints /backup em
// src/api.py): botão manual "Fazer backup agora" e lista das cópias
// existentes, cada uma com ação de restaurar/apagar. Uma cópia automática
// diária corre sozinha em segundo plano assim que a API está aberta — não
// depende de nada aqui, só se mostra o estado dela para o utilizador saber
// que está ativa.
// ------------------------------------------------------------
async function loadBackupsTab() {
  const table = document.getElementById("backup-table");
  if (!table) return; // secção não presente nesta versão do HTML

  const createBtn = document.getElementById("backup-create-btn");
  const messageBox = document.getElementById("backup-message");
  const autoNote = document.getElementById("backup-auto-note");

  // Evita registar o listener do botão várias vezes se a página for revisitada.
  if (!createBtn.dataset.wired) {
    createBtn.dataset.wired = "true";
    createBtn.addEventListener("click", async () => {
      createBtn.disabled = true;
      messageBox.classList.remove("hidden");
      messageBox.textContent = t("backup_creating");
      try {
        await Api.createBackup();
        messageBox.textContent = t("backup_created");
        showToast(t("backup_created_toast"), { type: "success" });
        await renderBackupList();
      } catch (err) {
        console.error(err);
        messageBox.textContent = err.message || t("backup_create_error");
        showToast(t("backup_create_error"), { type: "error" });
      } finally {
        createBtn.disabled = false;
      }
    });
  }

  try {
    const status = await Api.backupStatus();
    if (!status.sqlite_supported) {
      autoNote.textContent = t("backup_sqlite_unsupported");
      createBtn.disabled = true;
    } else if (status.auto_backup_running) {
      autoNote.textContent = t("backup_auto_active").replace("{h}", Math.round(status.auto_backup_interval_hours));
    } else {
      autoNote.textContent = t("backup_auto_not_started");
    }
  } catch (err) {
    console.error(err);
    autoNote.textContent = t("backup_auto_check_error");
  }

  await renderBackupList();
}

async function renderBackupList() {
  const tbody = document.getElementById("backup-table-body");
  const emptyState = document.getElementById("backup-empty-state");
  const table = document.getElementById("backup-table");
  if (!tbody) return;

  let backups = [];
  try {
    const data = await Api.listBackups();
    backups = data.backups || [];
  } catch (err) {
    console.error(err);
  }

  if (backups.length === 0) {
    table.classList.add("hidden");
    emptyState.classList.remove("hidden");
    return;
  }
  table.classList.remove("hidden");
  emptyState.classList.add("hidden");

  const reasonLabels = { manual: t("backup_reason_manual"), automatico: t("backup_reason_auto"), pre_restauro: t("backup_reason_pre_restore") };

  tbody.innerHTML = backups.map((b) => {
    const date = new Date(b.created_at);
    const dateStr = date.toLocaleString(getLanguage() === "en" ? "en-GB" : "pt-PT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
    const sizeStr = formatBackupSize(b.size_bytes);
    const reasonStr = reasonLabels[b.reason] || b.reason;
    return `
      <tr data-backup-id="${escapeHtml(b.id)}">
        <td>${dateStr}</td>
        <td>${reasonStr}</td>
        <td>${sizeStr}</td>
        <td class="table-actions">
          <button type="button" class="btn-small backup-restore-btn" data-id="${escapeHtml(b.id)}">${escapeHtml(t("backup_restore_btn"))}</button>
          <button type="button" class="btn-small btn-small-danger backup-delete-btn" data-id="${escapeHtml(b.id)}">${escapeHtml(t("backup_delete_btn"))}</button>
        </td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll(".backup-restore-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const ok = await appConfirm(
        t("backup_restore_confirm_msg"),
        { title: t("backup_restore_confirm_title"), confirmLabel: t("backup_restore_btn"), danger: true }
      );
      if (!ok) return;
      try {
        await Api.restoreBackup(id);
        showToast(t("backup_restored_toast"), { type: "success" });
        // Os dados mudaram por completo — força recarregar tudo o que estiver em cache.
        Object.keys(AppCache).forEach((k) => delete AppCache[k]);
        await renderBackupList();
      } catch (err) {
        console.error(err);
        showToast(err.message || t("backup_restore_error"), { type: "error" });
      }
    });
  });

  tbody.querySelectorAll(".backup-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const ok = await appConfirm(t("backup_delete_confirm_msg"), {
        title: t("backup_delete_confirm_title"), confirmLabel: t("backup_delete_btn"), danger: true,
      });
      if (!ok) return;
      try {
        await Api.deleteBackup(id);
        showToast(t("backup_deleted_toast"), { type: "success" });
        await renderBackupList();
      } catch (err) {
        console.error(err);
        showToast(err.message || t("backup_delete_error"), { type: "error" });
      }
    });
  });
}

function formatBackupSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
