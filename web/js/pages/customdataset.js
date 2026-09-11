// ============================================================
// Páginas: Dataset Personalizado (Importar / Estatísticas & Gráficos /
// Previsões / Treinar Modelo / Fórmulas Personalizadas)
// Área independente e GENÉRICA da app: o utilizador carrega QUALQUER
// ficheiro seu (CSV/Excel) — dados de estudantes ou não — e ele é importado
// tal como está, com as colunas originais, sem ter de o adaptar a nenhum
// esquema fixo. A partir daí pode ver estatísticas, escrever fórmulas
// personalizadas e treinar um modelo genérico (escolhendo a própria
// coluna-alvo e colunas-recurso). Previsões continuam a reaproveitar o
// modelo PRINCIPAL da StudentPerfomance, mas só ficam disponíveis quando o dataset
// tem colunas suficientes parecidas com as de estudantes, detetadas
// automaticamente. Nada disto toca no dataset nem nos modelos principais da
// app — ver src/custom_dataset.py no backend.
//
// As 5 sub-páginas partilham o mesmo grupo do menu lateral ("Dataset
// Personalizado", com submenus — ver index.html) e o mesmo estado no
// backend, por isso mudanças numa (importar, apagar, treinar) têm de se
// refletir nas outras da próxima vez que forem visitadas. Como o router da
// app (goToPage em main.js) só corre o loader de cada página uma única vez
// (a primeira visita), as páginas "a jusante" (estatísticas, previsões,
// treinar, fórmulas) voltam a carregar os seus dados sempre que o
// respetivo botão do menu lateral é clicado — não só na primeira vez —
// através dos listeners extra registados no fim deste ficheiro.
// ============================================================

