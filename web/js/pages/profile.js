// ============================================================
// Página: Perfil do Estudante (explorador com filtros)
// Permite filtrar o dataset por sexo, acesso à internet, ambição de estudar
// mais e intervalo de tempo de estudo, e mostra KPIs comparados com a turma
// toda, distribuição de notas, dispersão faltas/nota, tendência G1->G2->G3,
// gráfico radar de hábitos e uma tabela detalhada por estudante.
// ============================================================

// Instâncias dos gráficos Chart.js — guardadas para poderem ser destruídas e
// recriadas sempre que os filtros mudam (evita sobreposição de gráficos).
let profileDistChart = null;
let profileScatterChart = null;
let profileTrendChart = null;
let profileRadarChart = null;
let overallStats = null; // estatísticas da turma toda, usadas para comparação nos KPIs

// checkbox toggle: seleção única => filtra; ambas ou nenhuma => sem filtro
function profileSingleValueFilter(boxes) {
  const checked = Array.from(boxes).filter((b) => b.checked);
  if (checked.length === 1) return checked[0].value;
  return null; // 0 ou 2 selecionadas = mostrar tudo
}

// Lê e normaliza o intervalo (slider duplo) de tempo de estudo, garantindo
// que o mínimo nunca é maior que o máximo (troca-os se necessário).
function profileSyncRange() {
  const studytimeMin = document.getElementById("studytime-min");
  const studytimeMax = document.getElementById("studytime-max");
  const rangeLabel = document.getElementById("studytime-range-label");
  let min = parseInt(studytimeMin.value, 10);
  let max = parseInt(studytimeMax.value, 10);
  if (min > max) { [min, max] = [max, min]; }
  rangeLabel.textContent = `${min}–${max}`;
  return { min, max };
}

// Extraída para o âmbito do módulo (em vez de viver só dentro do
// registerPage("profile", ...)) para poder ser chamada de fora — quer pelo
// próprio loader da página, quer pelo mecanismo de filtro externo abaixo
// (ver profileApplyExternalFilter), sempre que se navega para aqui a partir
// de um clique num gráfico de outra página já visitada.
async function profileApplyFilters() {
  const sexBoxes = document.querySelectorAll("#filter-sex input");
  const internetBoxes = document.querySelectorAll("#filter-internet input");
  const higherBoxes = document.querySelectorAll("#filter-higher input");
  const { min, max } = profileSyncRange();
  const filters = {
    sex: profileSingleValueFilter(sexBoxes),
    internet: profileSingleValueFilter(internetBoxes),
    higher: profileSingleValueFilter(higherBoxes),
    studytime_min: min,
    studytime_max: max,
    limit: 649, // suficientemente alto para cobrir todo o dataset
  };
  const data = await Api.students(filters);
  renderProfileResults(data);

  // Gráfico radar: usa os mesmos filtros, mas é um pedido à parte (o
  // backend já calcula as médias normalizadas do subgrupo, não é derivado
  // da lista de estudantes recebida acima) — ver Api.profileRadar.
  try {
    const radarData = await Api.profileRadar(filters);
    renderProfileRadar(radarData);
  } catch (err) {
    console.error(err);
  }
}

// Aplica um filtro vindo de outra página (ver goToPage/registerPageFilterHandler
// em main.js) — por agora só sabe pré-selecionar um nível exato de tempo de
// estudo (clique numa barra do gráfico "Taxa de aprovação por tempo de
// estudo" na Visão Geral), mas o mecanismo aceita mais campos no futuro sem
// precisar de mudar a assinatura da função.
function profileApplyExternalFilter(filter) {
  if (!filter) return;
  if (filter.studytime !== undefined) {
    const studytimeMin = document.getElementById("studytime-min");
    const studytimeMax = document.getElementById("studytime-max");
    // Define o mesmo valor em ambos os extremos do intervalo -> filtra por um nível exato.
    if (studytimeMin) studytimeMin.value = filter.studytime;
    if (studytimeMax) studytimeMax.value = filter.studytime;
  }
  profileApplyFilters();
}
registerPageFilterHandler("profile", profileApplyExternalFilter);

