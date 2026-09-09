// ============================================================
// Página: Previsão de Notas — Simulador "e se"
// Qualquer campo do formulário recalcula a previsão sozinho (com um
// pequeno atraso, para não disparar um pedido a cada pixel arrastado num
// slider) — reaproveita o mesmo endpoint /predict que já preenche o que
// faltar com valores medianos/mais frequentes do dataset (ver get_defaults
// no backend), por isso não precisou de nenhum endpoint novo. O botão
// "Recalcular agora" fica só como atalho manual (ex.: teclado/acessibilidade).
// ============================================================

let predictionDebounceTimer = null; // temporizador do debounce dos campos "ao vivo"
let lastPredictedGrade = null; // última nota prevista (para calcular deltas visuais)
let lastPredictedProba = null; // última probabilidade de aprovação (idem)
let lastPredictionPayload = null; // últimos hábitos enviados (reutilizados ao guardar snapshot/cenário)
let lastPredictionResult = null; // último resultado completo da API (reutilizado ao guardar cenário)
let accuracyTrendChart = null; // instância do gráfico de precisão ao longo do tempo

// Cenários lado a lado: até 3 configurações do simulador guardadas em
// memória (não persiste na BD nem sobrevive a um refresh — é um bloco de
// rascunho para comparar variações "e se" durante a mesma sessão, ao
// contrário da Comparação Antes/Depois, que é guardada na BD para
// validação a médio prazo com a nota real).
let savedScenarios = [];
let scenarioIdCounter = 0; // gera ids únicos para os cenários guardados nesta sessão
const MAX_SCENARIOS = 3;
// Rótulos legíveis para os campos mostrados na tabela de comparação de cenários.
const SCENARIO_FIELD_LABELS = {
  studytime: "Tempo de estudo",
  absences: "Nº de faltas",
  failures: "Reprovações anteriores",
  goout: "Sair com amigos",
  freetime: "Tempo livre",
  Dalc: "Álcool (dias úteis)",
  Walc: "Álcool (fim de semana)",
  internet: "Internet em casa",
  higher: "Deseja estudo superior",
  schoolsup: "Apoio educativo extra",
  romantic: "Relação amorosa",
};

registerPage("prediction", async () => {
  // Ligar os "outputs" dos sliders ao valor atual
  ["goout", "freetime", "dalc", "walc"].forEach((id) => {
    const input = document.getElementById(`f-${id}`);
    const output = document.getElementById(`f-${id}-out`);
    input.addEventListener("input", () => (output.textContent = input.value));
  });

  document.getElementById("prediction-save-btn").addEventListener("click", savePredictionSnapshot);
  document.getElementById("scenario-save-btn").addEventListener("click", saveScenarioForComparison);
  document.getElementById("scenario-clear-btn").addEventListener("click", clearScenarios);
  document.getElementById("scenario-export-btn").addEventListener("click", exportScenariosJson);
  document.getElementById("scenario-import-input").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) importScenariosFromFile(file);
    e.target.value = ""; // limpa a seleção, para poder importar o mesmo ficheiro outra vez se necessário
  });
  // Carrega em paralelo o histórico de previsões, o resumo de validação e a evolução de precisão.
  await Promise.all([loadPredictionHistory(), loadValidationSummary(), loadAccuracyOverTime()]);

  // Simulador: cada campo dispara um recálculo automático — "input" nos
  // sliders/número (feedback imediato ao arrastar) e "change" nos
  // select/checkboxes (só faz sentido recalcular quando a escolha fecha).
  const liveFields = [
    ["f-studytime", "change"], ["f-absences", "input"], ["f-failures", "change"],
    ["f-goout", "input"], ["f-freetime", "input"], ["f-dalc", "input"], ["f-walc", "input"],
    ["f-internet", "change"], ["f-higher", "change"], ["f-schoolsup", "change"], ["f-romantic", "change"],
  ];
  liveFields.forEach(([id, evt]) => {
    document.getElementById(id).addEventListener(evt, scheduleRunPrediction);
  });

  const form = document.getElementById("prediction-form");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    runPrediction();
  });

  // Primeira previsão assim que a página abre, já com os valores por
  // omissão do formulário — o simulador mostra logo um resultado, em vez de
  // obrigar a um primeiro clique só para "ativar".
  runPrediction();
});

// Agenda um recálculo com atraso (debounce de 350ms), mostrando um indicador "A atualizar…" entretanto.
function scheduleRunPrediction() {
  const hint = document.getElementById("prediction-live-status");
  if (hint) { hint.textContent = "A atualizar…"; hint.classList.add("visible"); }
  clearTimeout(predictionDebounceTimer);
  predictionDebounceTimer = setTimeout(runPrediction, 350);
}

