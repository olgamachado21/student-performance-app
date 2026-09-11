// ============================================================
// Página: Início — dashboard de abertura / página principal da app.
// Mostra uma descrição geral da aplicação, algumas estatísticas rápidas do
// dataset, e um mosaico de cartões clicáveis para todas as secções/
// funcionalidades (agrupados exatamente como as secções do menu lateral).
// O conteúdo de cada cartão é estático (HTML em index.html) — este ficheiro
// liga os cliques à navegação, preenche a faixa de estatísticas, e decide
// se mostra o banner do tour de boas-vindas (ver initOnboardingBanner).
// ============================================================

registerPage("home", async () => {
  // Liga os cartões de funcionalidades à navegação, e carrega as estatísticas rápidas.
  wireHomeFeatureCards();
  initOnboardingBanner();
  await loadHomeHeroStats();
});

// ------------------------------------------------------------
// Banner do tour de boas-vindas: mostra-se só enquanto o tour ainda não
// tiver sido visto nem dispensado (ver isOnboardingResolved/
// markOnboardingResolved e showOnboarding em main.js). Ao contrário de um
// popup automático, fica sempre à vista mas nunca bloqueia nada — o
// utilizador decide se quer ver o tour ou simplesmente fechar o banner.
// ------------------------------------------------------------
function initOnboardingBanner() {
  const banner = document.getElementById("home-onboarding-banner");
  if (!banner) return;

  // Já resolvido (visto ou dispensado antes) -> nem mostra o banner.
  if (typeof isOnboardingResolved === "function" && isOnboardingResolved()) return;
  banner.classList.remove("hidden");

  // Evita registar os listeners outra vez se se voltar à página Início.
  if (banner.dataset.wired === "true") return;
  banner.dataset.wired = "true";

  document.getElementById("onboarding-banner-view-btn").addEventListener("click", () => {
    banner.classList.add("hidden"); // some já, mesmo que o utilizador feche o tour de seguida sem o terminar
    if (typeof showOnboarding === "function") showOnboarding(true);
  });
  document.getElementById("onboarding-banner-close-btn").addEventListener("click", () => {
    banner.classList.add("hidden");
    if (typeof markOnboardingResolved === "function") markOnboardingResolved();
  });
}

// Qualquer elemento com data-goto navega para essa página, tal como se
// tivesse sido clicado no menu lateral (o goToPage já trata de atualizar
// o item ativo do menu e mostrar a secção correta).
function wireHomeFeatureCards() {
  // Seleciona todos os elementos com o atributo data-goto dentro da página Início.
  document.querySelectorAll("#page-home [data-goto]").forEach((el) => {
    el.addEventListener("click", () => {
      // Só chama goToPage se a função existir globalmente (definida em main.js).
      if (typeof goToPage === "function") goToPage(el.dataset.goto);
    });
  });
}

async function loadHomeHeroStats() {
  const container = document.getElementById("home-hero-stats");
  if (!container) return; // elemento não existe nesta página/versão do HTML -> nada a fazer
  if (!container.querySelector(".home-hero-stat-value")) {
    // Ainda não há estatísticas renderizadas: mostra placeholders animados (skeleton) enquanto carrega.
    showSkeletonPlaceholders("home-hero-stats", { count: 4, cardClass: "home-hero-stat", height: "62px" });
  }
  try {
    // Vai buscar as estatísticas gerais (usa cache para não repetir o pedido desnecessariamente).
    const stats = await cached("stats", Api.stats);
    renderHomeHeroStats(container, [
      { label: t("home_stat_students"), value: `${stats.n_students}` },
      { label: t("home_stat_avg_grade"), value: `${fmtNum(stats.average_grade)} / 20` },
      { label: t("home_stat_pass_rate"), value: fmtPct(stats.pass_rate) },
      { label: t("home_stat_tools"), value: "11" }, // valor fixo, não vem da API
    ]);
  } catch (err) {
    console.error("Não foi possível carregar as estatísticas do Início:", err);
    // Sem dados do dataset, mostra pelo menos a contagem fixa de
    // ferramentas — a faixa nunca fica com skeletons presos para sempre.
    renderHomeHeroStats(container, [
      { label: t("home_stat_tools"), value: "11" },
    ]);
  }
}

function renderHomeHeroStats(container, items) {
  // Gera um cartão por cada item, com um espaço vazio para o valor (preenchido a seguir com animação).
  container.innerHTML = items.map((_, i) => `
    <div class="home-hero-stat">
      <div class="home-hero-stat-value" data-stat-index="${i}"></div>
      <div class="home-hero-stat-label">${items[i].label}</div>
    </div>
  `).join("");
  // Para cada cartão criado, anima o texto do valor (efeito de contagem/fade, definido globalmente).
  container.querySelectorAll("[data-stat-index]").forEach((el) => {
    animateNumberText(el, items[Number(el.dataset.statIndex)].value);
  });
}
