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

// Formata uma data ISO (ex.: "2026-08-20T15:05:52") para o formato curto português.
function fmtDateTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return isoString;
  return d.toLocaleString("pt-PT", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
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
    card.innerHTML = `<p class="form-help-text">Ainda não importaste nenhum dataset personalizado — carrega um ficheiro abaixo para começar.</p>`;
    return;
  }
  const columnsList = status.columns.join(", ");
  const detectedCount = Object.keys(status.detected_student_fields || {}).length;
  card.innerHTML = `
    <h3>Dataset ativo</h3>
    <p><strong>${escapeHtml(status.filename || "Sem nome")}</strong> — ${status.n_rows} linha(s), ${status.n_columns} coluna(s), importado em ${fmtDateTime(status.imported_at)}.</p>
    <p class="form-help-text">Colunas: ${escapeHtml(columnsList)}.</p>
    ${
      detectedCount > 0
        ? `<p class="form-help-text">${detectedCount} coluna(s) detetada(s) automaticamente como parecidas com dados de estudantes da StudentPerfomance — a página Previsões está disponível.</p>`
        : `<p class="form-help-text">Nenhuma coluna parecida com dados de estudantes foi detetada — a página Previsões não está disponível para este dataset, mas Estatísticas, Fórmulas e Treinar Modelo continuam a funcionar normalmente.</p>`
    }
    <button type="button" class="btn-small btn-small-danger" id="ci-delete-btn">Remover dataset personalizado</button>
  `;
  document.getElementById("ci-delete-btn").addEventListener("click", handleCustomImportDelete);
}