registerPage("profile", async () => {
  // Estatísticas gerais da turma, usadas como referência de comparação nos KPIs desta página.
  overallStats = await cached("stats", Api.stats);

  const sexBoxes = document.querySelectorAll("#filter-sex input");
  const internetBoxes = document.querySelectorAll("#filter-internet input");
  const higherBoxes = document.querySelectorAll("#filter-higher input");
  const studytimeMin = document.getElementById("studytime-min");
  const studytimeMax = document.getElementById("studytime-max");

  // Qualquer mudança nas checkboxes de filtro recalcula os resultados de imediato.
  [...sexBoxes, ...internetBoxes, ...higherBoxes].forEach((box) =>
    box.addEventListener("change", profileApplyFilters)
  );
  // 'change' (não 'input') — só refaz o pedido quando o utilizador larga o slider,
  // evitando dezenas de chamadas à API durante o arrasto.
  studytimeMin.addEventListener("change", profileApplyFilters);
  studytimeMax.addEventListener("change", profileApplyFilters);

  profileSyncRange();

  // Se a navegação até aqui trouxe um filtro pendente (clique num gráfico de
  // outra página, na primeira vez que se visita o Perfil do Estudante),
  // aplica-o em vez do estado por omissão — ver consumePendingNavFilter.
  const pending = consumePendingNavFilter("profile");
  if (pending) profileApplyExternalFilter(pending);
  else await profileApplyFilters();
});

function renderProfileResults(data) {
  const students = data.students;

  // 4 KPIs do subgrupo filtrado, cada um com a diferença (delta) face à turma toda.
  renderKpiCards("profile-kpis", [
    { label: t("profile_kpi_group_students"), value: data.n_students },
    {
      label: t("profile_kpi_group_avg_grade"),
      value: fmtNum(data.average_grade),
      delta: data.average_grade !== null ? `${(data.average_grade - data.overall_average_grade >= 0 ? "+" : "")}${fmtNum(data.average_grade - data.overall_average_grade)} ${t("profile_vs_overall_suffix")}` : null,
      deltaPositive: data.average_grade >= data.overall_average_grade,
    },
    {
      label: t("profile_kpi_group_pass_rate"),
      value: fmtPct(data.pass_rate),
      delta: data.pass_rate !== null ? `${((data.pass_rate - data.overall_pass_rate) * 100 >= 0 ? "+" : "")}${((data.pass_rate - data.overall_pass_rate) * 100).toFixed(1)} ${t("profile_pp_vs_overall_suffix")}` : null,
      deltaPositive: data.pass_rate >= data.overall_pass_rate,
    },
    {
      label: t("profile_kpi_group_avg_absences"),
      value: fmtNum(data.average_absences),
      delta: data.average_absences !== null ? `${(data.average_absences - data.overall_average_absences >= 0 ? "+" : "")}${fmtNum(data.average_absences - data.overall_average_absences)} ${t("profile_vs_overall_suffix")}` : null,
      deltaPositive: data.average_absences <= data.overall_average_absences, // menos faltas é melhor -> sinal invertido
    },
  ]);

  renderProfileDistribution(students);
  renderProfileScatter(students);
  renderProfileTrend(students);
  renderProfileTable(students);
}