// Formata uma data ISO (ex.: "2026-08-20T15:05:52") para o formato curto local.
function fmtDateTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return isoString;
  return d.toLocaleString(getLanguage() === "en" ? "en-GB" : "pt-PT", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// Navega para a página de importação — usado nos botões "Importar agora" das
// restantes sub-páginas, quando ainda não há nenhum dataset personalizado.
function wireGotoImportButton(buttonId) {
  const btn = document.getElementById(buttonId);
  if (!btn || btn.dataset.wired === "true") return;
  btn.dataset.wired = "true";
  btn.addEventListener("click", () => goToPage("customimport"));
}

// ============================================================
// Página: Importar Dataset
// ============================================================
registerPage("customimport", async () => {
  wireCustomImportForm();
  await refreshCustomImportStatus();
});

function wireCustomImportForm() {
  const uploadBtn = document.getElementById("ci-upload-btn");
  if (uploadBtn.dataset.wired !== "true") {
    uploadBtn.dataset.wired = "true";
    uploadBtn.addEventListener("click", handleCustomImportUpload);
  }
  const confirmBtn = document.getElementById("ci-confirm-btn");
  if (confirmBtn.dataset.wired !== "true") {
    confirmBtn.dataset.wired = "true";
    confirmBtn.addEventListener("click", confirmCustomImport);
  }
}

async function refreshCustomImportStatus() {
  try {
    const status = await Api.customDatasetStatus();
    renderCustomImportStatusCard(status);
  } catch (err) {
    console.error("Não foi possível carregar o estado do dataset personalizado:", err);
  }
  // Se ficou um ficheiro carregado mas ainda por confirmar (ex.: o
  // utilizador mudou de página a meio), retoma-o aqui.
  try {
    const staged = await Api.customDatasetStaged();
    renderCustomImportPending(staged);
  } catch (_) {
    // 404 é o caso normal: nenhum ficheiro em espera.
    document.getElementById("ci-mapping-card").classList.add("hidden");
  }
}

function renderCustomImportStatusCard(status) {
  const card = document.getElementById("ci-status-card");
  if (!status || !status.imported) {
    card.innerHTML = `<p class="form-help-text">${escapeHtml(t("cd_no_dataset"))}</p>`;
    return;
  }
  const columnsList = status.columns.join(", ");
  const detectedCount = Object.keys(status.detected_student_fields || {}).length;
  card.innerHTML = `
    <h3>${escapeHtml(t("cd_active_dataset"))}</h3>
    <p><strong>${escapeHtml(status.filename || t("cd_no_name"))}</strong>${escapeHtml(t("cd_file_summary").replace("{n}", status.n_rows).replace("{m}", status.n_columns).replace("{date}", fmtDateTime(status.imported_at)))}</p>
    <p class="form-help-text">${escapeHtml(t("cd_columns_label").replace("{list}", columnsList))}</p>
    ${
      detectedCount > 0
        ? `<p class="form-help-text">${escapeHtml(t("cd_detected_fields").replace("{n}", detectedCount))}</p>`
        : `<p class="form-help-text">${escapeHtml(t("cd_no_detected_fields"))}</p>`
    }
    <button type="button" class="btn-small btn-small-danger" id="ci-delete-btn">${escapeHtml(t("cd_remove_dataset_btn"))}</button>
  `;
  document.getElementById("ci-delete-btn").addEventListener("click", handleCustomImportDelete);
}

async function handleCustomImportDelete() {
  const ok = await appConfirm(
    t("cd_remove_confirm_msg"),
    { title: t("cd_remove_confirm_title"), confirmLabel: t("cd_remove_confirm_label"), danger: true }
  );
  if (!ok) return;
  try {
    await Api.customDatasetDelete();
    renderCustomImportStatusCard({ imported: false });
    showToast(t("cd_removed_toast"), { type: "info" });
  } catch (err) {
    showToast(err.message, { type: "error" });
  }
}

async function handleCustomImportUpload() {
  const btn = document.getElementById("ci-upload-btn");
  const input = document.getElementById("ci-file-input");
  const msgBox = document.getElementById("ci-upload-message");
  const file = input.files && input.files[0];

  if (!file) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = t("cd_choose_file_first");
    return;
  }

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = t("cd_uploading_btn");
  try {
    const staged = await Api.customDatasetUpload(file);
    msgBox.classList.add("hidden");
    renderCustomImportPending(staged);
  } catch (err) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// Mostra o resumo do ficheiro em espera (colunas + pré-visualização) e o
// botão para confirmar a importação — sem qualquer passo de mapeamento, as
// colunas ficam exatamente como vieram no ficheiro.
function renderCustomImportPending(staged) {
  const card = document.getElementById("ci-mapping-card");
  card.classList.remove("hidden");
  document.getElementById("ci-mapping-help").textContent = t("cd_pending_file_summary")
    .replace("{filename}", staged.filename)
    .replace("{n}", staged.n_rows)
    .replace("{m}", staged.columns.length)
    .replace("{cols}", staged.columns.join(", "));

  renderCustomImportPreview(staged);
  document.getElementById("ci-import-message").classList.add("hidden");
}

function renderCustomImportPreview(staged) {
  const wrap = document.getElementById("ci-preview-wrap");
  if (!staged.preview || !staged.preview.length) {
    wrap.innerHTML = "";
    return;
  }
  const cols = staged.columns;
  wrap.innerHTML = `
    <table>
      <thead><tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>
      <tbody>
        ${staged.preview
          .map((row) => `<tr>${cols.map((c) => `<td>${escapeHtml(row[c] ?? "")}</td>`).join("")}</tr>`)
          .join("")}
      </tbody>
    </table>
  `;
}

async function confirmCustomImport() {
  const btn = document.getElementById("ci-confirm-btn");
  const msgBox = document.getElementById("ci-import-message");

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = t("cd_importing_btn");
  try {
    const status = await Api.customDatasetImport();
    msgBox.classList.add("hidden");
    document.getElementById("ci-mapping-card").classList.add("hidden");
    document.getElementById("ci-file-input").value = "";
    renderCustomImportStatusCard(status);
    showToast(t("cd_imported_toast").replace("{n}", status.n_rows), { type: "success" });
  } catch (err) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// ============================================================
// Página: Estatísticas & Gráficos
// ============================================================
registerPage("customstats", async () => {
  await loadCustomStatsPage();
});

let csGradeChart = null;
let csPassFailChart = null;

async function loadCustomStatsPage() {
  const empty = document.getElementById("cs-empty-state");
  const content = document.getElementById("cs-content");
  let status;
  try {
    status = await Api.customDatasetStatus();
  } catch (err) {
    console.error(err);
    return;
  }

  if (!status.imported) {
    empty.classList.remove("hidden");
    content.classList.add("hidden");
    wireGotoImportButton("cs-goto-import");
    return;
  }
  empty.classList.add("hidden");
  content.classList.remove("hidden");

  try {
    const stats = await Api.customDatasetStats();
    renderCustomStatsKpis(stats);
    renderCustomStatsCharts(stats);
    renderCustomStatsColumnsTable(stats);
  } catch (err) {
    console.error("Não foi possível carregar as estatísticas do dataset personalizado:", err);
  }
}

function renderCustomStatsKpis(stats) {
  const items = [
    { label: t("cd_kpi_rows"), value: stats.n_rows },
    { label: t("cd_kpi_columns"), value: stats.n_columns },
  ];
  if (stats.average_grade !== undefined && stats.average_grade !== null) {
    items.push({ label: t("cd_kpi_avg_grade"), value: `${fmtNum(stats.average_grade)} / 20` });
  }
  if (stats.pass_rate !== undefined && stats.pass_rate !== null) {
    items.push({ label: t("cd_kpi_pass_rate"), value: fmtPct(stats.pass_rate) });
  }
  renderKpiCards("cs-kpis", items);
}

function renderCustomStatsCharts(stats) {
  const grid = document.getElementById("cs-chart-grid");
  if (!stats.grade_distribution) {
    // Sem uma coluna de nota final detetada não há dados para desenhar —
    // a secção de gráficos não faz sentido para este dataset.
    grid.classList.add("hidden");
    return;
  }
  grid.classList.remove("hidden");
  if (csGradeChart) csGradeChart.destroy();
  if (csPassFailChart) csPassFailChart.destroy();

  csGradeChart = new Chart(document.getElementById("cs-chart-grade-distribution"), {
    type: "bar",
    data: {
      labels: stats.grade_distribution.labels,
      datasets: [{
        label: t("cd_chart_rows_count_label"),
        data: stats.grade_distribution.counts,
        backgroundColor: COLORS.primary,
        borderRadius: 4,
        maxBarThickness: 22,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxRotation: 90, minRotation: 90, font: { size: 9 } }, grid: { display: false } },
        y: { beginAtZero: true, grid: { color: COLORS.border } },
      },
    },
  });

  if (stats.pass_fail_counts) {
    csPassFailChart = new Chart(document.getElementById("cs-chart-pass-fail"), {
      type: "doughnut",
      data: {
        labels: [t("cd_chart_passed"), t("cd_chart_failed")],
        datasets: [{
          data: [stats.pass_fail_counts.aprovados, stats.pass_fail_counts.reprovados],
          backgroundColor: [COLORS.positive, COLORS.negative],
          borderWidth: 0,
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, cutout: "65%", plugins: { legend: { position: "bottom" } } },
    });
  }
}

function renderCustomStatsColumnsTable(stats) {
  const tbody = document.querySelector("#cs-columns-table tbody");
  const rows = Object.entries(stats.columns).map(([col, info]) => {
    let summary;
    if (info.type === "numeric") {
      summary = t("cd_col_summary_numeric")
        .replace("{mean}", fmtNum(info.mean)).replace("{median}", fmtNum(info.median))
        .replace("{std}", fmtNum(info.std)).replace("{min}", fmtNum(info.min)).replace("{max}", fmtNum(info.max));
    } else {
      summary = Object.entries(info.counts)
        .map(([cat, count]) => `${escapeHtml(cat)}: ${count}`)
        .join(" · ");
      if (info.n_distinct > Object.keys(info.counts).length) {
        summary += t("cd_col_summary_more_categories").replace("{n}", info.n_distinct - Object.keys(info.counts).length);
      }
    }
    return `
      <tr>
        <td>${escapeHtml(col)}</td>
        <td>${info.type === "numeric" ? escapeHtml(t("cd_col_type_numeric")) : escapeHtml(t("cd_col_type_categorical"))}</td>
        <td>${summary}</td>
      </tr>
    `;
  });
  tbody.innerHTML = rows.join("") || `<tr><td colspan="3">${escapeHtml(t("cd_no_columns"))}</td></tr>`;
}

// ============================================================
// Página: Previsões
// ============================================================
registerPage("custompredict", async () => {
  await loadCustomPredictPage(1);
});

const cpState = { page: 1, page_size: 15 };

async function loadCustomPredictPage(page) {
  const empty = document.getElementById("cp-empty-state");
  const content = document.getElementById("cp-content");
  let status;
  try {
    status = await Api.customDatasetStatus();
  } catch (err) {
    console.error(err);
    return;
  }

  if (!status.imported || !status.can_predict) {
    empty.classList.remove("hidden");
    content.classList.add("hidden");
    wireGotoImportButton("cp-goto-import");
    return;
  }
  empty.classList.add("hidden");
  content.classList.remove("hidden");
  cpState.page = page;

  try {
    const data = await Api.customDatasetPredict(cpState.page, cpState.page_size);
    renderCustomPredictTable(data);
    renderCustomPredictPagination(data);
  } catch (err) {
    console.error("Não foi possível carregar as previsões do dataset personalizado:", err);
  }
}

function renderCustomPredictTable(data) {
  const tbody = document.querySelector("#cp-table tbody");
  const rows = data.predictions.map((p) => `
    <tr>
      <td>${p.row_id}</td>
      <td>${fmtNum(p.predicted_grade)}</td>
      <td>${fmtPct(p.pass_probability)}</td>
      <td>${p.aprovado_previsto ? `<span class="pill pill-yes">${escapeHtml(t("cat_yes"))}</span>` : `<span class="pill pill-no">${escapeHtml(t("cat_no"))}</span>`}</td>
      <td>${p.actual_grade !== undefined ? fmtNum(p.actual_grade) : "—"}</td>
    </tr>
  `).join("");
  tbody.innerHTML = rows || `<tr><td colspan="5">${escapeHtml(t("cd_no_rows"))}</td></tr>`;
}

function renderCustomPredictPagination(data) {
  const container = document.getElementById("cp-pagination");
  const { page, total_pages, total } = data;
  container.innerHTML = `
    <button id="cp-page-prev" ${page <= 1 ? "disabled" : ""}>${escapeHtml(t("data_pagination_prev"))}</button>
    <span class="pagination-info">${escapeHtml(t("cd_pagination_rows_info").replace("{page}", page).replace("{total_pages}", total_pages).replace("{total}", total))}</span>
    <button id="cp-page-next" ${page >= total_pages ? "disabled" : ""}>${escapeHtml(t("data_pagination_next"))}</button>
  `;
  document.getElementById("cp-page-prev")?.addEventListener("click", () => loadCustomPredictPage(Math.max(1, page - 1)));
  document.getElementById("cp-page-next")?.addEventListener("click", () => loadCustomPredictPage(Math.min(total_pages, page + 1)));
}

// ============================================================
// Página: Treinar Modelo
// ============================================================
// Genérico: o utilizador escolhe a coluna-alvo (o que quer prever) e as
// colunas-recurso (o que usar para prever) — funciona com qualquer dataset,
// não só dados de estudantes. Regressão ou classificação é decidido
// automaticamente pelo backend, consoante o tipo real da coluna-alvo.
registerPage("customtrain", async () => {
  wireCustomTrainForm();
  await loadCustomTrainPage();
});

function wireCustomTrainForm() {
  const btn = document.getElementById("ct-train-btn");
  if (btn.dataset.wired !== "true") {
    btn.dataset.wired = "true";
    btn.addEventListener("click", runCustomTrain);
  }
  const targetSelect = document.getElementById("ct-target-select");
  if (targetSelect.dataset.wired !== "true") {
    targetSelect.dataset.wired = "true";
    targetSelect.addEventListener("change", refreshCustomTrainFeatureChoices);
  }
}

async function loadCustomTrainPage() {
  const empty = document.getElementById("ct-empty-state");
  const content = document.getElementById("ct-content");
  let status;
  try {
    status = await Api.customDatasetStatus();
  } catch (err) {
    console.error(err);
    return;
  }

  if (!status.imported) {
    empty.classList.remove("hidden");
    empty.innerHTML = `${escapeHtml(t("cd_no_dataset_with_import"))} <button type="button" class="link-button" id="ct-goto-import">${escapeHtml(t("cd_import_now_btn"))}</button>`;
    content.classList.add("hidden");
    wireGotoImportButton("ct-goto-import");
    return;
  }
  if (!status.can_train) {
    empty.classList.remove("hidden");
    empty.textContent = t("cd_train_min_rows").replace("{min}", status.min_rows_for_train).replace("{n}", status.n_rows).replace("{m}", status.n_columns);
    content.classList.add("hidden");
    return;
  }
  empty.classList.add("hidden");
  content.classList.remove("hidden");

  renderCustomTrainColumnPickers(status.columns);
  document.getElementById("ct-train-message").classList.add("hidden");

  try {
    const metrics = await Api.customDatasetTrainMetrics();
    renderCustomTrainResults(metrics);
  } catch (_) {
    // 404: ainda não foi treinado nenhum modelo para este dataset -> nada a mostrar ainda.
    document.getElementById("ct-results").innerHTML = "";
  }
}

// Preenche o seletor de coluna-alvo com todas as colunas do dataset
// (excluindo "row_id", que é só o identificador interno de cada linha) e
// desenha as checkboxes de colunas-recurso para a escolha inicial.
function renderCustomTrainColumnPickers(columns) {
  const usableColumns = columns.filter((c) => c !== "row_id");
  const targetSelect = document.getElementById("ct-target-select");
  const previousTarget = targetSelect.value;
  targetSelect.innerHTML = usableColumns.map((c) => `<option value="${escapeAttr(c)}">${escapeHtml(c)}</option>`).join("");
  if (usableColumns.includes(previousTarget)) targetSelect.value = previousTarget;
  refreshCustomTrainFeatureChoices();
}

// As colunas-recurso disponíveis são todas exceto a que está escolhida como
// alvo (não faz sentido usar a própria coluna a prever como recurso) — os
// checkboxes já marcados são preservados sempre que possível.
function refreshCustomTrainFeatureChoices() {
  const targetSelect = document.getElementById("ct-target-select");
  const target = targetSelect.value;
  const wrap = document.getElementById("ct-feature-checkboxes");
  const previouslyChecked = new Set(
    Array.from(wrap.querySelectorAll("input[type=checkbox]:checked")).map((el) => el.value)
  );

  const usableColumns = Array.from(targetSelect.options)
    .map((opt) => opt.value)
    .filter((c) => c !== target);

  wrap.innerHTML = usableColumns
    .map((c) => {
      const checked = previouslyChecked.size === 0 || previouslyChecked.has(c);
      return `
        <label class="checkbox-chip">
          <input type="checkbox" value="${escapeAttr(c)}" ${checked ? "checked" : ""}>
          ${escapeHtml(c)}
        </label>
      `;
    })
    .join("") || `<p class="form-help-text">${escapeHtml(t("cd_no_more_feature_columns"))}</p>`;
}

async function runCustomTrain() {
  const btn = document.getElementById("ct-train-btn");
  const msgBox = document.getElementById("ct-train-message");
  const targetCol = document.getElementById("ct-target-select").value;
  const featureCols = Array.from(
    document.querySelectorAll("#ct-feature-checkboxes input[type=checkbox]:checked")
  ).map((el) => el.value);

  if (!targetCol) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = t("cd_choose_target_column");
    return;
  }
  if (featureCols.length === 0) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = t("cd_choose_feature_column");
    return;
  }

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = t("cd_training_btn");
  try {
    const metrics = await Api.customDatasetTrain(targetCol, featureCols);
    msgBox.classList.add("hidden");
    renderCustomTrainResults(metrics);
    showToast(t("cd_trained_toast"), { type: "success" });
  } catch (err) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function renderCustomMetricsTable(results, bestModel) {
  const metricNames = Object.keys(Object.values(results)[0] || {});
  const rows = Object.entries(results).map(([name, metrics]) => `
    <tr class="${name === bestModel ? "scenario-best-col" : ""}">
      <td>${escapeHtml(name)}${name === bestModel ? " ★" : ""}</td>
      ${metricNames.map((k) => `<td>${typeof metrics[k] === "number" ? metrics[k].toFixed(3) : (metrics[k] ?? "—")}</td>`).join("")}
    </tr>
  `).join("");
  return `
    <table>
      <thead><tr><th>${escapeHtml(t("cd_model_header"))}</th>${metricNames.map((k) => `<th>${escapeHtml(k)}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderCustomTrainResults(metrics) {
  const container = document.getElementById("ct-results");
  const featureLabels = metrics.feature_cols.join(", ");
  const isRegression = metrics.task === "regression";
  const taskLabel = isRegression
    ? t("cd_task_regression").replace("{target}", metrics.target)
    : t("cd_task_classification").replace("{target}", metrics.target);
  const results = isRegression ? metrics.regression : metrics.classification;
  container.innerHTML = `
    <div class="card">
      <h3>${escapeHtml(taskLabel)}</h3>
      <p class="form-help-text">${escapeHtml(t("cd_features_used").replace("{list}", featureLabels).replace("{n}", metrics.n_rows))}</p>
      <div class="table-wrap">${renderCustomMetricsTable(results.results, results.best_model)}</div>
    </div>
  `;
}

// ============================================================
// Página: Fórmulas Personalizadas
// ============================================================
// O utilizador escreve a sua própria fórmula (ex.: "G1*0.3 + G2*0.3 +
// G3*0.4" ou "media(G3) onde studytime >= 3") sobre o dataset personalizado
// — avaliada em segurança no backend (ver src/formula_engine.py: nunca
// corre eval()/exec() sobre o texto do utilizador). O resultado tanto pode
// ser uma coluna nova (um valor por linha, paginada tal como as Previsões)
// como um único resultado (uma média, soma, etc.), consoante a fórmula
// escrita — ver evaluate() no backend para a deteção automática.
registerPage("customformula", async () => {
  wireCustomFormulaForm();
  await loadCustomFormulaPage();
});

// Só guarda a página atual (a fórmula em si já vive no próprio campo de
// texto — voltar a lê-lo é mais simples do que manter os dois em sincronia).
const cfState = { page: 1, page_size: 20 };

function wireCustomFormulaForm() {
  const btn = document.getElementById("cf-calculate-btn");
  if (btn.dataset.wired !== "true") {
    btn.dataset.wired = "true";
    btn.addEventListener("click", () => runCustomFormula(1));
  }
  const input = document.getElementById("cf-formula-input");
  if (input.dataset.wired !== "true") {
    input.dataset.wired = "true";
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        runCustomFormula(1);
      }
    });
  }
}