async function handleCustomImportDelete() {
  const ok = await appConfirm(
    "Remover o dataset personalizado importado (dados, estatísticas, previsões e modelo treinado)? Esta ação não pode ser desfeita.",
    { title: "Remover dataset personalizado", confirmLabel: "Remover", danger: true }
  );
  if (!ok) return;
  try {
    await Api.customDatasetDelete();
    renderCustomImportStatusCard({ imported: false });
    showToast("Dataset personalizado removido.", { type: "info" });
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
    msgBox.textContent = "Escolhe um ficheiro (.csv, .xlsx ou .xls) primeiro.";
    return;
  }

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "A carregar…";
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
  document.getElementById("ci-mapping-help").textContent =
    `Ficheiro "${staged.filename}" — ${staged.n_rows} linha(s), ${staged.columns.length} coluna(s): ${staged.columns.join(", ")}. ` +
    `As colunas ficam tal como estão no ficheiro — não é preciso mapear nada.`;

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
  btn.textContent = "A importar…";
  try {
    const status = await Api.customDatasetImport();
    msgBox.classList.add("hidden");
    document.getElementById("ci-mapping-card").classList.add("hidden");
    document.getElementById("ci-file-input").value = "";
    renderCustomImportStatusCard(status);
    showToast(`Dataset personalizado importado: ${status.n_rows} linha(s).`, { type: "success" });
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
    { label: "Linhas", value: stats.n_rows },
    { label: "Colunas", value: stats.n_columns },
  ];
  if (stats.average_grade !== undefined && stats.average_grade !== null) {
    items.push({ label: "Nota média (G3)", value: `${fmtNum(stats.average_grade)} / 20` });
  }
  if (stats.pass_rate !== undefined && stats.pass_rate !== null) {
    items.push({ label: "Taxa de aprovação", value: fmtPct(stats.pass_rate) });
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
        label: "Nº de linhas",
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
        labels: ["Aprovado", "Reprovado"],
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
      summary = `média ${fmtNum(info.mean)} · mediana ${fmtNum(info.median)} · desvio-padrão ${fmtNum(info.std)} · min ${fmtNum(info.min)} · max ${fmtNum(info.max)}`;
    } else {
      summary = Object.entries(info.counts)
        .map(([cat, count]) => `${escapeHtml(cat)}: ${count}`)
        .join(" · ");
      if (info.n_distinct > Object.keys(info.counts).length) {
        summary += ` · (+${info.n_distinct - Object.keys(info.counts).length} categorias)`;
      }
    }
    return `
      <tr>
        <td>${escapeHtml(col)}</td>
        <td>${info.type === "numeric" ? "Numérico" : "Categórico"}</td>
        <td>${summary}</td>
      </tr>
    `;
  });
  tbody.innerHTML = rows.join("") || `<tr><td colspan="3">Sem colunas para mostrar.</td></tr>`;
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
      <td>${p.aprovado_previsto ? '<span class="pill pill-yes">Sim</span>' : '<span class="pill pill-no">Não</span>'}</td>
      <td>${p.actual_grade !== undefined ? fmtNum(p.actual_grade) : "—"}</td>
    </tr>
  `).join("");
  tbody.innerHTML = rows || `<tr><td colspan="5">Sem linhas para mostrar.</td></tr>`;
}

function renderCustomPredictPagination(data) {
  const container = document.getElementById("cp-pagination");
  const { page, total_pages, total } = data;
  container.innerHTML = `
    <button id="cp-page-prev" ${page <= 1 ? "disabled" : ""}>← Anterior</button>
    <span class="pagination-info">Página ${page} de ${total_pages} (${total} linha(s))</span>
    <button id="cp-page-next" ${page >= total_pages ? "disabled" : ""}>Seguinte →</button>
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
    empty.innerHTML = `Ainda não importaste nenhum dataset personalizado. <button type="button" class="link-button" id="ct-goto-import">Importar agora</button>`;
    content.classList.add("hidden");
    wireGotoImportButton("ct-goto-import");
    return;
  }
  if (!status.can_train) {
    empty.classList.remove("hidden");
    empty.textContent = `Para treinar um modelo com este dataset, é preciso ter pelo menos ${status.min_rows_for_train} linhas e 2 colunas (tens ${status.n_rows} linha(s) e ${status.n_columns} coluna(s)).`;
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
    .join("") || `<p class="form-help-text">Não há mais colunas disponíveis como recurso.</p>`;
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
    msgBox.textContent = "Escolhe a coluna a prever.";
    return;
  }
  if (featureCols.length === 0) {
    msgBox.classList.remove("hidden");
    msgBox.textContent = "Escolhe pelo menos uma coluna-recurso.";
    return;
  }

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "A treinar…";
  try {
    const metrics = await Api.customDatasetTrain(targetCol, featureCols);
    msgBox.classList.add("hidden");
    renderCustomTrainResults(metrics);
    showToast("Modelo treinado com sucesso.", { type: "success" });
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
      <thead><tr><th>Modelo</th>${metricNames.map((k) => `<th>${escapeHtml(k)}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderCustomTrainResults(metrics) {
  const container = document.getElementById("ct-results");
  const featureLabels = metrics.feature_cols.join(", ");
  const isRegression = metrics.task === "regression";
  const taskLabel = isRegression ? `Regressão — prever "${metrics.target}"` : `Classificação — prever "${metrics.target}"`;
  const results = isRegression ? metrics.regression : metrics.classification;
  container.innerHTML = `
    <div class="card">
      <h3>${escapeHtml(taskLabel)}</h3>
      <p class="form-help-text">Variáveis usadas: ${escapeHtml(featureLabels)} — ${metrics.n_rows} linha(s).</p>
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
          ? ' title="Nomes de coluna com espaços não podem ser usados diretamente numa fórmula."'
          : "";
        return `<button type="button" class="cluster-student-chip" data-field="${escapeAttr(c)}" ${hasSpaces ? "disabled" : ""}${title}>${escapeHtml(c)}${hasSpaces ? " ⚠" : ""}</button>`;
      })
      .join("") || `<p class="form-help-text">Sem colunas disponíveis.</p>`;
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
    msgBox.textContent = "Escreve uma fórmula antes de calcular.";
    return;
  }
  cfState.page = page;

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "A calcular…";
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
        <h3>Resultado</h3>
        <div class="kpi-row" id="cf-scalar-kpi"></div>
        <p class="form-help-text">Calculado sobre ${data.n_rows_considered} de ${data.n_rows_total_dataset} linha(s).</p>
      </div>
    `;
    renderKpiCards("cf-scalar-kpi", [
      { label: "Resultado", value: data.result === null ? "—" : formatFormulaValue(data.result) },
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
      .join("") || `<tr><td colspan="2">Sem resultados.</td></tr>`;

  const summaryHtml = data.summary
    ? `<p class="form-help-text">Média: ${fmtNum(data.summary.mean)} · Mínimo: ${fmtNum(data.summary.min)} · Máximo: ${fmtNum(data.summary.max)}</p>`
    : "";

  wrap.innerHTML = `
    <div class="card">
      <h3>Coluna calculada (${data.n_rows} de ${data.n_rows_total_dataset} linha(s))</h3>
      ${summaryHtml}
      <div class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Resultado</th></tr></thead>
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
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (typeof v === "number") return fmtNum(v);
  return escapeHtml(String(v));
}

function renderCustomFormulaPagination(data) {
  const container = document.getElementById("cf-pagination");
  const { page, total_pages, n_rows } = data;
  container.innerHTML = `
    <button id="cf-page-prev" ${page <= 1 ? "disabled" : ""}>← Anterior</button>
    <span class="pagination-info">Página ${page} de ${total_pages} (${n_rows} linha(s))</span>
    <button id="cf-page-next" ${page >= total_pages ? "disabled" : ""}>Seguinte →</button>
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