// Lê todos os campos do formulário e monta o payload para o endpoint /predict.
function collectPredictionPayload() {
  return {
    studytime: parseInt(document.getElementById("f-studytime").value, 10),
    absences: parseInt(document.getElementById("f-absences").value, 10),
    failures: parseInt(document.getElementById("f-failures").value, 10),
    goout: parseInt(document.getElementById("f-goout").value, 10),
    freetime: parseInt(document.getElementById("f-freetime").value, 10),
    Dalc: parseInt(document.getElementById("f-dalc").value, 10),
    Walc: parseInt(document.getElementById("f-walc").value, 10),
    internet: document.getElementById("f-internet").checked ? "yes" : "no",
    higher: document.getElementById("f-higher").checked ? "yes" : "no",
    schoolsup: document.getElementById("f-schoolsup").checked ? "yes" : "no",
    romantic: document.getElementById("f-romantic").checked ? "yes" : "no",
  };
}

async function runPrediction() {
  clearTimeout(predictionDebounceTimer);
  const payload = collectPredictionPayload();
  const hint = document.getElementById("prediction-live-status");

  try {
    const result = await Api.predict(payload);
    displayPredictionResult(result, payload);
    if (hint) hint.classList.remove("visible");

    // A explicação e a comparação com pares são extras sobre a mesma
    // previsão — se uma falhar (ex.: só essa chamada teve um problema
    // pontual), não deve impedir o resto do simulador de mostrar o
    // resultado principal.
    Api.predictExplain(payload).then(renderExplainCard).catch((err) => console.error(err));
    runPeerComparison(payload, result).catch((err) => console.error(err));
    Api.examWeekChecklist(payload).then(renderExamWeekChecklist).catch((err) => console.error(err));
  } catch (err) {
    console.error(err);
    // Um recálculo automático que falhe (ex.: rede instável a meio de um
    // arrasto) não deve interromper com um alerta — só se ainda não houver
    // nenhum resultado no ecrã é que se mostra o aviso, uma vez.
    if (hint) { hint.textContent = "Não foi possível atualizar a previsão."; hint.classList.add("visible"); }
    if (lastPredictedGrade === null) {
      document.getElementById("prediction-placeholder").classList.remove("hidden");
    }
  }
}

function displayPredictionResult(result, payload) {
  document.getElementById("prediction-placeholder").classList.add("hidden");
  const resultsBox = document.getElementById("prediction-results");
  resultsBox.classList.remove("hidden");
  lastPredictionPayload = payload;
  lastPredictionResult = result;

  // Medidor da nota prevista, colorido conforme a faixa de desempenho.
  const grade = result.nota_prevista_habitos.predicted_grade;
  const gradePct = (grade / 20) * 100;
  const gradeColor = grade >= 14 ? COLORS.positive : grade >= 10 ? COLORS.primary : COLORS.negative;
  setGauge("gauge-grade", "gauge-grade-value", gradePct, gradeColor);
  animateNumberText(document.getElementById("gauge-grade-value"), fmtNum(grade, 1), 500);
  renderPredictionDelta("gauge-grade-delta", grade, lastPredictedGrade, 1, "valores");
  flashGaugeOnChange("gauge-grade", grade, lastPredictedGrade);
  lastPredictedGrade = grade;

  // Margem de erro típica do modelo (MAE medido no conjunto de teste, ver
  // get_model_mae no backend) — mostra a previsão como "13.5 ± 2.0" em vez
  // de um único número, para não parecer mais exata do que realmente é.
  const marginNote = document.getElementById("gauge-grade-margin");
  if (marginNote) {
    const mae = result.nota_prevista_habitos.mae;
    marginNote.textContent = mae != null
      ? `Margem de erro típica do modelo: ± ${fmtNum(mae, 1)} valores`
      : "";
  }

  // Medidor da probabilidade de aprovação, verde/vermelho consoante o veredito previsto.
  const proba = result.aprovacao.probabilidade_aprovacao * 100;
  const probaColor = result.aprovacao.aprovado_previsto ? COLORS.positive : COLORS.negative;
  setGauge("gauge-proba", "gauge-proba-value", proba, probaColor);
  animateNumberText(document.getElementById("gauge-proba-value"), fmtNum(proba, 0), 500);
  renderPredictionDelta("gauge-proba-delta", proba, lastPredictedProba, 0, "pontos");
  flashGaugeOnChange("gauge-proba", proba, lastPredictedProba);
  lastPredictedProba = proba;

  renderRecommendations(payload).catch((err) => console.error(err));
}