async function loadCustomFormulaPage() {
  const empty = document.getElementById("cf-empty-state");
  const content = document.getElementById("cf-content");
  let status;
  try {
    status = await Api.customDatasetStatus();
  } catch (err) {
    console.error(err);
    return;
  }

  if (!status.imported) {
    empty.classList.remove("hidden");
    content.classList.add("hidden");
    wireGotoImportButton("cf-goto-import");
    return;
  }
  empty.classList.add("hidden");
  content.classList.remove("hidden");
  renderCustomFormulaColumnChips(status.columns);
}

// Lista de "chips" clicáveis com as colunas do dataset (tal como vêm do
// ficheiro) — poupa o utilizador de ter de voltar a escrever os nomes.
// Colunas com espaços no nome não são identificadores Python válidos e por
// isso não podem ser usadas diretamente numa fórmula — ficam visíveis mas
// marcadas, para o utilizador perceber a limitação em vez de descobrir só
// depois de calcular.
function renderCustomFormulaColumnChips(columns) {
  const wrap = document.getElementById("cf-column-chips");
  const usableColumns = (columns || []).filter((c) => c !== "row_id");
  wrap.innerHTML =
    usableColumns
      .map((c) => {
        const hasSpaces = /\s/.test(c);
        const title = hasSpaces
          ? ` title="${escapeAttr(t("cd_column_spaces_title"))}"`
          : "";
        return `<button type="button" class="cluster-student-chip" data-field="${escapeAttr(c)}" ${hasSpaces ? "disabled" : ""}${title}>${escapeHtml(c)}${hasSpaces ? " ⚠" : ""}</button>`;
      })
      .join("") || `<p class="form-help-text">${escapeHtml(t("cd_no_columns_available"))}</p>`;
  wrap.querySelectorAll(".cluster-student-chip:not([disabled])").forEach((chip) => {
    chip.addEventListener("click", () => insertFieldIntoFormula(chip.dataset.field));
  });
}

