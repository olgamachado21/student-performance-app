// ============================================================
// Página: Fatores de Risco
// A página mais densa de análise estatística: destaques de hábitos e de
// contexto familiar/socioeconómico, heatmap de correlação (clicável ->
// dispersão), importância de variáveis, métricas dos modelos (com
// comparação a um baseline ingénuo), estudantes atípicos (outliers) e um
// explorador genérico de qualquer variável categórica.
// ============================================================

// Rótulos legíveis para os nomes das colunas do dataset (usados em títulos
// de eixos, tabelas e no seletor do explorador de hábitos) — mapeados para
// chaves de tradução (ver i18n.js) e resolvidos em tempo real com t(), para
// mudarem de idioma sem recarregar a página.
const HABIT_LABEL_KEYS = {
  studytime: "habit_label_studytime",
  absences: "habit_label_absences",
  failures: "habit_label_failures",
  goout: "habit_label_goout",
  Dalc: "habit_label_dalc",
  Walc: "habit_label_walc",
  freetime: "habit_label_freetime",
  health: "habit_label_health",
  school: "habit_label_school",
  address: "habit_label_address",
  paid: "habit_label_paid",
  Mjob: "habit_label_mjob",
  Fjob: "habit_label_fjob",
  reason: "habit_label_reason",
  guardian: "habit_label_guardian",
  famsize: "habit_label_famsize",
  Pstatus: "habit_label_pstatus",
  nursery: "habit_label_nursery",
  Medu: "habit_label_medu",
  Fedu: "habit_label_fedu",
  traveltime: "habit_label_traveltime",
  famrel: "habit_label_famrel",
  age: "habit_label_age",
  G3: "habit_label_g3",
};
function habitLabel(variable) {
  const key = HABIT_LABEL_KEYS[variable];
  return key ? t(key) : variable;
}

// Tradução das categorias em bruto do dataset (ex.: "at_home", "GT3") para
// rótulos legíveis — só para apresentação, o backend continua a trabalhar
// com os valores originais (group-stats, statistical-tests).
const CATEGORY_VALUE_LABEL_KEYS = {
  address: { U: "cat_address_u", R: "cat_address_r" },
  paid: { yes: "cat_yes", no: "cat_no" },
  nursery: { yes: "cat_yes", no: "cat_no" },
  Pstatus: { T: "cat_pstatus_t", A: "cat_pstatus_a" },
  famsize: { GT3: "cat_famsize_gt3", LE3: "cat_famsize_le3" },
  guardian: { mother: "cat_guardian_mother", father: "cat_guardian_father", other: "cat_guardian_other" },
  Mjob: { at_home: "cat_job_at_home", health: "cat_job_health", other: "cat_job_other", services: "cat_job_services", teacher: "cat_job_teacher" },
  Fjob: { at_home: "cat_job_at_home", health: "cat_job_health", other: "cat_job_other", services: "cat_job_services", teacher: "cat_job_teacher" },
  reason: { course: "cat_reason_course", home: "cat_reason_home", reputation: "cat_reason_reputation", other: "cat_reason_other" },
};

// Traduz um valor categórico bruto para o rótulo legível, se existir mapeamento; senão devolve o valor original.
function translateCategory(variable, value) {
  const map = CATEGORY_VALUE_LABEL_KEYS[variable];
  const key = map && map[value];
  return key ? t(key) : value;
}

let habitExplorerChart = null; // instância do gráfico do explorador de hábitos, para poder ser recriada