// Simulador "vivo": um breve pulso colorido no anel do gauge sempre que o
// valor sobe ou desce desde o último ajuste — verde a subir, vermelho a
// descer — para o simulador reagir visualmente a cada mudança, não só
// mudar um número. Na primeiríssima previsão (sem nada para comparar) não
// há pulso, só o valor a aparecer.
function flashGaugeOnChange(gaugeElementId, current, previous) {
  const gauge = document.getElementById(gaugeElementId);
  if (!gauge || previous === null || previous === undefined) return;
  const diff = current - previous;
  if (Math.abs(diff) < 0.01) return; // variação insignificante -> não vale a pena animar
  gauge.classList.remove("gauge-flash-up", "gauge-flash-down");
  // Força o reflow para reiniciar a animação mesmo que a classe anterior já
  // estivesse lá (ex.: dois ajustes seguidos no mesmo sentido).
  void gauge.offsetWidth;
  gauge.classList.add(diff > 0 ? "gauge-flash-up" : "gauge-flash-down");
  setTimeout(() => gauge.classList.remove("gauge-flash-up", "gauge-flash-down"), 650);
}

// Mostra quanto a previsão mudou desde o último recálculo (ex.: "+0.8
// valores desde a última alteração") — é isto que torna o simulador
// percetível: cada ajuste num controlo mostra logo o impacto, não só o
// número final. Na primeíssima previsão (sem nada para comparar) não
// mostra nada.
function renderPredictionDelta(elementId, current, previous, decimals, unitLabel) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (previous === null || previous === undefined) {
    el.textContent = "";
    el.className = "kpi-delta";
    return;
  }
  const diff = current - previous;
  if (Math.abs(diff) < Math.pow(10, -decimals) / 2) {
    // Diferença abaixo da precisão mostrada (ex.: <0.05 com 1 casa decimal) -> considera-se "sem alteração".
    el.textContent = "Sem alteração desde o último ajuste";
    el.className = "kpi-delta";
    return;
  }
  const sign = diff > 0 ? "+" : "";
  el.textContent = `${sign}${fmtNum(diff, decimals)} ${unitLabel} desde o último ajuste`;
  el.className = `kpi-delta ${diff > 0 ? "positive" : "negative"}`;
}

// Rótulos para valores que, em bruto, não dizem nada a quem lê ("yes"/"no",
// ou o nível 1-4 do tempo de estudo) — os mesmos textos já usados no
// formulário do simulador, para não haver duas traduções diferentes do
// mesmo valor em sítios diferentes da página.
const EXPLAIN_YES_NO_FIELDS = ["internet", "higher", "schoolsup"];
const EXPLAIN_STUDYTIME_LABELS = { 1: "< 2h/semana", 2: "2-5h/semana", 3: "5-10h/semana", 4: "> 10h/semana" };

// Converte um valor bruto (feature/value) num texto legível, consoante o tipo de campo.
function formatExplainValue(feature, value) {
  if (EXPLAIN_YES_NO_FIELDS.includes(feature)) return value === "yes" ? "Sim" : "Não";
  if (feature === "studytime") return EXPLAIN_STUDYTIME_LABELS[Math.round(value)] || value;
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return Number.isInteger(num) ? String(num) : num.toFixed(1);
}

// Explicabilidade por estudante (ver explain_prediction no backend): ao
// contrário de /feature-importance (a mesma lista para toda a gente), isto
// mostra o efeito real, para OS valores que este estudante indicou, de cada
// fator — não é um "top 10 geral do modelo", é "o que está a pesar na TUA
// previsão agora mesmo".
function renderExplainCard(result) {
  const list = document.getElementById("prediction-explain-list");
  if (!list) return;
  const contributions = result.contributions || [];
  if (contributions.length === 0) {
    list.innerHTML = `<li class="explain-item-neutral">Os valores indicados estão perto do típico do dataset — nenhum fator isolado se destaca nesta previsão.</li>`;
    return;
  }
  // Mostra só os 5 fatores com maior impacto (já vêm ordenados por magnitude a partir do backend).
  list.innerHTML = contributions.slice(0, 5).map((c) => {
    const helping = c.impact > 0;
    const studentVal = formatExplainValue(c.feature, c.student_value);
    const typicalVal = formatExplainValue(c.feature, c.typical_value);
    const sign = helping ? "+" : "";
    return `
      <li class="explain-item ${helping ? "positive" : "negative"}">
        <span class="explain-item-label">${c.label}</span>
        <span class="explain-item-detail">O teu valor (${studentVal}) vs. típico do dataset (${typicalVal})</span>
        <span class="explain-item-impact">${sign}${fmtNum(c.impact, 2)} valores</span>
      </li>
    `;
  }).join("");
}

