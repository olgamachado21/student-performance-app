// ============================================================
// Página: Fatores de Risco
// A página mais densa de análise estatística: destaques de hábitos e de
// contexto familiar/socioeconómico, heatmap de correlação (clicável ->
// dispersão), importância de variáveis, métricas dos modelos (com
// comparação a um baseline ingénuo), estudantes atípicos (outliers) e um
// explorador genérico de qualquer variável categórica.
// ============================================================

// Rótulos legíveis em português para os nomes das colunas do dataset
// (usados em títulos de eixos, tabelas e no seletor do explorador de hábitos).
const HABIT_LABELS = {
  studytime: "Tempo de estudo",
  absences: "Faltas",
  failures: "Reprovações anteriores",
  goout: "Sair com amigos",
  Dalc: "Álcool (dias úteis)",
  Walc: "Álcool (fim de semana)",
  freetime: "Tempo livre",
  health: "Saúde",
  school: "Escola",
  address: "Zona (urbana/rural)",
  paid: "Explicações pagas",
  Mjob: "Profissão da mãe",
  Fjob: "Profissão do pai",
  reason: "Motivo de escolha da escola",
  guardian: "Encarregado de educação",
  famsize: "Tamanho da família",
  Pstatus: "Pais juntos/separados",
  nursery: "Frequentou infantário",
  Medu: "Educação da mãe",
  Fedu: "Educação do pai",
  traveltime: "Tempo de deslocação até à escola",
  famrel: "Relação familiar",
  age: "Idade",
  G3: "Nota final (G3)",
};

// Tradução das categorias em bruto do dataset (ex.: "at_home", "GT3") para
// rótulos legíveis em português — só para apresentação, o backend continua a
// trabalhar com os valores originais (group-stats, statistical-tests).
const CATEGORY_VALUE_LABELS = {
  address: { U: "Urbana", R: "Rural" },
  paid: { yes: "Sim", no: "Não" },
  nursery: { yes: "Sim", no: "Não" },
  Pstatus: { T: "Juntos", A: "Separados" },
  famsize: { GT3: "> 3 pessoas", LE3: "≤ 3 pessoas" },
  guardian: { mother: "Mãe", father: "Pai", other: "Outro" },
  Mjob: { at_home: "Em casa", health: "Saúde", other: "Outra", services: "Serviços", teacher: "Professor(a)" },
  Fjob: { at_home: "Em casa", health: "Saúde", other: "Outra", services: "Serviços", teacher: "Professor(a)" },
  reason: { course: "Curso oferecido", home: "Perto de casa", reputation: "Reputação da escola", other: "Outro motivo" },
};

// Traduz um valor categórico bruto para o rótulo legível, se existir mapeamento; senão devolve o valor original.
function translateCategory(variable, value) {
  const map = CATEGORY_VALUE_LABELS[variable];
  return (map && map[value]) || value;
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
      `<div class="info-box">Não foi possível carregar os dados. Confirma que a API está a correr.</div>`;
  }
});