registerPage("risk", async () => {
  try {
    // Todos os pedidos correm em paralelo, cada um com a sua própria cache.
    const [tests, corr, fi, mm, outliers] = await Promise.all([
      cached("statisticalTests", Api.statisticalTests),
      cached("correlations", Api.correlations),
      cached("featureImportance", Api.featureImportance),
      cached("modelMetrics", Api.modelMetrics),
      cached("outliers", Api.outliers),
    ]);

    renderRiskHighlights(tests);
    renderFamilyContextHighlights(tests);
    renderCorrelationHeatmap(corr);
    renderFeatureImportanceChart(fi);
    renderModelMetrics(mm);
    renderOutliers(outliers);

    const select = document.getElementById("habit-select");
    select.addEventListener("change", () => loadHabitExplorer(select.value));
    await loadHabitExplorer(select.value);
  } catch (err) {
    console.error(err);
    document.getElementById("risk-highlights").innerHTML =
      `<div class="info-box">${escapeHtml(t("risk_load_error"))}</div>`;
  }
});

function renderRiskHighlights(tests) {
  const container = document.getElementById("risk-highlights");
  // 3 destaques principais: reprovações, tempo de estudo e consumo de álcool,
  // cada um com o coeficiente da regressão e se é estatisticamente significativo.
  const items = [
    {
      title: t("risk_highlight_failures_title"),
      text: t("risk_highlight_failures_text").replace("{v}", Math.abs(tests.failures_regression.coeficiente).toFixed(2)),
      significant: tests.failures_regression.significativo_5pct,
    },
    {
      title: t("risk_highlight_studytime_title"),
      text: t("risk_highlight_studytime_text").replace("{v}", tests.studytime_regression.coeficiente.toFixed(2)),
      significant: tests.studytime_regression.significativo_5pct,
    },
    {
      title: t("risk_highlight_alcohol_title"),
      text: t("risk_highlight_alcohol_text").replace("{v}", Math.abs(tests.alcohol_regression.coeficiente).toFixed(2)),
      significant: tests.alcohol_regression.significativo_5pct,
    },
  ];

  container.innerHTML = items.map((item) => `
    <div class="card">
      <div class="highlight-title">${item.title}</div>
      <div class="highlight-text">${item.text}</div>
      <span class="badge ${item.significant ? "badge-positive" : "badge-negative"}">
        ${item.significant ? t("badge_significant") : t("badge_not_significant")}
      </span>
    </div>
  `).join("");
}

