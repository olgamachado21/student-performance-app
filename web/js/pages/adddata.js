// ============================================================
// Página: Adicionar Dados
// Formulário para adicionar um estudante de cada vez (com sugestões de
// valores prováveis e avisos de valores pouco habituais), e importação em
// lote via CSV para adicionar vários estudantes de uma só vez.
// ============================================================

registerPage("adddata", async () => {
  await refreshAddDataKpis();

  const form = document.getElementById("adddata-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await submitNewStudent();
  });

  setupFieldSuggestions();
  document.getElementById("adddata-similar-toggle").addEventListener("click", toggleSimilarStudentsTable);
  refreshFieldSuggestions();

  document.getElementById("ad-bulk-submit").addEventListener("click", submitBulkImport);
});

// ------------------------------------------------------------------
// Sugestão de valores prováveis + avisos de valores pouco habituais: à
// medida que o utilizador preenche campos, procuramos os estudantes já
// existentes mais parecidos e sugerimos os valores típicos DESSE grupo
// para os campos ainda vazios (em vez da mediana/moda de todo o dataset —
// ver src/suggestions.py), e avisamos se algum valor já indicado foge
// muito do habitual ou é inconsistente com os outros (ver
// src/data_quality.py). Nada disto bloqueia a submissão.
// ------------------------------------------------------------------

// Lista dos campos do formulário que participam no cálculo de sugestões,
// com o id do elemento HTML e o tipo de valor (para conversão correta).
const SUGGESTION_FIELDS = [
  { key: "school", elId: "ad-school", kind: "select" },
  { key: "sex", elId: "ad-sex", kind: "select" },
  { key: "age", elId: "ad-age", kind: "number" },
  { key: "studytime", elId: "ad-studytime", kind: "select" },
  { key: "absences", elId: "ad-absences", kind: "number" },
  { key: "failures", elId: "ad-failures", kind: "select" },
  { key: "G1", elId: "ad-g1", kind: "number" },
  { key: "G2", elId: "ad-g2", kind: "number" },
];

// Rótulos legíveis para valores categóricos/codificados, usados nas dicas de sugestão.
const SUGGESTION_LABELS = {
  school: { GP: "GP", MS: "MS" },
  sex: { F: "F", M: "M" },
  studytime: { 1: "< 2h", 2: "2-5h", 3: "5-10h", 4: "> 10h" },
};

// Rótulos das colunas mostradas na tabela de "estudantes semelhantes".
const SIMILAR_TABLE_COLUMN_LABELS = {
  school: "Escola", sex: "Sexo", age: "Idade", studytime: "Estudo",
  absences: "Faltas", failures: "Reprovações", G1: "G1", G2: "G2",
};

let suggestionDebounceTimer = null; // temporizador usado para "debounce" (atrasar) os pedidos de sugestão
let lastUnusualWarnings = []; // últimos avisos de valores pouco habituais, usados na confirmação de envio
let similarStudentsTableVisible = false; // se a tabela de estudantes semelhantes está expandida

function setupFieldSuggestions() {
  // Liga um listener a cada campo relevante: 'change' para <select>, 'input' para os demais.
  SUGGESTION_FIELDS.forEach(({ elId }) => {
    const el = document.getElementById(elId);
    const eventName = el.tagName === "SELECT" ? "change" : "input";
    el.addEventListener(eventName, () => {
      // Debounce de 300ms: evita disparar um pedido à API a cada tecla premida.
      clearTimeout(suggestionDebounceTimer);
      suggestionDebounceTimer = setTimeout(refreshFieldSuggestions, 300);
    });
  });
}

// Lê os valores já preenchidos pelo utilizador (ignora campos vazios).
function readKnownSuggestionFields() {
  const known = {};
  SUGGESTION_FIELDS.forEach(({ key, elId, kind }) => {
    const raw = document.getElementById(elId).value;
    if (raw === "") return;
    known[key] = kind === "number" ? parseInt(raw, 10) : raw;
  });
  return known;
}

async function refreshFieldSuggestions() {
  const known = readKnownSuggestionFields();

  // Pede em paralelo as sugestões de valores e a verificação de valores pouco habituais.
  // Cada pedido é isolado com .catch() para que uma falha não impeça o outro de ser usado.
  const [suggestResult, checkResult] = await Promise.all([
    Api.suggestValues(known).catch((err) => { console.error(err); return null; }),
    Api.checkValues(known).catch((err) => { console.error(err); return null; }),
  ]);

  if (suggestResult) {
    renderFieldSuggestions(suggestResult);
    renderSimilarStudents(suggestResult.similar_students, suggestResult.n_similar);
  }
  if (checkResult) {
    lastUnusualWarnings = checkResult.warnings;
    renderUnusualValueWarnings(checkResult.warnings);
  }
}