// Comparação com pares reais: em vez de um benchmark inventado, usa
// diretamente estudantes reais do dataset com o mesmo nível de tempo de
// estudo (/students já calcula estas médias sobre o subgrupo filtrado,
// antes de qualquer "limit" — por isso "limit: 1" chega, só interessam os
// agregados, não a lista de estudantes).
async function runPeerComparison(payload, result) {
  const peers = await Api.students({
    studytime_min: payload.studytime,
    studytime_max: payload.studytime,
    limit: 1,
  });
  renderPeerComparison(peers, result, payload);
}

function renderPeerComparison(peers, result, payload) {
  const note = document.getElementById("peer-compare-note");
  if (!note) return;

  if (!peers.n_students) {
    // Sem nenhum estudante real com este nível de estudo -> não há grupo para comparar.
    document.getElementById("peer-avg-grade").textContent = "–";
    document.getElementById("peer-pass-rate").textContent = "–";
    note.textContent = "Não há estudantes reais suficientes no dataset com este perfil de estudo para comparar.";
    return;
  }

  const grade = result.nota_prevista_habitos.predicted_grade;
  const proba = result.aprovacao.probabilidade_aprovacao * 100;

  document.getElementById("peer-avg-grade").textContent = fmtNum(peers.average_grade, 1);
  renderPeerDiff("peer-avg-grade-diff", grade, peers.average_grade, 1, "valores");

  document.getElementById("peer-pass-rate").textContent = fmtPct(peers.pass_rate, 0);
  renderPeerDiff("peer-pass-rate-diff", proba, peers.pass_rate * 100, 0, "pontos");

  const studytimeLabel = EXPLAIN_STUDYTIME_LABELS[payload.studytime] || payload.studytime;
  note.textContent = `Com base em ${peers.n_students} estudante${peers.n_students === 1 ? "" : "s"} reais do dataset com tempo de estudo "${studytimeLabel}".`;
}

// Mostra a diferença entre a previsão do utilizador e a média do grupo de pares, com sinal e cor.
function renderPeerDiff(elementId, mine, group, decimals, unitLabel) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const diff = mine - group;
  const sign = diff > 0 ? "+" : "";
  el.textContent = `${sign}${fmtNum(diff, decimals)} ${unitLabel} face à tua previsão`;
  el.className = `peer-compare-diff ${diff >= 0 ? "positive" : "negative"}`;
}

// Dica de tempo de estudo, calibrada por já ter reprovado ou não: o
// coeficiente "geral" (+0,91) esconde que o efeito é bem mais fraco (e
// deixa de ser estatisticamente significativo) em quem já reprovou antes
// — ver studytime_regression_no_failures/with_failures no backend
// (/statistical-tests). Sem esta calibração, a dica prometeria o mesmo
// ganho a todos, o que a análise aos dados reais não sustenta.
async function buildStudytimeTip(payload) {
  const tests = await cached("statisticalTests", Api.statisticalTests);
  const hasFailures = payload.failures > 0;
  const reg = hasFailures
    ? tests.studytime_regression_with_failures
    : tests.studytime_regression_no_failures;

  if (!reg) {
    return "Aumentar o tempo de estudo semanal está associado, em média, a notas mais altas.";
  }

  if (hasFailures) {
    return (
      `Aumentar o tempo de estudo semanal costuma ajudar, mas com reprovações anteriores o ` +
      `efeito medido nos dados é bem mais fraco (+${fmtNum(reg.coeficiente, 2)} valores por nível` +
      `${reg.significativo_5pct ? "" : ", sem significância estatística neste grupo mais pequeno"}) — ` +
      `vale a pena combinar com apoio adicional (explicações, acompanhamento pedagógico), não só mais tempo sozinho.`
    );
  }

  return (
    `Aumentar o tempo de estudo semanal está associado, em média, a notas mais altas ` +
    `(+${fmtNum(reg.coeficiente, 2)} valores por nível, estatisticamente significativo).`
  );
}

async function renderRecommendations(payload) {
  const stats = await cached("stats", Api.stats);
  const tips = [];

  // Cada condição adiciona uma dica textual só se for relevante para os valores atuais do formulário.
  if (payload.studytime < 3) {
    tips.push(await buildStudytimeTip(payload));
  }
  if (payload.failures > 0) {
    tips.push("Reprovações anteriores têm o maior impacto negativo identificado na análise (~-1,98 valores por reprovação).");
  }
  if (payload.absences > stats.average_absences) {
    tips.push("O número de faltas está acima da média do grupo — reduzir faltas está associado a melhores notas.");
  }
  if (payload.Dalc > 2 || payload.Walc > 2) {
    tips.push("Um consumo de álcool mais elevado está associado a notas mais baixas na análise estatística realizada.");
  }
  if (payload.internet === "no") {
    tips.push("Estudantes com acesso a internet em casa têm, em média, notas superiores (diferença estatisticamente significativa).");
  }
  if (tips.length === 0) {
    // Nenhuma condição disparou: hábitos já estão alinhados com o que a análise considera positivo.
    tips.push("Os hábitos indicados estão alinhados com os fatores associados a bom desempenho nesta análise.");
  }

  const list = document.getElementById("recommendations-list");
  list.innerHTML = tips.map((t) => `<li>${t}</li>`).join("");
}

