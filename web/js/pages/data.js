// ============================================================
// Página: Dados (Explorador de Dados)
// Tabela paginada de todos os estudantes, com filtros por escola, faixa de
// desempenho e situação de risco, e exportação do resultado filtrado em CSV.
// ============================================================

// Estado local da paginação: página atual e nº de linhas por página.
const dataExplorerState = { page: 1, page_size: 20 };

// Aplica um filtro vindo de outra página (ver goToPage/registerPageFilterHandler
// em main.js) — clicar numa barra do histograma de notas ou numa fatia do
// gráfico aprovado/reprovado, na Visão Geral, chega aqui já com
// perf_band/at_risk prontos a pré-selecionar nos <select> dos filtros.
function dataApplyExternalFilter(filter) {
  if (!filter) return;
  const schoolSelect = document.getElementById("data-filter-school");
  const bandSelect = document.getElementById("data-filter-band");
  const riskSelect = document.getElementById("data-filter-risk");
  // Só atualiza cada <select> se o filtro trouxer esse campo específico.
  if (filter.school !== undefined && schoolSelect) schoolSelect.value = filter.school;
  if (filter.perf_band !== undefined && bandSelect) bandSelect.value = filter.perf_band;
  if (filter.at_risk !== undefined && riskSelect) riskSelect.value = String(filter.at_risk);
  dataExplorerState.page = 1; // qualquer novo filtro reinicia a paginação
  loadDataTable();
}
// Regista este handler para que main.js o chame quando outra página navegar para "data" com um filtro.
registerPageFilterHandler("data", dataApplyExternalFilter);

registerPage("data", async () => {
  const schoolSelect = document.getElementById("data-filter-school");
  const bandSelect = document.getElementById("data-filter-band");
  const riskSelect = document.getElementById("data-filter-risk");

  // Qualquer mudança num dos 3 filtros recarrega a tabela a partir da página 1.
  [schoolSelect, bandSelect, riskSelect].forEach((el) =>
    el.addEventListener("change", () => {
      dataExplorerState.page = 1;
      loadDataTable();
    })
  );

  document.getElementById("data-export-csv").addEventListener("click", exportDataAsCsv);

  // Se a navegação até aqui trouxe um filtro pendente (clique num gráfico da
  // Visão Geral, na primeira vez que se visita a página Dados), aplica-o em
  // vez do estado por omissão — ver consumePendingNavFilter.
  const pending = consumePendingNavFilter("data");
  if (pending) dataApplyExternalFilter(pending);
  else await loadDataTable();
});

// Ideia 4: exportar o dataset completo (ou a vista já filtrada) em CSV — usa
// os mesmos filtros aplicados na tabela (ver src/data_export.py). Abrir a
// URL numa nova aba deixa o navegador tratar do download (o endpoint
// devolve Content-Disposition: attachment), sem sair da página atual.
function exportDataAsCsv() {
  const school = document.getElementById("data-filter-school").value;
  const perfBand = document.getElementById("data-filter-band").value;
  const atRisk = document.getElementById("data-filter-risk").value;
  const url = Api.exportCsvUrl({ school, perf_band: perfBand, at_risk: atRisk });
  window.open(url, "_blank");
}

async function loadDataTable() {
  // Lê os valores atuais dos 3 filtros diretamente do DOM.
  const school = document.getElementById("data-filter-school").value;
  const perfBand = document.getElementById("data-filter-band").value;
  const atRisk = document.getElementById("data-filter-risk").value;

  // Pede ao backend só a página atual, já filtrada e paginada (evita transferir o dataset inteiro).
  const data = await Api.studentsTable({
    school, perf_band: perfBand, at_risk: atRisk,
    page: dataExplorerState.page, page_size: dataExplorerState.page_size,
  });

  renderDataTable(data.students);
  renderPagination(data);
}

function renderDataTable(students) {
  const tbody = document.querySelector("#data-table tbody");
  // Uma linha de tabela por estudante, com pastilhas coloridas para faixa de desempenho e risco.
  const rows = students.map((s) => `
    <tr>
      <td>${s.student_id}</td>
      <td>${s.school}</td>
      <td>${s.sex}</td>
      <td>${s.age}</td>
      <td>${s.studytime}</td>
      <td>${s.absences}</td>
      <td>${s.failures}</td>
      <td>${s.G1}</td>
      <td>${s.G2}</td>
      <td><strong>${s.G3}</strong></td>
      <td><span class="band-pill band-${s.perf_band}">${s.perf_band}</span></td>
      <td>${s.at_risk ? `<span class="pill pill-no">${escapeHtml(t("data_pill_at_risk"))}</span>` : `<span class="pill pill-yes">${escapeHtml(t("data_pill_ok"))}</span>`}</td>
    </tr>
  `).join("");
  // Sem resultados: mostra uma linha única explicativa em vez de tabela vazia.
  tbody.innerHTML = rows || `<tr><td colspan="12">${escapeHtml(t("data_no_results"))}</td></tr>`;
}

function renderPagination(data) {
  const container = document.getElementById("data-pagination");
  const { page, total_pages, total } = data;

  // Botões anterior/seguinte (desativados nos extremos), e um pequeno campo
  // para ir diretamente a uma página escrevendo o número — útil quando o
  // dataset tem muitas páginas e clicar "Seguinte" repetidamente seria lento.
  container.innerHTML = `
    <button id="page-prev" ${page <= 1 ? "disabled" : ""}>${escapeHtml(t("data_pagination_prev"))}</button>
    <span class="pagination-info">${escapeHtml(t("data_pagination_info").replace("{page}", page).replace("{total_pages}", total_pages).replace("{total}", total))}</span>
    <form class="pagination-goto" id="pagination-goto-form">
      <label for="page-goto-input">${escapeHtml(t("data_pagination_goto_label"))}</label>
      <input type="number" id="page-goto-input" min="1" max="${total_pages}" value="${page}" ${total_pages <= 1 ? "disabled" : ""}>
      <button type="submit" class="btn-small" ${total_pages <= 1 ? "disabled" : ""}>${escapeHtml(t("data_pagination_goto_btn"))}</button>
    </form>
    <button id="page-next" ${page >= total_pages ? "disabled" : ""}>${escapeHtml(t("data_pagination_next"))}</button>
  `;

  // "?." evita erro se o botão não existir (ex.: já desativado/removido).
  document.getElementById("page-prev")?.addEventListener("click", () => {
    dataExplorerState.page = Math.max(1, dataExplorerState.page - 1);
    loadDataTable();
  });
  document.getElementById("page-next")?.addEventListener("click", () => {
    dataExplorerState.page = Math.min(total_pages, dataExplorerState.page + 1);
    loadDataTable();
  });

  // Ir para a página escrita: um <form> (em vez de só um botão) permite
  // também submeter com Enter, sem ser preciso clicar em "Ir". O valor é
  // sempre "encostado" ao intervalo válido [1, total_pages] — escrever 0,
  // um número maior que o total, ou texto inválido nunca dá erro, só ajusta
  // para o limite mais próximo.
  document.getElementById("pagination-goto-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("page-goto-input");
    let target = parseInt(input.value, 10);
    if (Number.isNaN(target)) target = page;
    target = Math.min(Math.max(target, 1), total_pages);
    dataExplorerState.page = target;
    loadDataTable();
  });
}