// Insere o nome técnico da coluna na posição atual do cursor no campo de
// fórmula (em vez de simplesmente acrescentar ao fim), para o utilizador
// poder construir a fórmula clicando em várias colunas sem ter de reescrever
// nada — cuidando de nunca colar duas palavras sem espaço entre elas.
function insertFieldIntoFormula(fieldName) {
  const input = document.getElementById("cf-formula-input");
  const start = input.selectionStart ?? input.value.length;
  const end = input.selectionEnd ?? input.value.length;
  const before = input.value.slice(0, start);
  const after = input.value.slice(end);
  const needsSpaceBefore = before.length > 0 && !/\s$/.test(before);
  const insertion = (needsSpaceBefore ? " " : "") + fieldName;
  input.value = before + insertion + after;
  const cursorPos = (before + insertion).length;
  input.focus();
  input.setSelectionRange(cursorPos, cursorPos);
}

async function runCustomFormula(page) {
  const input = document.getElementById("cf-formula-input");
  const btn = document.getElementById("cf-calculate-btn");
  const msgBox = document.getElementById("cf-error-message");
  const formula = input.value.trim();
  if (!formula) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = t("cd_write_formula_first");
    return;
  }
  cfState.page = page;

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = t("cd_calculating_btn");
  try {
    const data = await Api.customDatasetFormula(formula, cfState.page, cfState.page_size);
    msgBox.classList.add("hidden");
    renderCustomFormulaResult(data);
  } catch (err) {
    document.getElementById("cf-result-wrap").innerHTML = "";
    msgBox.classList.remove("hidden");
    msgBox.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function renderCustomFormulaResult(data) {
  const wrap = document.getElementById("cf-result-wrap");

  if (data.type === "scalar") {
    wrap.innerHTML = `
      <div class="card">
        <h3>${escapeHtml(t("cd_result_header"))}</h3>
        <div class="kpi-row" id="cf-scalar-kpi"></div>
        <p class="form-help-text">${escapeHtml(t("cd_calculated_over").replace("{n}", data.n_rows_considered).replace("{m}", data.n_rows_total_dataset))}</p>
      </div>
    `;
    renderKpiCards("cf-scalar-kpi", [
      { label: t("cd_result_header"), value: data.result === null ? "—" : formatFormulaValue(data.result) },
    ]);
    return;
  }

  // data.type === "column": um valor por linha, paginado.
  const rowsHtml =
    data.rows
      .map(
        (r) => `
      <tr>
        <td>${r.row_id}</td>
        <td>${formatFormulaValue(r.resultado)}</td>
      </tr>
    `
      )
      .join("") || `<tr><td colspan="2">${escapeHtml(t("cd_no_results"))}</td></tr>`;

  const summaryHtml = data.summary
    ? `<p class="form-help-text">${escapeHtml(t("cd_summary_stats").replace("{mean}", fmtNum(data.summary.mean)).replace("{min}", fmtNum(data.summary.min)).replace("{max}", fmtNum(data.summary.max)))}</p>`
    : "";

  wrap.innerHTML = `
    <div class="card">
      <h3>${escapeHtml(t("cd_calculated_column_header").replace("{n}", data.n_rows).replace("{m}", data.n_rows_total_dataset))}</h3>
      ${summaryHtml}
      <div class="table-wrap">
        <table>
          <thead><tr><th>${escapeHtml(t("cd_id_header"))}</th><th>${escapeHtml(t("cd_result_header_col"))}</th></tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
      <div class="pagination-row" id="cf-pagination"></div>
    </div>
  `;
  renderCustomFormulaPagination(data);
}

// Formata um valor de resultado para mostrar na tabela/KPI: números com
// fmtNum (mesmo formato do resto da app), booleanos como "Sim"/"Não" (mais
// natural do que "true"/"false" em português), texto tal como veio.
function formatFormulaValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? t("cat_yes") : t("cat_no");
  if (typeof v === "number") return fmtNum(v);
  return escapeHtml(String(v));
}