// Regressão linear simples por mínimos quadrados — usada aqui só para 3
// pontos (G1, G2, G3), por isso resolvida diretamente em JS em vez de pedir
// ao backend (a mesma fórmula usada em simple_linear_regression no backend,
// mas essa opera sobre milhares de linhas do dataset, não sobre 3 médias).
function linearTrend(xs, ys) {
  const n = xs.length;
  const sumX = xs.reduce((a, b) => a + b, 0);
  const sumY = ys.reduce((a, b) => a + b, 0);
  const sumXY = xs.reduce((acc, x, i) => acc + x * ys[i], 0);
  const sumXX = xs.reduce((acc, x) => acc + x * x, 0);
  const denom = n * sumXX - sumX * sumX;
  if (denom === 0) return { slope: 0, intercept: sumY / n }; // evita divisão por zero (xs todos iguais)
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

// Evolução das notas do grupo filtrado: média de G1/G2/G3 ligadas por uma
// linha, mais um 4º ponto tracejado — não é uma previsão do modelo de ML
// (esse já existe no Simulador), é só a reta de tendência dos 3 valores
// médios em si, extrapolada um período à frente, para se perceber se o
// grupo está, em média, a melhorar ou a piorar ao longo do ano.
function renderProfileTrend(students) {
  const ctx = document.getElementById("chart-profile-trend");
  const summary = document.getElementById("profile-trend-summary");
  if (!ctx) return;

  if (students.length === 0) {
    // Sem estudantes no grupo: destrói qualquer gráfico anterior e mostra mensagem.
    if (profileTrendChart) { profileTrendChart.destroy(); profileTrendChart = null; }
    if (summary) summary.textContent = t("profile_trend_no_students");
    return;
  }

  // Calcula a média de cada período (G1, G2, G3) para o grupo filtrado.
  const avgG1 = students.reduce((a, s) => a + s.G1, 0) / students.length;
  const avgG2 = students.reduce((a, s) => a + s.G2, 0) / students.length;
  const avgG3 = students.reduce((a, s) => a + s.G3, 0) / students.length;
  const { slope, intercept } = linearTrend([1, 2, 3], [avgG1, avgG2, avgG3]);
  // Projeta o 4º período (x=4), garantindo que fica dentro da escala válida (0-20).
  const projected = Math.max(0, Math.min(20, intercept + slope * 4));

  if (profileTrendChart) profileTrendChart.destroy();
  profileTrendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [t("profile_period_1"), t("profile_period_2"), t("profile_period_3"), t("profile_period_projection")],
      datasets: [{
        label: t("profile_kpi_group_avg_grade"),
        data: [avgG1, avgG2, avgG3, projected],
        borderColor: COLORS.primary,
        backgroundColor: COLORS.primaryLighter,
        pointBackgroundColor: (c) => (c.dataIndex === 3 ? COLORS.muted : COLORS.primary),
        pointRadius: 5,
        tension: 0,
        fill: false,
        // Só o último troço (3º período -> projeção) fica tracejado, para
        // se distinguir logo o que é medido do que é extrapolado.
        segment: {
          borderDash: (c) => (c.p1DataIndex === 3 ? [6, 5] : undefined),
        },
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { min: 0, max: 20, title: { display: true, text: t("profile_grade_scale_axis") }, grid: { color: COLORS.border } },
      },
    },
  });

  if (summary) {
    // Classifica a tendência em 3 categorias, com uma margem morta (-0.05 a 0.05) para "estável".
    const direction = slope > 0.05 ? t("trend_improving") : slope < -0.05 ? t("trend_worsening") : t("trend_stable");
    summary.innerHTML = t("profile_trend_summary")
      .replace("{direction}", direction)
      .replace("{sign}", slope >= 0 ? "+" : "")
      .replace("{slope}", slope.toFixed(2))
      .replace("{projected}", projected.toFixed(1));
  }
}

function renderProfileDistribution(students) {
  const ctx = document.getElementById("chart-profile-distribution");
  const bins = Array(11).fill(0); // 0-20 em passos de ~2 (11 intervalos)
  students.forEach((s) => {
    // Cada estudante cai num intervalo de largura 2, limitado ao último bin (índice 10).
    const idx = Math.min(10, Math.floor(s.G3 / 2));
    bins[idx]++;
  });
  const labels = bins.map((_, i) => `${i * 2}-${i * 2 + 2}`);

  if (profileDistChart) profileDistChart.destroy();
  profileDistChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ data: bins, backgroundColor: COLORS.primary, borderRadius: 4, maxBarThickness: 30 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, grid: { color: COLORS.border } },
      },
    },
  });
}

function renderProfileScatter(students) {
  const ctx = document.getElementById("chart-profile-scatter");
  // Separa os pontos em 2 séries (aprovado/reprovado) para cores diferentes.
  const aprovados = students.filter((s) => s.aprovado === 1).map((s) => ({ x: s.absences, y: s.G3 }));
  const reprovados = students.filter((s) => s.aprovado === 0).map((s) => ({ x: s.absences, y: s.G3 }));

  if (profileScatterChart) profileScatterChart.destroy();
  profileScatterChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        { label: t("chart_pass_label"), data: aprovados, backgroundColor: COLORS.positive },
        { label: t("chart_fail_label"), data: reprovados, backgroundColor: COLORS.negative },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: { title: { display: true, text: habitLabel("absences") }, grid: { color: COLORS.border } },
        y: { title: { display: true, text: habitLabel("G3") }, grid: { color: COLORS.border } },
      },
    },
  });
}

