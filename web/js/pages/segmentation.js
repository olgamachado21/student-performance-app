// ============================================================
// Página: Segmentação de Perfis (K-Means)
// Agrupa os estudantes em clusters (perfis) com base num conjunto de
// variáveis escolhido pelo utilizador (clustering configurável), com
// sugestões de micro-hábitos por grupo e exportação para CSV.
// ============================================================

registerPage("segmentation", async () => {
  const select = document.getElementById("segment-n-clusters");
  const featureBoxes = document.querySelectorAll("#segment-features input");

  // Lê as variáveis atualmente marcadas nas caixas de seleção.
  function currentFeatures() {
    return Array.from(featureBoxes).filter((b) => b.checked).map((b) => b.value);
  }

  // Mínimo de 2 variáveis: se o utilizador tentar desmarcar a penúltima,
  // as restantes ficam visualmente desativadas até voltar a marcar alguma,
  // para não ser possível chegar a um pedido inválido (0 ou 1 variável).
  function enforceMinimumSelection() {
    const checkedCount = currentFeatures().length;
    const warning = document.getElementById("segment-features-warning");
    featureBoxes.forEach((box) => {
      // Só desativa uma caixa se já estivermos no mínimo (2) E ela estiver marcada
      // (impede desmarcá-la, mas não impede marcar outras).
      const disableThis = checkedCount <= 2 && box.checked;
      box.disabled = disableThis;
      box.closest("label").classList.toggle("checkbox-disabled", disableThis);
    });
    warning.hidden = checkedCount >= 2;
  }

  function reload() {
    loadSegmentation(parseInt(select.value, 10), currentFeatures());
  }

  select.addEventListener("change", reload);
  featureBoxes.forEach((box) =>
    box.addEventListener("change", () => {
      enforceMinimumSelection();
      reload();
    })
  );

  const exportBtn = document.getElementById("segment-export-csv-btn");
  if (exportBtn) exportBtn.addEventListener("click", exportSegmentationCsv);

  enforceMinimumSelection();
  await loadSegmentation(parseInt(select.value, 10), currentFeatures());
});

// Guarda o último resultado carregado, para a exportação CSV não precisar de pedir de novo à API.
let lastSegmentationData = null;

async function loadSegmentation(nClusters, features) {
  const grid = document.getElementById("segment-grid");
  // 4 cartões placeholder (skeleton) enquanto o resultado não chega.
  grid.innerHTML = `
    <div class="segment-card skeleton" style="height:220px"></div>
    <div class="segment-card skeleton" style="height:220px"></div>
    <div class="segment-card skeleton" style="height:220px"></div>
    <div class="segment-card skeleton" style="height:220px"></div>
  `;

  try {
    // cache por nº de clusters + variáveis escolhidas, para não repetir o
    // pedido se o utilizador voltar à mesma combinação
    const cacheKey = `segmentation_${nClusters}_${features.slice().sort().join("-")}`;
    const data = await cached(cacheKey, () => Api.segmentation(nClusters, features));
    lastSegmentationData = data;
    renderSegments(data);
  } catch (err) {
    console.error(err);
    grid.innerHTML = `<div class="info-box">Não foi possível carregar a segmentação. Confirma que a API está a correr.</div>`;
  }
}

function renderSegments(data) {
  const grid = document.getElementById("segment-grid");
  // Um cartão por grupo/cluster, com nome, tamanho, traços característicos,
  // 4 estatísticas resumidas e sugestões de micro-hábitos (se existirem).
  grid.innerHTML = data.groups.map((g, i) => `
    <div class="segment-card segment-card-clickable" data-cluster-index="${i}" role="button" tabindex="0" aria-label="Ver estudantes do grupo ${escapeAttr(g.name)}">
      <div class="segment-name">${g.name}</div>
      <div class="segment-size">${g.size} estudantes (${g.size_pct}% do total)</div>
      <div class="segment-traits">
        ${g.traits.map((t) => `<span class="segment-trait">${t}</span>`).join("")}
      </div>
      <div class="segment-stats">
        <div>
          <div class="segment-stat-label">Nota média</div>
          <div class="segment-stat-value">${fmtNum(g.avg_grade)}</div>
        </div>
        <div>
          <div class="segment-stat-label">Taxa de risco</div>
          <div class="segment-stat-value">${g.risk_pct}%</div>
        </div>
        <div>
          <div class="segment-stat-label">Estudo médio</div>
          <div class="segment-stat-value">${fmtNum(g.avg_studytime)}</div>
        </div>
        <div>
          <div class="segment-stat-label">Faltas médias</div>
          <div class="segment-stat-value">${fmtNum(g.avg_absences)}</div>
        </div>
      </div>
      ${renderSegmentSuggestions(g.suggestions)}
      <div class="segment-card-hint">Ver os ${g.size} estudantes deste grupo →</div>
    </div>
  `).join("");

  // Cartão inteiro clicável (moldura toda, tal como noutras listas de
  // cartões da app) — abre a lista de estudantes deste grupo em concreto,
  // em vez de ficar só com as médias agregadas (ver openClusterStudentsModal).
  grid.querySelectorAll("[data-cluster-index]").forEach((card) => {
    const group = data.groups[parseInt(card.dataset.clusterIndex, 10)];
    const open = () => openClusterStudentsModal(group);
    card.addEventListener("click", open);
    // Acessibilidade: também abre com Enter/Espaço, já que o cartão tem role="button".
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
  });
}