// ------------------------------------------------------------
// Comparação Antes/Depois: guarda a previsão atual como ponto de partida
// e, mais tarde, permite registar a nota REAL obtida — o backend recalcula
// a previsão a partir dos hábitos enviados (não confia num número já
// calculado no browser), a mesma garantia que /predict e /predict/explain
// já dão.
// ------------------------------------------------------------
const PREDICTION_STATUS_LABELS = {
  melhor_que_previsto: "Melhor que previsto",
  pior_que_previsto: "Pior que previsto",
  como_previsto: "Como previsto",
  pendente: "Pendente",
};

// Formata uma data ISO para o formato curto português (ex.: "05 ago. 2026").
function fmtSnapshotDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString("pt-PT", { day: "2-digit", month: "short", year: "numeric" });
}

async function savePredictionSnapshot() {
  const btn = document.getElementById("prediction-save-btn");
  const messageBox = document.getElementById("prediction-save-message");

  if (!lastPredictionPayload) {
    messageBox.classList.remove("hidden");
    messageBox.textContent = "Ainda não há nenhuma previsão calculada para guardar.";
    return;
  }

  const label = document.getElementById("prediction-save-label").value.trim();
  const originalText = btn.textContent;
  btn.textContent = "A guardar…";
  btn.disabled = true;

  try {
    await Api.savePredictionSnapshot({ ...lastPredictionPayload, label });
    messageBox.classList.remove("hidden");
    messageBox.textContent = "Previsão guardada. Regista a nota real mais tarde no histórico abaixo.";
    document.getElementById("prediction-save-label").value = "";
    await loadPredictionHistory();
    showToast("Previsão guardada com sucesso.", { type: "success" });
  } catch (err) {
    console.error(err);
    messageBox.classList.remove("hidden");
    messageBox.textContent = err.message || "Não foi possível guardar esta previsão.";
    showToast("Não foi possível guardar esta previsão.", { type: "error" });
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

async function loadPredictionHistory() {
  const tbody = document.querySelector("#prediction-history-table tbody");
  try {
    const data = await Api.predictionSnapshots();
    renderPredictionHistory(tbody, data.snapshots);
  } catch (err) {
    console.error(err);
    tbody.innerHTML = `<tr><td colspan="6">Não foi possível carregar o histórico.</td></tr>`;
  }
}

function renderPredictionHistory(tbody, snapshots) {
  if (!snapshots || snapshots.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6">Ainda não guardaste nenhuma previsão.</td></tr>`;
    return;
  }

  tbody.innerHTML = snapshots.map((s) => {
    // Classe CSS de cor conforme o status da previsão (melhor/pior/como previsto/pendente).
    const statusClass = {
      melhor_que_previsto: "status-melhor",
      pior_que_previsto: "status-pior",
      como_previsto: "status-igual",
      pendente: "status-pendente",
    }[s.status];
    const badge = `<span class="prediction-status-badge ${statusClass}">${PREDICTION_STATUS_LABELS[s.status]}</span>`;

    // Se ainda não há nota real registada, mostra um pequeno formulário inline em vez do valor.
    const actualCell = s.actual_grade !== null
      ? fmtNum(s.actual_grade, 1)
      : `
        <div class="prediction-actual-input-row">
          <input type="number" min="0" max="20" step="0.1" class="prediction-actual-input" data-snapshot-id="${s.id}" placeholder="0-20">
          <button type="button" class="btn-small" data-record-actual="${s.id}">Registar</button>
        </div>
      `;

    return `
      <tr>
        <td>${fmtSnapshotDate(s.created_at)}</td>
        <td>${s.label ? escapeHtml(s.label) : "–"}</td>
        <td>${fmtNum(s.predicted_grade, 1)}</td>
        <td>${actualCell}</td>
        <td>${badge}</td>
        <td><button type="button" class="btn-small btn-small-danger" data-delete-snapshot="${s.id}">Remover</button></td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("[data-record-actual]").forEach((btn) => {
    btn.addEventListener("click", () => recordSnapshotActual(btn.dataset.recordActual));
  });
  tbody.querySelectorAll("[data-delete-snapshot]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!(await appConfirm("Remover esta previsão guardada? Fica guardada na Lixeira."))) return;
      await Api.deletePredictionSnapshot(btn.dataset.deleteSnapshot);
      // Recarrega os 3 painéis dependentes do histórico após remover um registo.
      await Promise.all([loadPredictionHistory(), loadValidationSummary(), loadAccuracyOverTime()]);
    });
  });
}

async function recordSnapshotActual(snapshotId) {
  const input = document.querySelector(`.prediction-actual-input[data-snapshot-id="${snapshotId}"]`);
  if (!input) return;
  const value = parseFloat(input.value);
  if (Number.isNaN(value) || value < 0 || value > 20) {
    input.classList.add("input-error");
    return;
  }
  // Mede a posição ANTES de recarregar o histórico — a linha da tabela onde
  // este campo vive vai ser substituída pelo re-render (ver
  // renderPredictionHistory), por isso o elemento original deixa de estar
  // no ecrã por essa altura.
  const anchorRect = (input.closest("tr") || input).getBoundingClientRect();
  const anchorX = anchorRect.left + anchorRect.width / 2;
  const anchorY = anchorRect.top + anchorRect.height / 2;

  try {
    const updated = await Api.recordPredictionSnapshotActual(snapshotId, value);
    await Promise.all([loadPredictionHistory(), loadValidationSummary(), loadAccuracyOverTime()]);

    // Micro-gamificação: uma pequena celebração quando o resultado real veio
    // melhor do que o modelo tinha previsto — não é preciso um sistema de
    // conquistas a sério, só reconhecer visualmente uma boa surpresa.
    if (updated && updated.status === "melhor_que_previsto") {
      celebrateAt(anchorX, anchorY);
      showToast("Melhor do que o previsto! A nota real superou a previsão do modelo.", { type: "success" });
    } else {
      showToast("Nota real registada.", { type: "success" });
    }
  } catch (err) {
    console.error(err);
    input.classList.add("input-error");
    showToast("Não foi possível registar a nota real.", { type: "error" });
  }
}

// Validação do modelo com dados reais deste utilizador (ver
// get_validation_summary no backend) — complementa o MAE "de fábrica"
// (calculado uma vez no conjunto de teste do treino) com o erro medido em
// previsões e resultados que realmente aconteceram para quem está a usar a
// app agora.
function renderValidationSummary(summary) {
  const wrap = document.getElementById("validation-summary-wrap");
  if (!wrap) return;

  if (!summary || !summary.has_data) {
    wrap.innerHTML = `<p class="card-subtitle">${summary ? escapeHtml(summary.message) : "Não foi possível carregar a validação do modelo."}</p>`;
    return;
  }

  const counts = summary.status_counts || {};
  wrap.innerHTML = `
    <div class="validation-summary-box">
      <div class="validation-summary-stat">
        <span class="validation-summary-value">${fmtNum(summary.real_world_mae, 2)}</span>
        <span class="validation-summary-label">Erro médio real (${summary.n_validated} previsão${summary.n_validated === 1 ? "" : "ões"} validada${summary.n_validated === 1 ? "" : "s"})</span>
      </div>
      <div class="validation-summary-breakdown">
        <span class="badge badge-positive">${counts.melhor_que_previsto || 0} melhor que previsto</span>
        <span class="badge badge-neutral">${counts.como_previsto || 0} como previsto</span>
        <span class="badge badge-negative">${counts.pior_que_previsto || 0} pior que previsto</span>
      </div>
    </div>
  `;
}

async function loadValidationSummary() {
  try {
    const summary = await Api.predictionValidation();
    renderValidationSummary(summary);
  } catch (err) {
    console.error(err);
    renderValidationSummary(null);
  }
}

// Ideia 5: acompanhar a precisão do modelo ao longo do tempo — em vez de um
// único número agregado "de sempre" (ver renderValidationSummary), mostra o
// erro médio (MAE) acumulado à medida que mais notas reais vão sendo
// registadas, para se perceber se a precisão do modelo se mantém estável
// (ver get_accuracy_over_time no backend). Só aparece com pelo menos 2
// previsões validadas — com uma só não há "tendência" nenhuma para mostrar.
function renderAccuracyOverTime(accuracy) {
  const wrap = document.getElementById("accuracy-trend-wrap");
  const canvas = document.getElementById("accuracy-trend-chart");
  if (!wrap || !canvas) return;

  if (!accuracy || !accuracy.has_data) {
    // Sem dados suficientes: esconde a secção e destrói qualquer gráfico anterior.
    wrap.classList.add("hidden");
    if (accuracyTrendChart) { accuracyTrendChart.destroy(); accuracyTrendChart = null; }
    return;
  }

  wrap.classList.remove("hidden");
  const points = accuracy.points;
  // Converte cada data de registo para o formato local português; se a data for inválida, usa o valor bruto.
  const labels = points.map((p) => {
    const date = new Date(p.recorded_at);
    return Number.isNaN(date.getTime()) ? p.recorded_at : date.toLocaleDateString("pt-PT");
  });

  if (accuracyTrendChart) accuracyTrendChart.destroy();
  accuracyTrendChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Erro médio acumulado (MAE)",
        data: points.map((p) => p.cumulative_mae),
        borderColor: COLORS.primary,
        backgroundColor: COLORS.primaryLighter,
        pointRadius: 4,
        tension: 0.15,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          // Mostra também a previsão e o valor real desse ponto específico, além do MAE acumulado.
          callbacks: {
            afterLabel: (ctx) => {
              const p = points[ctx.dataIndex];
              return `Previsão: ${fmtNum(p.predicted_grade)} · Real: ${fmtNum(p.actual_grade)}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, title: { display: true, text: "MAE (valores)" }, grid: { color: COLORS.border } },
      },
    },
  });
}