function renderProfileTable(students) {
  const tbody = document.querySelector("#profile-table tbody");
  // Limitado às primeiras 100 linhas (segurança de desempenho — grupos grandes não travam a tabela).
  const rows = students.slice(0, 100).map((s) => `
    <tr>
      <td>${s.student_id}</td>
      <td>${s.sex}</td>
      <td>${s.age}</td>
      <td>${s.studytime}</td>
      <td>${s.absences}</td>
      <td>${s.failures}</td>
      <td>${s.internet}</td>
      <td>${s.G1}</td>
      <td>${s.G2}</td>
      <td>${s.G3}</td>
      <td><span class="pill ${s.aprovado ? "pill-yes" : "pill-no"}">${s.aprovado ? t("cat_yes") : t("cat_no")}</span></td>
      <td>${progressBadgeHtml(s.progress_badge)}</td>
      <td>${percentileCellHtml(s)}</td>
      <td><button type="button" class="table-note-btn" data-note-student="${s.student_id}">${escapeHtml(t("table_add_note_btn"))}</button></td>
    </tr>
  `).join("");
  tbody.innerHTML = rows || `<tr><td colspan="14">${escapeHtml(t("profile_table_empty"))}</td></tr>`;
  // Comentários (ver openStudentNotesModal em main.js): cada linha abre o
  // modal de comentários do respetivo estudante, sem contexto de alerta
  // (o utilizador está aqui a escrever livremente sobre o estudante).
  tbody.querySelectorAll("[data-note-student]").forEach((btn) => {
    btn.addEventListener("click", () => openStudentNotesModal(btn.dataset.noteStudent));
  });
}

// Selo de progresso (Ideia 7): direção da evolução G1 -> G2 -> G3 (ver
// progress_badge em src/data_processing.py) — reaproveita as classes .badge
// já usadas noutras páginas (ex.: validação do Simulador), sem CSS novo.
function progressBadgeHtml(badge) {
  const cls = badge === "Em Ascensão" ? "badge-positive" : badge === "Queda a Vigiar" ? "badge-negative" : "badge-neutral";
  return `<span class="badge ${cls}">${badge || "–"}</span>`;
}

// Gráfico radar (Ideia 4): perfil de hábitos do grupo filtrado vs a turma
// toda, sobre variáveis normalizadas 0-100 (ver radar_profile no backend).
function renderProfileRadar(data) {
  const ctx = document.getElementById("chart-profile-radar");
  if (!ctx) return;

  if (profileRadarChart) profileRadarChart.destroy();
  profileRadarChart = new Chart(ctx, {
    type: "radar",
    data: {
      labels: data.labels,
      datasets: [
        {
          // Série do subgrupo filtrado, preenchida com cor principal e transparência.
          label: t("radar_filtered_group_label").replace("{n}", data.n_subgroup),
          data: data.subgroup_values,
          borderColor: COLORS.primary,
          backgroundColor: COLORS.primaryLighter + "80",
          pointBackgroundColor: COLORS.primary,
        },
        {
          // Série de referência (turma toda), sem preenchimento e com contorno tracejado.
          label: t("radar_whole_class_label"),
          data: data.overall_values,
          borderColor: COLORS.muted,
          backgroundColor: "transparent",
          pointBackgroundColor: COLORS.muted,
          borderDash: [5, 4],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        r: { min: 0, max: 100, ticks: { display: false }, grid: { color: COLORS.border } },
      },
    },
  });
}

// Percentil da nota final (G3) face à TURMA TODA (não só ao subgrupo
// filtrado — ver o comentário em /students no backend), com uma mini-barra
// visual e um resumo dos 3 percentis (nota/estudo/faltas) no tooltip, para
// não precisar de mais uma coluna/painel só para isso.
function percentileCellHtml(s) {
  const pct = s.percentile_g3;
  const tooltip = t("percentile_tooltip").replace("{g3}", pct).replace("{st}", s.percentile_studytime).replace("{abs}", s.percentile_absences);
  return `
    <div class="percentile-cell" title="${escapeAttr(tooltip)}">
      <span class="percentile-label">${Math.round(pct)}º</span>
      <span class="percentile-bar-track"><span class="percentile-bar-fill" style="width:${pct}%;"></span></span>
    </div>
  `;
}