// ------------------------------------------------------------
// Cartões de cluster clicáveis -> lista de estudantes (ver run_segmentation
// em src/segmentation.py, que agora devolve os student_ids de cada grupo).
// A lista mostra os IDs como "chips" clicáveis, cada um a descarregar
// logo a ficha de desempenho PDF desse estudante — reaproveita
// downloadFichaFor, já definida em risk.js (carregado antes deste ficheiro
// em index.html), em vez de duplicar a mesma lógica de download.
// ------------------------------------------------------------
function openClusterStudentsModal(group) {
  // Cria a sobreposição (overlay) e o modal de raiz, com o resumo do grupo e
  // os "chips" de cada estudante (um botão por ID).
  const overlay = document.createElement("div");
  overlay.className = "app-modal-overlay";
  overlay.innerHTML = `
    <div class="app-modal cluster-students-modal" role="dialog" aria-modal="true" aria-labelledby="cluster-modal-title">
      <div class="app-modal-title" id="cluster-modal-title">${escapeHtml(group.name)}</div>
      <p class="card-subtitle">
        ${group.size} estudantes (${group.size_pct}% do total) · nota média ${fmtNum(group.avg_grade)} ·
        risco ${group.risk_pct}%
      </p>
      <div class="cluster-students-list">
        ${group.student_ids.map((id) => `
          <button type="button" class="cluster-student-chip" data-ficha="${id}" title="Descarregar ficha de desempenho">#${id}</button>
        `).join("")}
      </div>
      <div class="app-modal-actions">
        <button type="button" class="btn-small cluster-modal-close">Fechar</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // Fecha o modal com Escape, clique fora (no overlay) ou no botão "Fechar".
  const onKeydown = (e) => { if (e.key === "Escape") close(); };
  function close() {
    document.removeEventListener("keydown", onKeydown, true);
    overlay.remove();
  }
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  overlay.querySelector(".cluster-modal-close").addEventListener("click", close);
  document.addEventListener("keydown", onKeydown, true);

  // Cada chip de estudante descarrega diretamente a sua ficha PDF ao clicar.
  overlay.querySelectorAll("[data-ficha]").forEach((chip) => {
    chip.addEventListener("click", () => downloadFichaFor(chip.dataset.ficha));
  });
}

// Micro-hábitos sugeridos: 2-3 sugestões concretas ligadas diretamente aos
// traços mais desviantes do grupo (ver src/segmentation.py, _suggest_micro_habits)
// — não aparece nada se o grupo for "Perfil Misto" (sem traço característico
// suficientemente forte para gerar uma sugestão específica).
function renderSegmentSuggestions(suggestions) {
  if (!suggestions || suggestions.length === 0) return "";
  return `
    <div class="segment-suggestions">
      <div class="segment-suggestions-title">Sugestões para este perfil</div>
      <ul>
        ${suggestions.map((s) => `<li>${s}</li>`).join("")}
      </ul>
    </div>
  `;
}

// ------------------------------------------------------------
// Exportar segmentação para CSV (Ideia 8): a segmentação atual (a que está
// visível no ecrã, já com o nº de perfis e as variáveis escolhidas), com um
// estudante representado como a lista de IDs do seu grupo — em vez de uma
// linha por estudante, uma linha por grupo, que é como a página já
// apresenta a informação.
// ------------------------------------------------------------
function exportSegmentationCsv() {
  if (!lastSegmentationData || !lastSegmentationData.groups.length) return;

  // Função auxiliar para escapar valores no formato CSV (aspas duplicadas dentro de aspas).
  const csvEscape = (value) => `"${String(value).replace(/"/g, '""')}"`;
  const header = ["cluster_id", "nome", "estudantes", "percentagem", "nota_media", "taxa_risco", "estudo_medio", "faltas_medias", "student_ids"];
  // Uma linha por grupo, com os IDs dos estudantes concatenados por ";" dentro da célula.
  const rows = lastSegmentationData.groups.map((g) => [
    g.cluster_id, csvEscape(g.name), g.size, g.size_pct, g.avg_grade, g.risk_pct, g.avg_studytime, g.avg_absences,
    csvEscape(g.student_ids.join(";")),
  ].join(","));
  const csv = [header.join(","), ...rows].join("\n");

  // Cria um ficheiro (Blob) em memória e simula o clique num link para forçar o download.
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "segmentacao_perfis.csv";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url); // liberta a memória usada pelo Blob
}