async function loadAccuracyOverTime() {
  try {
    const accuracy = await Api.predictionAccuracyOverTime();
    renderAccuracyOverTime(accuracy);
  } catch (err) {
    console.error(err);
    renderAccuracyOverTime(null);
  }
}

// ------------------------------------------------------------
// Modo "Última Semana Antes do Exame": checklist curto, ordenado pelo
// ganho estimado de UM passo em cada hábito ainda ajustável em poucos dias
// (ver gerar_checklist_ultima_semana no backend) — atualiza-se em tempo
// real com o resto do simulador, tal como a explicação e a comparação com
// pares, porque parte exatamente dos mesmos valores do formulário.
// ------------------------------------------------------------
function renderExamWeekChecklist(result) {
  const list = document.getElementById("examweek-checklist");
  const message = document.getElementById("examweek-message");
  if (!list) return;

  const items = result.items || [];
  if (items.length === 0) {
    list.innerHTML = "";
    message.textContent = result.message || "Não há mudanças rápidas com impacto relevante identificadas nesta previsão.";
    return;
  }

  message.textContent = "";
  // Uma linha por sugestão, com a ação recomendada e o ganho estimado de nota.
  list.innerHTML = items.map((item) => `
    <li class="examweek-item">
      <span class="examweek-item-action">${escapeHtml(item.action)}</span>
      <span class="examweek-item-gain">+${fmtNum(item.estimated_gain, 2)} valores</span>
    </li>
  `).join("");
}