function renderRiskHighlights(tests) {
  const container = document.getElementById("risk-highlights");
  // 3 destaques principais: reprovações, tempo de estudo e consumo de álcool,
  // cada um com o coeficiente da regressão e se é estatisticamente significativo.
  const items = [
    {
      title: "Reprovações anteriores",
      text: `Cada reprovação anterior reduz a nota em ~${Math.abs(tests.failures_regression.coeficiente).toFixed(2)} valores`,
      significant: tests.failures_regression.significativo_5pct,
    },
    {
      title: "Tempo de estudo",
      text: `Cada nível extra de estudo aumenta a nota em ~${tests.studytime_regression.coeficiente.toFixed(2)} valores`,
      significant: tests.studytime_regression.significativo_5pct,
    },
    {
      title: "Consumo de álcool",
      text: `Cada nível extra reduz a nota em ~${Math.abs(tests.alcohol_regression.coeficiente).toFixed(2)} valores`,
      significant: tests.alcohol_regression.significativo_5pct,
    },
  ];

  container.innerHTML = items.map((item) => `
    <div class="card">
      <div class="highlight-title">${item.title}</div>
      <div class="highlight-text">${item.text}</div>
      <span class="badge ${item.significant ? "badge-positive" : "badge-negative"}">
        ${item.significant ? "estatisticamente significativo" : "não significativo"}
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
      title: "Escola",
      text: `GP: ${fmtNum(tests.school.categorias.GP, 1)} valores vs. MS: ${fmtNum(tests.school.categorias.MS, 1)} valores`,
      significant: tests.school.significativo_5pct,
    },
    {
      title: "Zona de residência",
      text: `Urbana: ${fmtNum(tests.address.categorias.U, 1)} valores vs. Rural: ${fmtNum(tests.address.categorias.R, 1)} valores`,
      significant: tests.address.significativo_5pct,
    },
    {
      title: "Explicações pagas",
      text: `Paga: ${fmtNum(tests.paid.categorias.yes, 1)} valores vs. Não paga: ${fmtNum(tests.paid.categorias.no, 1)} valores`,
      significant: tests.paid.significativo_5pct,
    },
    {
      title: "Educação da mãe",
      text: `Cada nível de escolaridade da mãe está associado a ${tests.medu_regression.coeficiente >= 0 ? "+" : ""}${fmtNum(tests.medu_regression.coeficiente, 2)} valores na nota final`,
      significant: tests.medu_regression.significativo_5pct,
    },
    {
      title: "Profissão da mãe",
      text: `Maior média: ${translateCategory("Mjob", mjobBest[0])} (${fmtNum(mjobBest[1], 1)}) — menor: ${translateCategory("Mjob", mjobWorst[0])} (${fmtNum(mjobWorst[1], 1)})`,
      significant: tests.mjob.significativo_5pct,
    },
    {
      title: "Motivo de escolha da escola",
      text: `Maior média: "${translateCategory("reason", reasonBest[0])}" (${fmtNum(reasonBest[1], 1)}) — menor: "${translateCategory("reason", reasonWorst[0])}" (${fmtNum(reasonWorst[1], 1)})`,
      significant: tests.reason.significativo_5pct,
    },
    {
      title: "Apoio educativo extra",
      text: `Com apoio: ${fmtNum(tests.schoolsup.categorias.yes, 1)} valores vs. Sem apoio: ${fmtNum(tests.schoolsup.categorias.no, 1)} valores`,
      significant: tests.schoolsup.significativo_5pct,
      // Contra-intuitivo de propósito: sem esta nota, o número sozinho lê-se
      // como "o apoio prejudica os alunos", quando é o oposto — o apoio é
      // dado a quem já está com dificuldades, por isso o grupo apoiado
      // começa em desvantagem. Correlação não implica causalidade.
      note: "Não significa que o apoio prejudique: o apoio é atribuído a quem já está com mais dificuldades, por isso este grupo parte em desvantagem. Correlação não é causalidade.",
    },
  ];

  container.innerHTML = items.map((item) => `
    <div class="card">
      <div class="highlight-title">${item.title}</div>
      <div class="highlight-text">${item.text}</div>
      <span class="badge ${item.significant ? "badge-positive" : "badge-negative"}">
        ${item.significant ? "estatisticamente significativo" : "não significativo"}
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
    cell.title = `${cell.title} — clica para veres a relação em detalhe`;
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
      <div class="app-modal-title" id="scatter-modal-title">${escapeHtml(HABIT_LABELS[x] || x)} × ${escapeHtml(HABIT_LABELS[y] || y)}</div>
      <div class="scatter-modal-body">
        <div class="scatter-modal-loading">A carregar...</div>
        <div class="scatter-modal-canvas-wrap hidden"><canvas></canvas></div>
        <p class="scatter-modal-summary"></p>
      </div>
      <div class="app-modal-actions">
        <button type="button" class="btn-small scatter-modal-close">Fechar</button>
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
      label: `${points.length} estudantes`,
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
        label: "Tendência (regressão linear)",
        data: [
          { x: xMin, y: intercept + coeficiente * xMin },
          { x: xMax, y: intercept + coeficiente * xMax },
        ],
        borderColor: COLORS.negative,
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
      });
      summary.textContent = `R² = ${r2.toFixed(3)} · p = ${p_value} · ${significativo_5pct ? "estatisticamente significativo" : "não significativo a 5%"}`;
    } else {
      // Mesma variável nos dois eixos: não há regressão a mostrar, só a diagonal identidade.
      summary.textContent = "Mesma variável nos dois eixos — cada ponto está sobre a diagonal.";
    }

    scatterModalChart = new Chart(wrap.querySelector("canvas"), {
      type: "scatter",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: !!data.regression, position: "bottom" } },
        scales: {
          x: { title: { display: true, text: HABIT_LABELS[x] || x }, grid: { color: COLORS.border } },
          y: { title: { display: true, text: HABIT_LABELS[y] || y }, grid: { color: COLORS.border } },
        },
      },
    });
  } catch (err) {
    console.error(err);
    overlay.querySelector(".scatter-modal-loading").textContent = "Não foi possível carregar o gráfico.";
  }
}