function renderCustomFormulaPagination(data) {
  const container = document.getElementById("cf-pagination");
  const { page, total_pages, n_rows } = data;
  container.innerHTML = `
    <button id="cf-page-prev" ${page <= 1 ? "disabled" : ""}>${escapeHtml(t("data_pagination_prev"))}</button>
    <span class="pagination-info">${escapeHtml(t("cd_pagination_rows_info").replace("{page}", page).replace("{total_pages}", total_pages).replace("{total}", n_rows))}</span>
    <button id="cf-page-next" ${page >= total_pages ? "disabled" : ""}>${escapeHtml(t("data_pagination_next"))}</button>
  `;
  document.getElementById("cf-page-prev")?.addEventListener("click", () => runCustomFormula(Math.max(1, page - 1)));
  document.getElementById("cf-page-next")?.addEventListener("click", () => runCustomFormula(Math.min(total_pages, page + 1)));
}

// ------------------------------------------------------------
// As 5 páginas dependem do estado partilhado do dataset personalizado, que
// muda sempre que se importa, apaga ou treina um modelo — coisas que só
// acontecem noutra sub-página. Como o router (goToPage em main.js) só corre
// o loader de cada página UMA ÚNICA VEZ (a primeira visita — ver
// PAGE_LOADERS[name].loaded em main.js), aqui garante-se que cada clique
// seguinte no respetivo botão do menu lateral volta a carregar os dados a
// partir do backend, para nunca mostrar informação desatualizada de uma
// visita anterior.
//
// O próprio botão do menu já tem o listener do router (registado em
// main.js, que trata a primeira visita) — o listener extra aqui só entra em
// ação a partir do SEGUNDO clique em diante (contador próprio), para nunca
// disparar duas vezes em paralelo o mesmo pedido à API na primeira visita.
// ------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  const revisitLoaders = {
    customimport: refreshCustomImportStatus,
    customstats: loadCustomStatsPage,
    custompredict: () => loadCustomPredictPage(1),
    customtrain: loadCustomTrainPage,
    customformula: loadCustomFormulaPage,
  };
  const clickCounts = {};
  Object.entries(revisitLoaders).forEach(([page, loader]) => {
    const btn = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (!btn) return;
    btn.addEventListener("click", () => {
      clickCounts[page] = (clickCounts[page] || 0) + 1;
      if (clickCounts[page] > 1) loader();
    });
  });
});