// ------------------------------------------------------------
// Cenários lado a lado: guarda até 3 "fotografias" do simulador (hábitos +
// resultado) para comparar as diferenças de uma vez, em vez de teres de
// decorar o número anterior enquanto ajustas os controlos outra vez.
// ------------------------------------------------------------
function saveScenarioForComparison() {
  const messageBox = document.getElementById("scenario-save-message");
  messageBox.classList.remove("hidden");

  if (!lastPredictionPayload || !lastPredictionResult) {
    messageBox.textContent = "Ainda não há nenhuma previsão calculada para guardar.";
    return;
  }
  if (savedScenarios.length >= MAX_SCENARIOS) {
    messageBox.textContent = `Já tens ${MAX_SCENARIOS} cenários guardados — remove um antes de adicionar outro.`;
    return;
  }

  const labelInput = document.getElementById("scenario-save-label");
  const label = labelInput.value.trim() || `Cenário ${savedScenarios.length + 1}`;

  // Guarda uma cópia "congelada" dos hábitos e do resultado atuais (não referências vivas).
  savedScenarios.push({
    id: ++scenarioIdCounter,
    label,
    payload: { ...lastPredictionPayload },
    grade: lastPredictionResult.nota_prevista_habitos.predicted_grade,
    mae: lastPredictionResult.nota_prevista_habitos.mae,
    proba: lastPredictionResult.aprovacao.probabilidade_aprovacao * 100,
    aprovado: lastPredictionResult.aprovacao.aprovado_previsto,
  });

  labelInput.value = "";
  messageBox.classList.add("hidden");
  renderScenarioComparison();
}

function removeScenario(id) {
  savedScenarios = savedScenarios.filter((s) => s.id !== id);
  renderScenarioComparison();
}

function clearScenarios() {
  savedScenarios = [];
  renderScenarioComparison();
}