function renderFeatureImportanceChart(fi) {
  const ctx = document.getElementById("chart-feature-importance");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: fi.features,
      datasets: [{
        label: "Importância relativa",
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
const REGRESSION_METRIC_COLUMNS = [
  { label: "R²", get: (m) => m.R2.toFixed(3) },
  { label: "MAE", get: (m) => m.MAE.toFixed(2) },
  { label: "RMSE", get: (m) => m.RMSE.toFixed(2) },
  { label: "R² (val. cruzada)", get: (m) => `${m.CV_R2_mean.toFixed(2)} ± ${m.CV_R2_std.toFixed(2)}` },
];

const CLASSIFICATION_METRIC_COLUMNS = [
  { label: "Exatidão", get: (m) => `${(m.Accuracy * 100).toFixed(1)}%` },
  { label: "Precisão", get: (m) => `${(m.Precision * 100).toFixed(1)}%` },
  { label: "Sensibilidade", get: (m) => `${(m.Recall * 100).toFixed(1)}%` },
  { label: "F1", get: (m) => m.F1.toFixed(3) },
  { label: "AUC-ROC", get: (m) => m.ROC_AUC.toFixed(3) },
  { label: "F1 (val. cruzada)", get: (m) => `${m.CV_F1_mean.toFixed(2)} ± ${m.CV_F1_std.toFixed(2)}` },
];

// Comparação contra o baseline "ingénuo" (ver compute_naive_baseline no
// backend): prever sempre a nota média da turma, sem olhar a nada — a
// referência mínima que qualquer modelo a sério tem de superar. Mostrar
// isto ao lado das métricas "abstratas" (R², MAE) torna concreto o que
// significam: quantos valores de erro o modelo poupa face a não ter
// modelo nenhum.
function renderBaselineComparison(baseline, regHabitos, bestHabitos, regCompleto, bestCompleto) {
  return `
    <div class="baseline-compare-card">
      <h4>O modelo acrescenta valor real?</h4>
      <p class="card-subtitle">
        Comparação contra o baseline mais simples possível: prever sempre a nota média da turma
        (${fmtNum(baseline.predicted_value, 1)} valores), sem olhar a nenhum hábito ou dado do estudante.
      </p>
      <div class="baseline-compare-grid">
        <div class="baseline-compare-item">
          <span class="baseline-compare-label">Baseline (média da turma)</span>
          <span class="baseline-compare-value">MAE ${fmtNum(baseline.MAE, 2)}</span>
        </div>
        <div class="baseline-compare-item">
          <span class="baseline-compare-label">${regHabitos.best_model} (só hábitos)</span>
          <span class="baseline-compare-value">MAE ${fmtNum(bestHabitos.MAE, 2)}</span>
          <span class="badge badge-positive">${fmtNum(baseline.melhoria_habitos_pct, 1)}% menos erro</span>
        </div>
        <div class="baseline-compare-item">
          <span class="baseline-compare-label">${regCompleto.best_model} (com G1/G2)</span>
          <span class="baseline-compare-value">MAE ${fmtNum(bestCompleto.MAE, 2)}</span>
          <span class="badge badge-positive">${fmtNum(baseline.melhoria_completo_pct, 1)}% menos erro</span>
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
          <th>Modelo</th>
          ${columns.map((c) => `<th>${c.label}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${modelNames.map((name) => `
          <tr class="${name === bestModel ? "model-metrics-best-row" : ""}">
            <td>${name}${name === bestModel ? ' <span class="badge badge-positive">melhor</span>' : ""}</td>
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

  wrap.innerHTML = `
    <p class="model-metrics-summary">
      O modelo <strong>${regCompleto.best_model}</strong> (com as notas de períodos anteriores) explica
      <strong>${Math.round(bestCompleto.R2 * 100)}%</strong> da variação na nota final (R²=${bestCompleto.R2.toFixed(2)}),
      contra <strong>${Math.round(bestHabitos.R2 * 100)}%</strong> usando só hábitos e contexto
      (<strong>${regHabitos.best_model}</strong>, R²=${bestHabitos.R2.toFixed(2)}) — o histórico de notas ajuda
      bastante, como seria de esperar, mas os hábitos por si só já explicam uma parte real do resultado.
    </p>
    ${baseline ? renderBaselineComparison(baseline, regHabitos, bestHabitos, regCompleto, bestCompleto) : ""}
    <div class="model-metrics-group">
      <h4>Regressão — nota final, só hábitos/contexto (sem G1/G2)</h4>
      ${buildMetricsTable(regHabitos.results, regHabitos.best_model, REGRESSION_METRIC_COLUMNS)}
    </div>
    <div class="model-metrics-group">
      <h4>Regressão — nota final, com G1/G2</h4>
      ${buildMetricsTable(regCompleto.results, regCompleto.best_model, REGRESSION_METRIC_COLUMNS)}
    </div>
    <div class="model-metrics-group">
      <h4>Classificação — aprovado vs reprovado</h4>
      ${buildMetricsTable(clf.results, clf.best_model, CLASSIFICATION_METRIC_COLUMNS)}
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
    wrap.innerHTML = `<div class="info-box">Nenhum estudante se desviou o suficiente do esperado (limiar: ${data.z_threshold} desvios-padrão) para ser sinalizado.</div>`;
    return;
  }

  wrap.innerHTML = `
    <table class="outliers-table">
      <thead>
        <tr>
          <th>Estudante</th>
          <th>Nota real</th>
          <th>Nota prevista</th>
          <th>Resíduo</th>
          <th>Direção</th>
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
            <td><button type="button" class="btn-small" data-outlier-ficha="${s.student_id}">Ver ficha</button></td>
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
        label: `Nota média (${HABIT_LABELS[variable] || variable})`,
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
            afterLabel: (ctx) => `n = ${data.n_students[ctx.dataIndex]} estudantes`,
          },
        },
      },
      scales: {
        x: { title: { display: true, text: HABIT_LABELS[variable] || variable }, grid: { display: false } },
        y: { title: { display: true, text: "Nota final (G3)" }, beginAtZero: true, grid: { color: COLORS.border } },
      },
    },
  });
}