function renderFieldSuggestions(result) {
  SUGGESTION_FIELDS.forEach(({ key, elId }) => {
    const hint = document.getElementById(`${elId}-suggestion`);
    const fieldEmpty = document.getElementById(elId).value === "";
    const value = result.suggestions[key];

    if (!fieldEmpty || value === undefined) {
      // Campo já preenchido, ou sem sugestão disponível: esconde a dica.
      hint.classList.add("hidden");
      hint.textContent = "";
      return;
    }

    // Usa o rótulo legível se existir, senão mostra o valor bruto.
    const displayValue = (SUGGESTION_LABELS[key] && SUGGESTION_LABELS[key][value]) ?? value;
    hint.innerHTML = `<span class="field-suggestion-dot"></span>sugestão: <strong>${escapeHtml(String(displayValue))}</strong>`;
    hint.classList.remove("hidden");
    hint.onclick = () => applySuggestion(elId, value); // clicar na dica preenche o campo automaticamente
  });
}

function applySuggestion(elId, value) {
  const el = document.getElementById(elId);
  el.value = value;
  refreshFieldSuggestions(); // recalcula tudo, já que este campo deixou de estar vazio
}

// -- Ideia 2: explicar a sugestão, mostrando os estudantes usados --------
function renderSimilarStudents(students, nSimilar) {
  const box = document.getElementById("adddata-similar-box");
  const toggle = document.getElementById("adddata-similar-toggle");
  const table = document.getElementById("adddata-similar-table");

  if (!students || students.length === 0) {
    // Sem nenhum campo conhecido ainda: nada para mostrar.
    box.classList.add("hidden");
    table.classList.add("hidden");
    similarStudentsTableVisible = false;
    return;
  }

  box.classList.remove("hidden");
  const arrow = similarStudentsTableVisible ? "▾" : "▸";
  toggle.textContent = `${arrow} Ver estudantes semelhantes usados na sugestão (${nSimilar} no total, ${students.length} em destaque)`;

  // Constrói a tabela dinamicamente a partir das chaves do primeiro estudante (colunas variam consoante os campos conhecidos).
  const cols = Object.keys(students[0]);
  const headerRow = cols.map((c) => `<th>${escapeHtml(SIMILAR_TABLE_COLUMN_LABELS[c] || c)}</th>`).join("");
  const bodyRows = students.map((s) => {
    const cells = cols.map((c) => `<td>${escapeHtml(String(s[c]))}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  table.innerHTML = `<table class="similar-students-table"><thead><tr>${headerRow}</tr></thead><tbody>${bodyRows}</tbody></table>`;
}

function toggleSimilarStudentsTable() {
  similarStudentsTableVisible = !similarStudentsTableVisible;
  const table = document.getElementById("adddata-similar-table");
  const toggle = document.getElementById("adddata-similar-toggle");
  table.classList.toggle("hidden", !similarStudentsTableVisible);
  const arrow = similarStudentsTableVisible ? "▾" : "▸";
  // Substitui só o primeiro caráter (a seta) do texto do botão, mantendo o resto igual.
  toggle.textContent = toggle.textContent.replace(/^[▾▸]/, arrow);
}

// -- Ideia 1: avisar sobre valores pouco habituais/inconsistentes --------
function renderUnusualValueWarnings(warnings) {
  const box = document.getElementById("adddata-warnings");
  if (!warnings || warnings.length === 0) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  // Um item por aviso, colorido conforme a severidade (info/warning).
  box.innerHTML = warnings.map((w) => `
    <div class="field-warning-item severity-${w.severity}">
      <span class="field-warning-dot"></span>
      <span>${escapeHtml(w.message)}</span>
    </div>
  `).join("");
}

async function refreshAddDataKpis() {
  // Só mostra os placeholders animados se as estatísticas ainda não estiverem em cache.
  if (AppCache["stats"] === undefined) showSkeletonPlaceholders("adddata-kpis", { count: 3 });
  const stats = await cached("stats", Api.stats);
  renderKpiCards("adddata-kpis", [
    { label: "Estudantes no dataset", value: stats.n_students },
    { label: "Nota média", value: `${fmtNum(stats.average_grade)} / 20` },
    { label: "Taxa de aprovação", value: fmtPct(stats.pass_rate) },
  ]);
}

// Todos os campos são opcionais: só entram no pedido se o utilizador
// escreveu/escolheu algo. Os que ficarem de fora usam o valor por omissão
// definido na API (para os campos do formulário) ou um valor típico
// calculado a partir do dataset atual (para os restantes, ver add_student.py).
function addTextField(payload, key, elId) {
  const value = document.getElementById(elId).value.trim();
  if (value !== "") payload[key] = value;
}

function addSelectField(payload, key, elId) {
  const value = document.getElementById(elId).value;
  if (value !== "") payload[key] = value;
}

function addNumberField(payload, key, elId) {
  const raw = document.getElementById(elId).value;
  if (raw === "") return;
  const parsed = parseInt(raw, 10);
  if (!Number.isNaN(parsed)) payload[key] = parsed;
}

// Micro-gamificação: um pequeno destaque quando o total de estudantes do
// dataset cruza um marco redondo (25, 50, 75...) — não é preciso um sistema
// de conquistas a sério, só um sinal visual de progresso de vez em quando.
const DATASET_MILESTONE_STEP = 25;
function crossesMilestone(prevTotal, nextTotal, step = DATASET_MILESTONE_STEP) {
  if (prevTotal === null || prevTotal === undefined || nextTotal <= prevTotal) return false;
  // Verifica se o total "atravessou" um múltiplo de step entre o valor anterior e o novo.
  return Math.floor(prevTotal / step) !== Math.floor(nextTotal / step);
}

async function submitNewStudent() {
  if (lastUnusualWarnings.length > 0) {
    // Há avisos pendentes: pede confirmação explícita antes de submeter (não bloqueia, só avisa).
    const summary = lastUnusualWarnings.map((w) => `• ${w.message}`).join("\n");
    const proceed = await appConfirm(
      `Antes de adicionar, repara nisto:\n\n${summary}\n\nQueres continuar mesmo assim?`,
      { title: "Valores pouco habituais", confirmLabel: "Adicionar mesmo assim", danger: false }
    );
    if (!proceed) return;
  }

  // Monta o payload só com os campos preenchidos.
  const payload = {};
  addSelectField(payload, "school", "ad-school");
  addSelectField(payload, "sex", "ad-sex");
  addNumberField(payload, "age", "ad-age");
  addNumberField(payload, "studytime", "ad-studytime");
  addNumberField(payload, "absences", "ad-absences");
  addNumberField(payload, "failures", "ad-failures");
  addNumberField(payload, "G1", "ad-g1");
  addNumberField(payload, "G2", "ad-g2");
  addTextField(payload, "nome", "ad-nome");
  addTextField(payload, "disciplina", "ad-disciplina");
  addTextField(payload, "ano", "ad-ano");

  const form = document.getElementById("adddata-form");
  const submitBtn = form.querySelector("button[type=submit]");
  const originalText = submitBtn.textContent;
  submitBtn.textContent = "A adicionar…";
  submitBtn.disabled = true;

  // Guarda o total anterior de estudantes, para depois verificar se um marco foi ultrapassado.
  const prevTotal = AppCache["stats"] ? AppCache["stats"].n_students : null;

  try {
    const result = await Api.addStudent(payload);

    // O dataset mudou no servidor — limpar as caches locais dependentes dele
    // para que as outras páginas (Visão Geral, Dados, etc.) reflitam o novo estudante.
    delete AppCache["stats"];
    delete AppCache["gradeDistribution"];
    delete AppCache["passFailCounts"];
    delete AppCache["correlations"];
    delete AppCache["alerts"];
    Object.keys(AppCache).forEach((key) => {
      if (key.startsWith("segmentation_")) delete AppCache[key];
    });

    showAddDataResult(result);
    await refreshAddDataKpis();

    const newTotal = result.dataset_stats.n_students;
    showToast("Estudante adicionado com sucesso.", { type: "success" });
    if (crossesMilestone(prevTotal, newTotal)) {
      // Cruzou um marco redondo: pequena celebração visual + toast especial.
      const kpiCard = document.querySelector("#adddata-kpis .kpi-card");
      celebrate(kpiCard || submitBtn);
      showToast(`Marco alcançado: ${newTotal} estudantes no dataset!`, { type: "success" });
    }
  } catch (err) {
    console.error(err);
    showToast("Não foi possível adicionar o estudante. Confirma que a API está a correr.", { type: "error" });
  } finally {
    submitBtn.textContent = originalText;
    submitBtn.disabled = false;
  }
}

// ------------------------------------------------------------------
// Ideia 3: importação em lote de estudantes via CSV — em vez de preencher o
// formulário estudante a estudante, carrega um ficheiro com várias linhas
// de uma só vez (ver src/bulk_import.py). Linhas inválidas são reportadas
// mas não impedem as restantes de serem adicionadas.
// ------------------------------------------------------------------
async function submitBulkImport() {
  const fileInput = document.getElementById("ad-bulk-file");
  const file = fileInput.files[0];
  const resultBox = document.getElementById("adddata-bulk-result");

  if (!file) {
    resultBox.classList.remove("hidden");
    resultBox.innerHTML = `<div class="bulk-import-summary">Escolhe primeiro um ficheiro CSV.</div>`;
    return;
  }

  const submitBtn = document.getElementById("ad-bulk-submit");
  const originalText = submitBtn.textContent;
  submitBtn.textContent = "A importar…";
  submitBtn.disabled = true;

  const prevTotal = AppCache["stats"] ? AppCache["stats"].n_students : null;

  try {
    const result = await Api.bulkImportStudents(file);
    renderBulkImportResult(result);

    if (result.added_count > 0) {
      // Pelo menos uma linha foi adicionada: invalida as mesmas caches que a adição individual.
      delete AppCache["stats"];
      delete AppCache["gradeDistribution"];
      delete AppCache["passFailCounts"];
      delete AppCache["correlations"];
      delete AppCache["alerts"];
      Object.keys(AppCache).forEach((key) => {
        if (key.startsWith("segmentation_")) delete AppCache[key];
      });
      await refreshAddDataKpis();

      const newTotal = AppCache["stats"] ? AppCache["stats"].n_students : null;
      showToast(
        `${result.added_count} estudante${result.added_count === 1 ? "" : "s"} importado${result.added_count === 1 ? "" : "s"} com sucesso${result.error_count > 0 ? ` (${result.error_count} linha(s) com erros)` : ""}.`,
        { type: result.error_count > 0 ? "warning" : "success" }
      );
      if (newTotal !== null && crossesMilestone(prevTotal, newTotal)) {
        celebrate(document.querySelector("#adddata-kpis .kpi-card") || submitBtn);
        showToast(`Marco alcançado: ${newTotal} estudantes no dataset!`, { type: "success" });
      }
    } else {
      // Nenhuma linha válida: nada foi alterado no dataset.
      showToast("Nenhuma linha válida foi importada — confirma o formato do ficheiro.", { type: "error" });
    }
    fileInput.value = ""; // limpa a seleção do ficheiro após a tentativa
  } catch (err) {
    console.error(err);
    resultBox.classList.remove("hidden");
    resultBox.innerHTML = `<div class="bulk-import-summary">Não foi possível importar o ficheiro: ${escapeHtml(err.message || "erro desconhecido")}</div>`;
    showToast("Não foi possível importar o ficheiro.", { type: "error" });
  } finally {
    submitBtn.textContent = originalText;
    submitBtn.disabled = false;
  }
}

function renderBulkImportResult(result) {
  const resultBox = document.getElementById("adddata-bulk-result");
  resultBox.classList.remove("hidden");

  const summary = `
    <div class="bulk-import-summary">
      <strong>${result.added_count}</strong> estudante(s) adicionado(s) com sucesso
      ${result.error_count > 0 ? `, <strong>${result.error_count}</strong> linha(s) com erros` : ""}.
      Total no dataset adicionado: ${result.total_added_so_far}.
    </div>
  `;

  // Lista detalhada de erros por linha, só construída se houver erros.
  const errorsHtml = result.errors && result.errors.length
    ? `<div class="bulk-import-errors">${result.errors.map((e) => `
        <div class="bulk-import-error-item">Linha ${e.line}: ${escapeHtml(e.errors.join("; "))}</div>
      `).join("")}</div>`
    : "";

  resultBox.innerHTML = summary + errorsHtml;
}

function showAddDataResult(result) {
  const box = document.getElementById("adddata-result");
  const body = document.getElementById("adddata-result-body");
  const s = result.added_student;

  // Linha de identificação (nome/disciplina/ano) só aparece se algum desses campos foi preenchido.
  const identityBits = [];
  if (s.nome) identityBits.push(escapeHtml(s.nome));
  if (s.disciplina) identityBits.push(escapeHtml(s.disciplina));
  if (s.ano) identityBits.push(escapeHtml(s.ano));
  const identityLine = identityBits.length
    ? `<p style="margin-bottom:0.4rem; color:var(--text-secondary);">${identityBits.join(" · ")}</p>`
    : "";

  box.classList.remove("hidden");
  body.innerHTML = `
    ${identityLine}
    <p style="margin-bottom:0.8rem;">
      Nota final (G3) prevista pelo modelo (<strong>${result.model_used}</strong>):
      <strong style="font-size:1.3rem; color:var(--primary);">${s.G3} / 20</strong>
    </p>
    <div class="kpi-row" style="grid-template-columns:repeat(4,1fr);">
      <div class="kpi-card">
        <div class="kpi-label">Total no dataset</div>
        <div class="kpi-value">${result.dataset_stats.n_students}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Nota média</div>
        <div class="kpi-value">${fmtNum(result.dataset_stats.average_grade)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Taxa de aprovação</div>
        <div class="kpi-value">${fmtPct(result.dataset_stats.pass_rate)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Taxa de risco</div>
        <div class="kpi-value">${fmtPct(result.dataset_stats.risk_rate)}</div>
      </div>
    </div>
  `;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