function renderScenarioComparison() {
  const wrap = document.getElementById("scenario-compare-wrap");
  if (!wrap) return;

  if (savedScenarios.length === 0) {
    wrap.innerHTML = `<p class="card-subtitle">Ainda não guardaste nenhum cenário para comparar.</p>`;
    return;
  }

  // Destaca a coluna com a nota prevista mais alta — não é preciso ler a
  // tabela toda linha a linha para ver qual cenário compensa mais.
  const bestGrade = Math.max(...savedScenarios.map((s) => s.grade));

  // Linhas da tabela: primeiro nota e probabilidade, depois um valor por cada campo de hábito.
  const rows = [
    {
      key: "grade",
      label: "Nota prevista",
      render: (s) => `${fmtNum(s.grade, 1)} / 20${s.mae != null ? ` (± ${fmtNum(s.mae, 1)})` : ""}`,
    },
    { key: "proba", label: "Probabilidade de aprovação", render: (s) => `${fmtNum(s.proba, 0)}%` },
    ...Object.keys(SCENARIO_FIELD_LABELS).map((field) => ({
      key: field,
      label: SCENARIO_FIELD_LABELS[field],
      render: (s) => formatExplainValue(field, s.payload[field]),
    })),
  ];

  // Cabeçalho: uma coluna por cenário, com nome e botão de remover.
  const headerCells = savedScenarios.map((s) => `
    <th class="${s.grade === bestGrade ? "scenario-best-col" : ""}">
      <div class="scenario-col-header">
        <span>${escapeHtml(s.label)}</span>
        <button type="button" class="btn-small btn-small-danger" data-remove-scenario="${s.id}">Remover</button>
      </div>
    </th>
  `).join("");

  const bodyRows = rows.map((row) => `
    <tr>
      <td>${row.label}</td>
      ${savedScenarios.map((s) => `
        <td class="${row.key === "grade" && s.grade === bestGrade ? "scenario-best-col" : ""}">${row.render(s)}</td>
      `).join("")}
    </tr>
  `).join("");

  wrap.innerHTML = `
    <table>
      <thead><tr><th>Cenário</th>${headerCells}</tr></thead>
      <tbody>${bodyRows}</tbody>
    </table>
  `;

  wrap.querySelectorAll("[data-remove-scenario]").forEach((btn) => {
    btn.addEventListener("click", () => removeScenario(Number(btn.dataset.removeScenario)));
  });
}

// ------------------------------------------------------------
// Exportar/importar cenários (Ideia 8): guarda os cenários guardados em
// memória num ficheiro JSON, para os poderes reabrir mais tarde ou partilhar
// — os cenários lado a lado não são guardados na BD (ver o comentário acima
// sobre savedScenarios), por isso sem isto perdem-se sempre ao fechar a app.
// ------------------------------------------------------------
function exportScenariosJson() {
  const messageBox = document.getElementById("scenario-save-message");
  if (savedScenarios.length === 0) {
    messageBox.classList.remove("hidden");
    messageBox.textContent = "Ainda não guardaste nenhum cenário para exportar.";
    return;
  }

  const payload = {
    exported_at: new Date().toISOString(),
    scenarios: savedScenarios.map((s) => ({
      label: s.label, payload: s.payload, grade: s.grade, mae: s.mae, proba: s.proba, aprovado: s.aprovado,
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "cenarios_studentperfomance.json";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function importScenariosFromFile(file) {
  const messageBox = document.getElementById("scenario-save-message");
  messageBox.classList.remove("hidden");

  const reader = new FileReader();
  reader.onload = () => {
    let items;
    try {
      const data = JSON.parse(reader.result);
      // Aceita tanto um array direto de cenários como um objeto { scenarios: [...] } (o formato exportado).
      items = Array.isArray(data) ? data : data.scenarios;
      if (!Array.isArray(items)) throw new Error("formato inválido");
    } catch (err) {
      messageBox.textContent = "Não foi possível ler o ficheiro de cenários (formato inválido).";
      return;
    }

    let added = 0;
    for (const item of items) {
      if (savedScenarios.length >= MAX_SCENARIOS) break; // respeita sempre o limite máximo
      if (!item || typeof item.payload !== "object" || typeof item.grade !== "number") continue; // ignora itens malformados
      savedScenarios.push({
        id: ++scenarioIdCounter,
        label: item.label || `Cenário importado ${savedScenarios.length + 1}`,
        payload: { ...item.payload },
        grade: item.grade,
        mae: typeof item.mae === "number" ? item.mae : null,
        proba: typeof item.proba === "number" ? item.proba : null,
        aprovado: typeof item.aprovado === "boolean" ? item.aprovado : null,
      });
      added++;
    }

    messageBox.textContent = added > 0
      ? `${added} cenário(s) importado(s).`
      : "Nenhum cenário válido encontrado no ficheiro (ou já tens o máximo de 3 cenários guardados).";
    renderScenarioComparison();
  };
  reader.onerror = () => {
    messageBox.textContent = "Não foi possível ler o ficheiro selecionado.";
  };
  reader.readAsText(file);
}
