// ============================================================
// Página: Otimizador de Estudo
// Duas ferramentas: (1) plano individual — que mudanças de hábito um
// estudante precisa para atingir uma nota-alvo; (2) simulação em lote —
// aplicar a mesma alteração hipotética a toda a turma em risco de uma vez.
// ============================================================

registerPage("optimizer", async () => {
  const btn = document.getElementById("optimizer-generate-btn");
  btn.addEventListener("click", () => runOptimizer());

  const cohortBtn = document.getElementById("cohort-simulate-btn");
  if (cohortBtn) cohortBtn.addEventListener("click", () => runCohortSimulation());
});

async function runOptimizer() {
  // Lê e converte os dois campos de input: ID do estudante e nota-alvo.
  const studentId = parseInt(document.getElementById("optimizer-student-id").value, 10);
  const targetGrade = parseFloat(document.getElementById("optimizer-target-grade").value);

  const resultBox = document.getElementById("optimizer-result");
  const placeholder = document.getElementById("optimizer-placeholder");

  if (!studentId || studentId < 1) {
    // ID inválido: mostra mensagem de erro e esconde o resultado anterior (se houver).
    placeholder.textContent = "Indica um número de estudante válido.";
    placeholder.classList.remove("hidden");
    resultBox.classList.add("hidden");
    return;
  }
  if (Number.isNaN(targetGrade) || targetGrade < 0 || targetGrade > 20) {
    // Nota-alvo fora da escala válida (0-20) ou não numérica.
    placeholder.textContent = "Indica uma nota-alvo válida (entre 0 e 20).";
    placeholder.classList.remove("hidden");
    resultBox.classList.add("hidden");
    return;
  }

  // Feedback visual de "a processar" no botão, para o utilizador saber que o pedido está em curso.
  const btn = document.getElementById("optimizer-generate-btn");
  const originalText = btn.textContent;
  btn.textContent = "A calcular…";
  btn.disabled = true;

  try {
    const result = await Api.optimizer(studentId, targetGrade);
    displayOptimizerResult(result);
  } catch (err) {
    console.error(err);
    placeholder.textContent = "Não foi possível calcular o plano. Confirma que o número do estudante existe no dataset.";
    placeholder.classList.remove("hidden");
    resultBox.classList.add("hidden");
  } finally {
    // Repõe o botão ao estado normal, quer o pedido tenha tido sucesso ou não.
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

function displayOptimizerResult(result) {
  document.getElementById("optimizer-placeholder").classList.add("hidden");
  const resultBox = document.getElementById("optimizer-result");
  resultBox.classList.remove("hidden");

  // Medidor (gauge) circular com a nota inicial, colorido conforme a faixa de desempenho.
  const initialPct = (result.initial_grade / 20) * 100;
  const initialColor = result.initial_grade >= 14 ? COLORS.positive : result.initial_grade >= 10 ? COLORS.primary : COLORS.negative;
  setGauge("gauge-optimizer-initial", "gauge-optimizer-initial-value", initialPct, initialColor);
  document.getElementById("gauge-optimizer-initial-value").textContent = fmtNum(result.initial_grade, 1);

  // Medidor com a nota final prevista após aplicar as mudanças; verde só se a meta foi atingida.
  const finalPct = (result.final_grade / 20) * 100;
  const finalColor = result.achieved ? COLORS.positive : result.final_grade > result.initial_grade ? COLORS.primary : COLORS.negative;
  setGauge("gauge-optimizer-final", "gauge-optimizer-final-value", finalPct, finalColor);
  document.getElementById("gauge-optimizer-final-value").textContent = fmtNum(result.final_grade, 1);

  const messageBox = document.getElementById("optimizer-message");
  messageBox.textContent = result.message;

  // Tabela com a lista de mudanças de hábito sugeridas (de -> para); escondida se não houver nenhuma.
  const tbody = document.querySelector("#optimizer-changes-table tbody");
  const changesWrap = document.getElementById("optimizer-changes-wrap");
  if (!result.changes || result.changes.length === 0) {
    changesWrap.classList.add("hidden");
    tbody.innerHTML = "";
  } else {
    changesWrap.classList.remove("hidden");
    tbody.innerHTML = result.changes.map((c) => `
      <tr>
        <td>${c.label}</td>
        <td>${c.from}</td>
        <td><strong>${c.to}</strong></td>
      </tr>
    `).join("");
  }

  // Garante que o resultado fica visível no ecrã, mesmo que o utilizador tenha feito scroll.
  resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ------------------------------------------------------------
// Simulador em lote (turma): em vez de otimizar um estudante de cada vez
// (acima), aplica a MESMA alteração hipotética a TODOS os estudantes em
// risco de uma só vez, e mostra o impacto agregado na aprovação (ver
// simular_intervencao_turma no backend).
// ------------------------------------------------------------

// Lê um campo numérico de delta (variação); devolve null se estiver vazio ou não for número.
function readCohortDelta(id) {
  const el = document.getElementById(id);
  if (!el || el.value.trim() === "") return null;
  const value = parseFloat(el.value);
  return Number.isNaN(value) ? null : value;
}

async function runCohortSimulation() {
  const deltas = {};
  // Mapeamento entre o id do campo HTML e o nome da coluna correspondente no backend.
  const fields = [
    ["cohort-studytime", "studytime"], ["cohort-absences", "absences"],
    ["cohort-goout", "goout"], ["cohort-dalc", "Dalc"], ["cohort-walc", "Walc"],
  ];
  // Só inclui no payload os campos que o utilizador de facto preencheu.
  fields.forEach(([elId, key]) => {
    const value = readCohortDelta(elId);
    if (value !== null) deltas[key] = value;
  });

  const resultBox = document.getElementById("cohort-simulation-result");
  const placeholder = document.getElementById("cohort-simulation-placeholder");

  if (Object.keys(deltas).length === 0) {
    // Nenhum campo preenchido: nada para simular.
    placeholder.classList.remove("hidden");
    resultBox.classList.add("hidden");
    return;
  }

  const btn = document.getElementById("cohort-simulate-btn");
  const originalText = btn.textContent;
  btn.textContent = "A simular…";
  btn.disabled = true;

  try {
    const result = await Api.cohortSimulation(deltas);
    displayCohortSimulationResult(result);
  } catch (err) {
    console.error(err);
    placeholder.textContent = err.message || "Não foi possível calcular a simulação em lote.";
    placeholder.classList.remove("hidden");
    resultBox.classList.add("hidden");
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

function displayCohortSimulationResult(result) {
  document.getElementById("cohort-simulation-placeholder").classList.add("hidden");
  const resultBox = document.getElementById("cohort-simulation-result");
  resultBox.classList.remove("hidden");

  // 4 KPIs: quantos estudantes simulados, nota média antes/depois, aprovados
  // antes/depois (com a variação em destaque) e taxa de aprovação final.
  renderKpiCards("cohort-simulation-kpis", [
    { label: "Estudantes em risco simulados", value: result.n_students },
    { label: "Nota média (antes → depois)", value: `${fmtNum(result.avg_grade_before)} → ${fmtNum(result.avg_grade_after)}` },
    {
      label: "Aprovados no grupo (antes → depois)",
      value: `${result.n_passing_before} → ${result.n_passing_after}`,
      delta: result.newly_passing !== 0 ? `${result.newly_passing > 0 ? "+" : ""}${result.newly_passing}` : null,
      deltaPositive: result.newly_passing >= 0,
    },
    { label: "Taxa de aprovação do grupo (depois)", value: fmtPct(result.pass_rate_after) },
  ]);

  document.getElementById("cohort-simulation-message").textContent = result.message;
}