// Contexto familiar e socioeconómico: os mesmos testes estatísticos
// (t-test/ANOVA/regressão) já usados nos 3 destaques de hábitos, mas para
// variáveis que o estudante não controla — escola, zona, explicações pagas,
// educação e profissão dos pais, motivo de escolha da escola. Os valores vêm
// sempre do mesmo /statistical-tests, calculados em tempo real sobre os
// dados atuais (incluindo os que forem adicionados em "Adicionar Dados").
function renderFamilyContextHighlights(tests) {
  const container = document.getElementById("family-context-highlights");
  if (!container || !tests) return;

  // Encontra a categoria com maior e menor média, para profissão da mãe (grupo com várias categorias).
  const mjobEntries = Object.entries(tests.mjob.medias_por_grupo);
  const mjobBest = mjobEntries.reduce((a, b) => (b[1] > a[1] ? b : a));
  const mjobWorst = mjobEntries.reduce((a, b) => (b[1] < a[1] ? b : a));

  // O mesmo para o motivo de escolha da escola.
  const reasonEntries = Object.entries(tests.reason.medias_por_grupo);
  const reasonBest = reasonEntries.reduce((a, b) => (b[1] > a[1] ? b : a));
  const reasonWorst = reasonEntries.reduce((a, b) => (b[1] < a[1] ? b : a));

  const items = [
    {
      title: t("family_school_title"),
      text: t("family_school_text").replace("{gp}", fmtNum(tests.school.categorias.GP, 1)).replace("{ms}", fmtNum(tests.school.categorias.MS, 1)),
      significant: tests.school.significativo_5pct,
    },
    {
      title: t("family_address_title"),
      text: t("family_address_text").replace("{u}", fmtNum(tests.address.categorias.U, 1)).replace("{r}", fmtNum(tests.address.categorias.R, 1)),
      significant: tests.address.significativo_5pct,
    },
    {
      title: t("family_paid_title"),
      text: t("family_paid_text").replace("{yes}", fmtNum(tests.paid.categorias.yes, 1)).replace("{no}", fmtNum(tests.paid.categorias.no, 1)),
      significant: tests.paid.significativo_5pct,
    },
    {
      title: t("family_medu_title"),
      text: t("family_medu_text")
        .replace("{sign}", tests.medu_regression.coeficiente >= 0 ? "+" : "")
        .replace("{v}", fmtNum(tests.medu_regression.coeficiente, 2)),
      significant: tests.medu_regression.significativo_5pct,
    },
    {
      title: t("family_mjob_title"),
      text: t("family_mjob_text")
        .replace("{best}", translateCategory("Mjob", mjobBest[0])).replace("{bestv}", fmtNum(mjobBest[1], 1))
        .replace("{worst}", translateCategory("Mjob", mjobWorst[0])).replace("{worstv}", fmtNum(mjobWorst[1], 1)),
      significant: tests.mjob.significativo_5pct,
    },
    {
      title: t("family_reason_title"),
      text: t("family_reason_text")
        .replace("{best}", translateCategory("reason", reasonBest[0])).replace("{bestv}", fmtNum(reasonBest[1], 1))
        .replace("{worst}", translateCategory("reason", reasonWorst[0])).replace("{worstv}", fmtNum(reasonWorst[1], 1)),
      significant: tests.reason.significativo_5pct,
    },
    {
      title: t("family_schoolsup_title"),
      text: t("family_schoolsup_text").replace("{yes}", fmtNum(tests.schoolsup.categorias.yes, 1)).replace("{no}", fmtNum(tests.schoolsup.categorias.no, 1)),
      significant: tests.schoolsup.significativo_5pct,
      // Contra-intuitivo de propósito: sem esta nota, o número sozinho lê-se
      // como "o apoio prejudica os alunos", quando é o oposto — o apoio é
      // dado a quem já está com dificuldades, por isso o grupo apoiado
      // começa em desvantagem. Correlação não implica causalidade.
      note: t("family_schoolsup_note"),
    },
  ];

  container.innerHTML = items.map((item) => `
    <div class="card">
      <div class="highlight-title">${item.title}</div>
      <div class="highlight-text">${item.text}</div>
      <span class="badge ${item.significant ? "badge-positive" : "badge-negative"}">
        ${item.significant ? t("badge_significant") : t("badge_not_significant")}
      </span>
      ${item.note ? `<p class="highlight-caveat">${item.note}</p>` : ""}
    </div>
  `).join("");
}

function renderCorrelationHeatmap(corr) {
  const container = document.getElementById("correlation-heatmap");
  const { columns, matrix } = corr;

  // Constrói a tabela do heatmap manualmente (não é um gráfico Chart.js):
  // uma linha de cabeçalho com os nomes das colunas, depois uma linha por variável.
  let html = '<table class="heatmap-table"><thead><tr><th></th>';
  columns.forEach((c) => (html += `<th>${c}</th>`));
  html += "</tr></thead><tbody>";

  matrix.forEach((row, i) => {
    html += `<tr><th>${columns[i]}</th>`;
    row.forEach((value, j) => {
      // Cor de fundo proporcional ao valor da correlação; texto branco em fundos escuros para contraste.
      const bg = correlationColor(value);
      const textColor = Math.abs(value) > 0.55 ? "#fff" : "#1E293B";
      html += `<td><div class="heatmap-cell" style="background:${bg}; color:${textColor}; padding:0.3rem 0.4rem;" title="${value}" data-heatmap-x="${columns[j]}" data-heatmap-y="${columns[i]}">${value.toFixed(2)}</div></td>`;
    });
    html += "</tr>";
  });
  html += "</tbody></table>";
  container.innerHTML = html;

  // Clicar numa célula abre um gráfico de dispersão com os pontos reais por
  // trás do coeficiente (ver openScatterModal) — um único número (ex.:
  // -0.34) não mostra a forma da relação nem os estudantes que fogem à
  // tendência geral.
  container.querySelectorAll("[data-heatmap-x]").forEach((cell) => {
    cell.classList.add("heatmap-cell-clickable");
    cell.title = `${cell.title}${t("scatter_hint_suffix")}`;
    cell.addEventListener("click", () => openScatterModal(cell.dataset.heatmapX, cell.dataset.heatmapY));
  });
}

