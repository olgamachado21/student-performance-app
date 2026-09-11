// ============================================================
// Página: Visão Geral
// Primeira página de análise: KPIs gerais, resumo automático em linguagem
// natural, e 3 gráficos interativos (histograma de notas, aprovado/
// reprovado, taxa de aprovação por tempo de estudo) — todos clicáveis para
// navegar para outras páginas já com o filtro correspondente aplicado.
// ============================================================

registerPage("overview", async () => {
  // Mostra 4 placeholders animados enquanto os dados carregam.
  showSkeletonPlaceholders("overview-kpis", { count: 4 });
  try {
    // Os 3 pedidos correm em paralelo (mais rápido do que um de cada vez), com cache.
    const [stats, gradeDist, passFail] = await Promise.all([
      cached("stats", Api.stats),
      cached("gradeDistribution", Api.gradeDistribution),
      cached("passFailCounts", Api.passFailCounts),
    ]);

    renderKpiCards("overview-kpis", [
      { label: t("overview_kpi_students"), value: stats.n_students },
      { label: t("overview_kpi_avg_grade"), value: `${fmtNum(stats.average_grade)} / 20` },
      { label: t("overview_kpi_pass_rate"), value: fmtPct(stats.pass_rate) },
      { label: t("overview_kpi_avg_absences"), value: fmtNum(stats.average_absences) },
    ]);

    // Resumo automático em linguagem natural (Ideia 5) — ver
    // generate_overview_summary no backend.
    const summaryEl = document.getElementById("overview-summary-text");
    if (summaryEl) summaryEl.textContent = stats.summary_text || "";

    renderGradeDistributionChart(gradeDist);
    renderPassFailChart(passFail);
    renderStudytimeRateChart(stats);
  } catch (err) {
    console.error(err);
    document.getElementById("overview-kpis").innerHTML =
      `<div class="info-box">${escapeHtml(t("overview_load_error"))}</div>`;
  }
});

// Faixas de desempenho iguais às usadas no backend (ver perf_band em
// data_processing.py) — usado para traduzir o valor médio de um intervalo do
// histograma de notas no filtro correspondente da página "Dados", quando se
// clica numa barra (ver onClick em renderGradeDistributionChart).
function gradeToPerfBand(grade) {
  if (grade < 10) return "Insuficiente";
  if (grade < 14) return "Suficiente";
  if (grade < 17) return "Bom";
  return "Excelente";
}

// Cursor em forma de "mão" só quando o rato está sobre uma barra/fatia
// clicável — sinaliza que o gráfico é interativo sem precisar de mais texto.
function pointerCursorOnHover(evt, elements) {
  evt.native.target.style.cursor = elements.length ? "pointer" : "default";
}

function renderGradeDistributionChart(data) {
  const ctx = document.getElementById("chart-grade-distribution");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.labels, // ex.: ["0-1", "1-2", ..., "19-20"]
      datasets: [{
        label: t("chart_students_count_label"),
        data: data.counts,
        backgroundColor: COLORS.primary,
        borderRadius: 4,
        maxBarThickness: 22,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onHover: pointerCursorOnHover,
      // Clicar numa barra do histograma navega para "Dados" já filtrada
      // pelo nível de desempenho (perf_band) correspondente ao intervalo de
      // notas dessa barra — para ver logo a lista de estudantes por trás do
      // número, em vez de só olhar para a forma da distribuição.
      onClick: (evt, elements) => {
        if (!elements.length) return; // clique fora de qualquer barra -> ignora
        const label = data.labels[elements[0].index]; // ex.: "8.5-9.5"
        const [lo, hi] = label.split("-").map(Number);
        const band = gradeToPerfBand((lo + hi) / 2); // usa o ponto médio do intervalo
        goToPage("data", { perf_band: band });
      },
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxRotation: 90, minRotation: 90, font: { size: 9 } }, grid: { display: false } },
        y: { beginAtZero: true, grid: { color: COLORS.border } },
      },
    },
  });
}

function renderPassFailChart(data) {
  const ctx = document.getElementById("chart-pass-fail");
  new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: [t("chart_pass_label"), t("chart_fail_label")],
      datasets: [{
        data: [data.aprovados, data.reprovados],
        backgroundColor: [COLORS.positive, COLORS.negative],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "65%", // grossura do anel do gráfico "donut"
      onHover: pointerCursorOnHover,
      // Clicar em "Aprovado"/"Reprovado" navega para "Dados" filtrada por
      // risco (at_risk) — a aproximação mais próxima disponível na página
      // Dados, já que todo o estudante reprovado está sempre marcado como
      // em risco (ver at_risk em data_processing.py), mesmo que o inverso
      // nem sempre se verifique (também há aprovados em risco por faltas ou
      // reprovações anteriores).
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const isReprovado = elements[0].index === 1; // índice 1 = "Reprovado" na lista de labels
        goToPage("data", { at_risk: isReprovado ? "1" : "0" });
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            // Mostra o valor absoluto E a percentagem, em vez de só o valor bruto.
            label: (ctx) => {
              const total = data.aprovados + data.reprovados;
              const pct = ((ctx.parsed / total) * 100).toFixed(1);
              return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

function renderStudytimeRateChart(stats) {
  // Rótulos legíveis para os 4 níveis de tempo de estudo (1-4) do dataset original.
  const labels = { 1: "< 2h", 2: "2-5h", 3: "5-10h", 4: "> 10h" };
  // Ordena as entradas pelo nível numérico (as chaves de um objeto JS não garantem ordem numérica).
  const entries = Object.entries(stats.pass_rate_by_studytime).sort((a, b) => a[0] - b[0]);
  const ctx = document.getElementById("chart-studytime-rate");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: entries.map(([k]) => labels[k] || k),
      datasets: [{
        label: t("overview_kpi_pass_rate"),
        data: entries.map(([, v]) => v),
        backgroundColor: COLORS.primary,
        borderRadius: 6,
        maxBarThickness: 60,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onHover: pointerCursorOnHover,
      // Clicar numa barra navega para "Perfil do Estudante" já filtrada por
      // esse nível exato de tempo de estudo, para ver logo o subgrupo por
      // trás da taxa de aprovação (em vez de reajustar o filtro à mão lá).
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const level = parseInt(entries[elements[0].index][0], 10);
        goToPage("profile", { studytime: level });
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `${(ctx.parsed.y * 100).toFixed(1)}%` } },
      },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, max: 1, ticks: { callback: (v) => `${(v * 100).toFixed(0)}%` }, grid: { color: COLORS.border } },
      },
    },
  });
}