// ------------------------------------------------------------
// Gráfico de dispersão (heatmap clicável -> scatter plot): abre uma janela
// modal com os pontos reais (x, y) de um par de variáveis do heatmap de
// correlação, mais a reta de regressão linear simples — ver o endpoint
// /scatter em src/api.py. Usa o mesmo estilo de modal do appConfirm() em
// main.js, mas com conteúdo próprio (gráfico) em vez de uma mensagem.
// ------------------------------------------------------------
let scatterModalChart = null; // instância do gráfico dentro do modal, destruída ao fechar

async function openScatterModal(x, y) {
  // Cria a sobreposição e a estrutura do modal, com um estado de "a carregar" inicial.
  const overlay = document.createElement("div");
  overlay.className = "app-modal-overlay";
  overlay.innerHTML = `
    <div class="app-modal scatter-modal" role="dialog" aria-modal="true" aria-labelledby="scatter-modal-title">
      <div class="app-modal-title" id="scatter-modal-title">${escapeHtml(habitLabel(x))} × ${escapeHtml(habitLabel(y))}</div>
      <div class="scatter-modal-body">
        <div class="scatter-modal-loading">${escapeHtml(t("scatter_loading"))}</div>
        <div class="scatter-modal-canvas-wrap hidden"><canvas></canvas></div>
        <p class="scatter-modal-summary"></p>
      </div>
      <div class="app-modal-actions">
        <button type="button" class="btn-small scatter-modal-close">${escapeHtml(t("notes_close_btn"))}</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // Fecha o modal com Escape, clique fora, ou no botão "Fechar" — e destrói o gráfico para libertar memória.
  const onKeydown = (e) => { if (e.key === "Escape") close(); };
  function close() {
    if (scatterModalChart) { scatterModalChart.destroy(); scatterModalChart = null; }
    document.removeEventListener("keydown", onKeydown, true);
    overlay.remove();
  }
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  overlay.querySelector(".scatter-modal-close").addEventListener("click", close);
  document.addEventListener("keydown", onKeydown, true);

  try {
    const data = await Api.scatter(x, y);
    const loading = overlay.querySelector(".scatter-modal-loading");
    const wrap = overlay.querySelector(".scatter-modal-canvas-wrap");
    const summary = overlay.querySelector(".scatter-modal-summary");
    loading.remove();
    wrap.classList.remove("hidden");

    const points = data.points;
    const datasets = [{
      label: t("scatter_students_suffix").replace("{n}", points.length),
      data: points,
      backgroundColor: COLORS.primaryLight,
      pointRadius: 3,
    }];

    if (data.regression) {
      // Desenha a reta de regressão como uma segunda série do tipo "line",
      // usando só os pontos extremos (x mínimo e máximo) — suficiente para uma reta.
      const xs = points.map((p) => p.x);
      const xMin = Math.min(...xs);
      const xMax = Math.max(...xs);
      const { coeficiente, intercept, r2, p_value, significativo_5pct } = data.regression;
      datasets.push({
        type: "line",
        label: t("scatter_trend_label"),
        data: [
          { x: xMin, y: intercept + coeficiente * xMin },
          { x: xMax, y: intercept + coeficiente * xMax },
        ],
        borderColor: COLORS.negative,
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
      });
      const sig = significativo_5pct ? t("badge_significant") : t("stat_not_significant_5pct");
      summary.textContent = t("scatter_summary").replace("{r2}", r2.toFixed(3)).replace("{p}", p_value).replace("{sig}", sig);
    } else {
      // Mesma variável nos dois eixos: não há regressão a mostrar, só a diagonal identidade.
      summary.textContent = t("scatter_same_variable");
    }

    scatterModalChart = new Chart(wrap.querySelector("canvas"), {
      type: "scatter",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: !!data.regression, position: "bottom" } },
        scales: {
          x: { title: { display: true, text: habitLabel(x) }, grid: { color: COLORS.border } },
          y: { title: { display: true, text: habitLabel(y) }, grid: { color: COLORS.border } },
        },
      },
    });
  } catch (err) {
    console.error(err);
    overlay.querySelector(".scatter-modal-loading").textContent = t("scatter_load_error");
  }
}

function renderFeatureImportanceChart(fi) {
  const ctx = document.getElementById("chart-feature-importance");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: fi.features,
      datasets: [{
        label: t("chart_feature_importance_label"),
        data: fi.importance,
        backgroundColor: COLORS.primary,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y", // barras horizontais — mais legível para muitas variáveis com nomes longos
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, grid: { color: COLORS.border } },
        y: { grid: { display: false } },
      },
    },
  });
}

// Colunas mostradas em cada tabela de métricas — ver renderModelMetrics.
// A validação cruzada (val. cruzada) junta média ± desvio-padrão de 5
// repetições do treino em subconjuntos diferentes dos dados, para mostrar se
// o resultado é estável ou só "sorte" da divisão treino/teste escolhida.
// "label" é uma função (não uma string fixa) para poder chamar t() em cada
// desenho da tabela, e assim refletir o idioma atual mesmo que tenha mudado
// depois deste ficheiro ter sido carregado.
function regressionMetricColumns() {
  return [
    { label: "R²", get: (m) => m.R2.toFixed(3) },
    { label: "MAE", get: (m) => m.MAE.toFixed(2) },
    { label: "RMSE", get: (m) => m.RMSE.toFixed(2) },
    { label: t("metric_r2_cv"), get: (m) => `${m.CV_R2_mean.toFixed(2)} ± ${m.CV_R2_std.toFixed(2)}` },
  ];
}

function classificationMetricColumns() {
  return [
    { label: t("metric_accuracy"), get: (m) => `${(m.Accuracy * 100).toFixed(1)}%` },
    { label: t("metric_precision"), get: (m) => `${(m.Precision * 100).toFixed(1)}%` },
    { label: t("metric_recall"), get: (m) => `${(m.Recall * 100).toFixed(1)}%` },
    { label: "F1", get: (m) => m.F1.toFixed(3) },
    { label: "AUC-ROC", get: (m) => m.ROC_AUC.toFixed(3) },
    { label: t("metric_f1_cv"), get: (m) => `${m.CV_F1_mean.toFixed(2)} ± ${m.CV_F1_std.toFixed(2)}` },
  ];
}

// Comparação contra o baseline "ingénuo" (ver compute_naive_baseline no
// backend): prever sempre a nota média da turma, sem olhar a nada — a
// referência mínima que qualquer modelo a sério tem de superar. Mostrar
// isto ao lado das métricas "abstratas" (R², MAE) torna concreto o que
// significam: quantos valores de erro o modelo poupa face a não ter
// modelo nenhum.
function renderBaselineComparison(baseline, regHabitos, bestHabitos, regCompleto, bestCompleto) {
  return `
    <div class="baseline-compare-card">
      <h4>${escapeHtml(t("baseline_title"))}</h4>
      <p class="card-subtitle">
        ${t("baseline_subtitle").replace("{v}", fmtNum(baseline.predicted_value, 1))}
      </p>
      <div class="baseline-compare-grid">
        <div class="baseline-compare-item">
          <span class="baseline-compare-label">${escapeHtml(t("baseline_label"))}</span>
          <span class="baseline-compare-value">MAE ${fmtNum(baseline.MAE, 2)}</span>
        </div>
        <div class="baseline-compare-item">
          <span class="baseline-compare-label">${regHabitos.best_model} ${escapeHtml(t("baseline_habits_suffix"))}</span>
          <span class="baseline-compare-value">MAE ${fmtNum(bestHabitos.MAE, 2)}</span>
          <span class="badge badge-positive">${t("baseline_less_error").replace("{v}", fmtNum(baseline.melhoria_habitos_pct, 1))}</span>
        </div>
        <div class="baseline-compare-item">
          <span class="baseline-compare-label">${regCompleto.best_model} ${escapeHtml(t("baseline_full_suffix"))}</span>
          <span class="baseline-compare-value">MAE ${fmtNum(bestCompleto.MAE, 2)}</span>
          <span class="badge badge-positive">${t("baseline_less_error").replace("{v}", fmtNum(baseline.melhoria_completo_pct, 1))}</span>
        </div>
      </div>
    </div>
  `;
}

// Constrói uma tabela HTML de métricas, com a linha do melhor modelo destacada.
function buildMetricsTable(results, bestModel, columns) {
  const modelNames = Object.keys(results);
  return `
    <table class="model-metrics-table">
      <thead>
        <tr>
          <th>${escapeHtml(t("metrics_table_model_col"))}</th>
          ${columns.map((c) => `<th>${c.label}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${modelNames.map((name) => `
          <tr class="${name === bestModel ? "model-metrics-best-row" : ""}">
            <td>${name}${name === bestModel ? ` <span class="badge badge-positive">${escapeHtml(t("metrics_table_best_badge"))}</span>` : ""}</td>
            ${columns.map((c) => `<td>${c.get(results[name])}</td>`).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

// Qualidade do modelo: três tabelas (regressão só-hábitos, regressão
// completa, classificação aprovado/reprovado) com as métricas calculadas no
// treino (train_model.py) sobre um conjunto de teste que o modelo nunca viu
// — mais um resumo em linguagem simples do R² dos dois modelos de regressão,
// para se perceber de imediato quanto "hábitos por si só" já explicam do
// resultado, sem ser preciso ler a tabela toda.
function renderModelMetrics(mm) {
  const wrap = document.getElementById("model-metrics-wrap");
  if (!wrap || !mm) return;

  const regHabitos = mm.regressao_habitos;
  const regCompleto = mm.regressao_completo;
  const clf = mm.classificacao;
  const bestHabitos = regHabitos.results[regHabitos.best_model];
  const bestCompleto = regCompleto.results[regCompleto.best_model];
  const baseline = mm.baseline_ingenuo;

  const summary = t("model_metrics_summary")
    .replace("{model}", regCompleto.best_model)
    .replace("{pct1}", Math.round(bestCompleto.R2 * 100))
    .replace("{r1}", bestCompleto.R2.toFixed(2))
    .replace("{pct2}", Math.round(bestHabitos.R2 * 100))
    .replace("{model2}", regHabitos.best_model)
    .replace("{r2}", bestHabitos.R2.toFixed(2));

  wrap.innerHTML = `
    <p class="model-metrics-summary">${summary}</p>
    ${baseline ? renderBaselineComparison(baseline, regHabitos, bestHabitos, regCompleto, bestCompleto) : ""}
    <div class="model-metrics-group">
      <h4>${escapeHtml(t("metrics_group_habits"))}</h4>
      ${buildMetricsTable(regHabitos.results, regHabitos.best_model, regressionMetricColumns())}
    </div>
    <div class="model-metrics-group">
      <h4>${escapeHtml(t("metrics_group_full"))}</h4>
      ${buildMetricsTable(regCompleto.results, regCompleto.best_model, regressionMetricColumns())}
    </div>
    <div class="model-metrics-group">
      <h4>${escapeHtml(t("metrics_group_classification"))}</h4>
      ${buildMetricsTable(clf.results, clf.best_model, classificationMetricColumns())}
    </div>
  `;
}

// Link temporário com "download" — funciona tanto no browser como na janela
// de desktop (pywebview), ao contrário de window.open() (ver fichas.js, de
// onde este padrão foi copiado).
function downloadFichaFor(studentId) {
  const link = document.createElement("a");
  link.href = Api.fichaUrl(studentId);
  link.download = `ficha_estudante_${studentId}.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Perfis atípicos: tabela dos estudantes cujo resíduo (nota real - nota
// prevista pelo modelo para o SEU perfil) é grande de mais para ser
// coincidência — ver detect_outliers em predict.py. Cada linha tem um botão
// para abrir logo a ficha PDF do estudante, para investigar o caso.
function renderOutliers(data) {
  const wrap = document.getElementById("outliers-table-wrap");
  if (!wrap || !data) return;

  const students = data.students || [];
  if (students.length === 0) {
    wrap.innerHTML = `<div class="info-box">${escapeHtml(t("outliers_empty").replace("{n}", data.z_threshold))}</div>`;
    return;
  }

  wrap.innerHTML = `
    <table class="outliers-table">
      <thead>
        <tr>
          <th>${escapeHtml(t("outliers_th_student"))}</th>
          <th>${escapeHtml(t("outliers_th_actual"))}</th>
          <th>${escapeHtml(t("outliers_th_predicted"))}</th>
          <th>${escapeHtml(t("outliers_th_residual"))}</th>
          <th>${escapeHtml(t("outliers_th_direction"))}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${students.map((s) => `
          <tr>
            <td>#${s.student_id}</td>
            <td>${s.actual_grade.toFixed(1)}</td>
            <td>${s.predicted_grade.toFixed(1)}</td>
            <td class="${s.residual > 0 ? "outlier-positive" : "outlier-negative"}">${s.residual > 0 ? "+" : ""}${s.residual.toFixed(2)}</td>
            <td>
              <span class="badge ${s.residual > 0 ? "badge-positive" : "badge-negative"}">${s.direction}</span>
            </td>
            <td><button type="button" class="btn-small" data-outlier-ficha="${s.student_id}">${escapeHtml(t("outliers_view_ficha_btn"))}</button></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  // Cada botão "Ver ficha" descarrega diretamente o PDF desse estudante.
  wrap.querySelectorAll("[data-outlier-ficha]").forEach((btn) => {
    btn.addEventListener("click", () => downloadFichaFor(btn.dataset.outlierFicha));
  });
}

async function loadHabitExplorer(variable) {
  // Pede as médias de nota por categoria da variável escolhida (ex.: nota média por profissão da mãe).
  const data = await Api.groupStats(variable);
  const ctx = document.getElementById("chart-habit-explorer");

  if (habitExplorerChart) habitExplorerChart.destroy();
  habitExplorerChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.categories.map((c) => translateCategory(variable, c)),
      datasets: [{
        label: t("habit_explorer_avg_grade_label").replace("{habit}", habitLabel(variable)),
        data: data.avg_grade,
        backgroundColor: COLORS.primary,
        borderRadius: 6,
        maxBarThickness: 50,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          // Mostra também o tamanho da amostra (nº de estudantes) de cada categoria, no tooltip.
          callbacks: {
            afterLabel: (ctx) => t("habit_explorer_tooltip_n").replace("{n}", data.n_students[ctx.dataIndex]),
          },
        },
      },
      scales: {
        x: { title: { display: true, text: habitLabel(variable) }, grid: { display: false } },
        y: { title: { display: true, text: t("habit_explorer_grade_axis") }, beginAtZero: true, grid: { color: COLORS.border } },
      },
    },
  });
}
