// ============================================================
// main.js — router SPA (sem recarregar a página) e utilitários
// partilhados por todas as páginas.
// ============================================================

// Paleta de cores partilhada por todos os gráficos e elementos visuais da app.
const COLORS = {
  primary: "#4F46E5",
  primaryLight: "#818CF8",
  primaryLighter: "#C7D2FE",
  positive: "#059669",
  negative: "#DC2626",
  muted: "#64748B",
  border: "#E7E9EE",
};

// Cache simples em memória: evita voltar a pedir os mesmos dados à API
// sempre que o utilizador troca de página (eficiência).
const AppCache = {};

// Devolve o valor em cache se já existir; senão chama o loader, guarda o resultado e devolve-o.
async function cached(key, loader) {
  if (AppCache[key] !== undefined) return AppCache[key];
  const data = await loader();
  AppCache[key] = data;
  return data;
}

// Gera um nome genérico com a hora atual — usado sempre que um formulário
// (Dashboards, Esquema Mental, ...) permite criar um item sem escrever um
// nome, mas o backend exige que os nomes sejam únicos.
function genericTimeName(prefix) {
  const time = new Date().toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return `${prefix} ${time}`;
}

// ------------------------------------------------------------
// Janela de confirmação com o estilo da própria app — usada em vez do
// popup nativo do browser/sistema (confirm()) para tudo o que apaga ou
// confirma uma ação irreversível. Devolve uma Promise<boolean>, tal como um
// confirm() normal, mas sem bloquear o browser e mantendo o visual da app.
// ------------------------------------------------------------
function appConfirm(message, options = {}) {
  const {
    title = t("modal_confirm_title"),
    confirmLabel = t("modal_confirm_label"),
    cancelLabel = t("modal_cancel_label"),
    danger = true,
  } = options;

  return new Promise((resolve) => {
    // Constrói a sobreposição e o diálogo modal com os textos/rótulos fornecidos.
    const overlay = document.createElement("div");
    overlay.className = "app-modal-overlay";
    overlay.innerHTML = `
      <div class="app-modal" role="alertdialog" aria-modal="true" aria-labelledby="app-modal-title">
        <div class="app-modal-title" id="app-modal-title">${escapeHtml(title)}</div>
        <div class="app-modal-message">${escapeHtml(message)}</div>
        <div class="app-modal-actions">
          <button type="button" class="btn-small app-modal-cancel">${escapeHtml(cancelLabel)}</button>
          <button type="button" class="btn-small ${danger ? "btn-small-danger" : "btn-primary"} app-modal-confirm">${escapeHtml(confirmLabel)}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    // Remove o modal do DOM e resolve a Promise com o resultado (true=confirmou, false=cancelou).
    const cleanup = (result) => {
      document.removeEventListener("keydown", onKeydown, true);
      overlay.remove();
      resolve(result);
    };
    // Escape cancela, Enter confirma — atalhos de teclado comuns num diálogo.
    const onKeydown = (e) => {
      if (e.key === "Escape") { e.preventDefault(); cleanup(false); }
      else if (e.key === "Enter") { e.preventDefault(); cleanup(true); }
    };

    overlay.addEventListener("click", (e) => { if (e.target === overlay) cleanup(false); });
    overlay.querySelector(".app-modal-cancel").addEventListener("click", () => cleanup(false));
    overlay.querySelector(".app-modal-confirm").addEventListener("click", () => cleanup(true));
    document.addEventListener("keydown", onKeydown, true);

    const confirmBtn = overlay.querySelector(".app-modal-confirm");
    if (confirmBtn.focus) confirmBtn.focus(); // foca o botão de confirmar para permitir Enter imediato
  });
}

// ------------------------------------------------------------
// Comentários por estudante (ver src/notes.py e Api.studentNotes/
// addStudentNote/deleteStudentNote em api.js) — um espaço curto para o
// utilizador registar as suas próprias observações sobre um estudante,
// sempre ligado a um estudante real do dataset (nunca um bloco de notas
// solto). Partilhado entre a página Perfil do Estudante (sem contexto — o
// utilizador escreveu livremente sobre o estudante) e a tabela de
// estudantes em risco em Avisos e Alertas (com "context" pré-preenchido
// com o título do alerta que motivou o comentário). Reaproveita o mesmo
// par .app-modal-overlay/.app-modal usado pelo appConfirm() acima.
// ------------------------------------------------------------
function openStudentNotesModal(studentId, context = null) {
  const overlay = document.createElement("div");
  overlay.className = "app-modal-overlay";
  overlay.innerHTML = `
    <div class="app-modal student-notes-modal" role="dialog" aria-modal="true" aria-labelledby="notes-modal-title">
      <div class="app-modal-title" id="notes-modal-title">${escapeHtml(t("notes_modal_title_prefix"))}${escapeHtml(studentId)}</div>
      ${context ? `<p class="card-subtitle">${escapeHtml(t("notes_modal_from_alert"))} <strong>${escapeHtml(context)}</strong></p>` : ""}
      <div class="student-notes-list" id="student-notes-list">
        <div class="info-box">${escapeHtml(t("notes_loading"))}</div>
      </div>
      <form class="student-notes-form" id="student-notes-form">
        <textarea class="student-notes-textarea" id="student-notes-textarea" rows="2"
          placeholder="${escapeAttr(t("notes_placeholder"))}" required></textarea>
        <button type="submit" class="btn-small btn-primary">${escapeHtml(t("notes_save_btn"))}</button>
      </form>
      <div class="app-modal-actions">
        <button type="button" class="btn-small student-notes-close">${escapeHtml(t("notes_close_btn"))}</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const onKeydown = (e) => { if (e.key === "Escape") close(); };
  function close() {
    document.removeEventListener("keydown", onKeydown, true);
    overlay.remove();
  }
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  overlay.querySelector(".student-notes-close").addEventListener("click", close);
  document.addEventListener("keydown", onKeydown, true);

  const listEl = overlay.querySelector("#student-notes-list");

  function renderNotesList(items) {
    if (!items.length) {
      listEl.innerHTML = `<div class="info-box">${escapeHtml(t("notes_empty"))}</div>`;
      return;
    }
    const dateLocale = getLanguage() === "en" ? "en-GB" : "pt-PT";
    listEl.innerHTML = items.map((n) => `
      <div class="student-note-item">
        <div class="student-note-item-header">
          ${n.context ? `<span class="pill pill-context" title="${escapeAttr(n.context)}">${escapeHtml(n.context)}</span>` : ""}
          <span class="student-note-date">${new Date(n.created_at).toLocaleString(dateLocale, { dateStyle: "short", timeStyle: "short" })}</span>
          <button type="button" class="student-note-delete" data-note-id="${n.id}" title="${escapeAttr(t("notes_delete_title"))}" aria-label="${escapeAttr(t("notes_delete_title"))}">&times;</button>
        </div>
        <p class="student-note-text">${escapeHtml(n.text)}</p>
      </div>
    `).join("");
    listEl.querySelectorAll("[data-note-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ok = await appConfirm(t("notes_delete_confirm_msg"), { title: t("notes_delete_title"), confirmLabel: t("notes_delete_confirm_btn") });
        if (!ok) return;
        try {
          await Api.deleteStudentNote(btn.dataset.noteId);
          await reload();
          showToast(t("notes_deleted_toast"), { type: "success" });
        } catch (err) {
          showToast(err.message || t("notes_delete_error"), { type: "error" });
        }
      });
    });
  }

  async function reload() {
    const data = await Api.studentNotes(studentId);
    renderNotesList(data.notes || []);
  }

  overlay.querySelector("#student-notes-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const textarea = overlay.querySelector("#student-notes-textarea");
    const text = textarea.value.trim();
    if (!text) return;
    try {
      await Api.addStudentNote(studentId, text, context);
      textarea.value = "";
      await reload();
      showToast(t("notes_saved_toast"), { type: "success" });
    } catch (err) {
      showToast(err.message || t("notes_save_error"), { type: "error" });
    }
  });

  reload().catch((err) => {
    listEl.innerHTML = `<div class="info-box">${escapeHtml(t("notes_load_error"))}</div>`;
    console.error(err);
  });
}

// ------------------------------------------------------------
// Tour de boas-vindas (onboarding) — um pequeno guia em vários passos que
// explica a lógica geral da app (analisar dados -> prever -> agir). Nunca
// aparece sozinho ao abrir a app (isso seria intrusivo todas as vezes que
// alguém entra) — só é mostrado quando pedido: pelo banner discreto e
// dispensável na página Início (ver initOnboardingBanner em home.js), ou a
// qualquer momento pelo botão "Rever tour de boas-vindas" em Configurações.
// Guarda em localStorage que o banner/tour já foi "resolvido" (visto ou
// dispensado), só para o banner da Início parar de aparecer depois disso —
// o tour em si continua sempre acessível pelas Configurações. Reaproveita o
// mesmo par .app-modal-overlay/.app-modal usado pelo appConfirm() e pelos
// modais de dispersão/cluster, só com uma classe extra (.onboarding-modal)
// para ser um pouco mais largo e caber o conteúdo de cada passo.
// ------------------------------------------------------------
const ONBOARDING_STORAGE_KEY = "studentperfomanceOnboardingSeen";

// Lê/escreve o sinalizador em localStorage — usado tanto pelo modal (abaixo)
// como pelo banner da Início (ver initOnboardingBanner em home.js), para as
// duas partes ficarem sempre de acordo sobre se já foi "resolvido".
function isOnboardingResolved() {
  try { return localStorage.getItem(ONBOARDING_STORAGE_KEY) === "true"; } catch (_) { return false; } // localStorage indisponível — assume que nunca foi resolvido
}
function markOnboardingResolved() {
  try { localStorage.setItem(ONBOARDING_STORAGE_KEY, "true"); } catch (_) { /* ignora — só não persiste entre sessões */ }
}

// Conteúdo de cada passo: ícone (reaproveita os mesmos traços dos ícones do
// menu/cartões da Início, para o tour parecer parte da mesma app), título e
// texto. Mantido como dados simples para ser fácil acrescentar/editar passos.
// Cada passo guarda a CHAVE de tradução do título/texto (não o texto já
// resolvido), para que o tour continue correto mesmo que o idioma mude
// entre uma abertura e a seguinte — t() só é chamado ao desenhar o passo
// (ver renderOnboardingStep), nunca aqui.
const ONBOARDING_STEPS = [
  {
    icon: `<svg viewBox="0 0 16 16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6.2"></circle><path d="M5.5 8.3 7.3 10.2 10.8 6"></path></svg>`,
    titleKey: "onboarding_step1_title",
    textKey: "onboarding_step1_text",
  },
  {
    icon: `<svg viewBox="0 0 16 16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="13" x2="3" y2="8"></line><line x1="8" y1="13" x2="8" y2="4"></line><line x1="13" y1="13" x2="13" y2="10"></line></svg>`,
    titleKey: "onboarding_step2_title",
    textKey: "onboarding_step2_text",
  },
  {
    icon: `<svg viewBox="0 0 16 16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="5.5"></circle><circle cx="8" cy="8" r="2.4"></circle><circle cx="8" cy="8" r="0.6" fill="currentColor" stroke="none"></circle></svg>`,
    titleKey: "onboarding_step3_title",
    textKey: "onboarding_step3_text",
  },
  {
    icon: `<svg viewBox="0 0 16 16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.4c-2 0-3.3 1.6-3.3 3.6v2.4c0 .8-.3 1.6-.9 2.2l-.7.7h9.8l-.7-.7c-.6-.6-.9-1.4-.9-2.2V6c0-2-1.3-3.6-3.3-3.6Z"></path><path d="M6.4 13.3a1.6 1.6 0 003.2 0"></path></svg>`,
    titleKey: "onboarding_step4_title",
    textKey: "onboarding_step4_text",
  },
  {
    icon: `<svg viewBox="0 0 16 16" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="4.3"></circle><line x1="10.1" y1="10.1" x2="13.5" y2="13.5"></line></svg>`,
    titleKey: "onboarding_step5_title",
    textKey: "onboarding_step5_text",
    isLast: true,
  },
];

let onboardingStepIndex = 0;

// Constrói (se ainda não existir) e mostra a sobreposição do tour, sempre a
// começar no primeiro passo. "force" ignora o localStorage — usado pelo
// botão manual em Configurações, que deve poder reabrir o tour mesmo depois
// de já ter sido visto.
function showOnboarding(force = false) {
  if (!force && isOnboardingResolved()) return;

  onboardingStepIndex = 0;

  const overlay = document.createElement("div");
  overlay.className = "app-modal-overlay onboarding-overlay";
  overlay.innerHTML = `
    <div class="app-modal onboarding-modal" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
      <button type="button" class="onboarding-close" aria-label="${escapeAttr(t("onboarding_close_aria"))}">&times;</button>
      <div class="onboarding-step-icon" id="onboarding-icon"></div>
      <div class="app-modal-title" id="onboarding-title"></div>
      <p class="onboarding-text" id="onboarding-text"></p>
      <div class="onboarding-dots" id="onboarding-dots"></div>
      <div class="onboarding-actions">
        <button type="button" class="btn-small onboarding-skip">${escapeHtml(t("onboarding_skip_btn"))}</button>
        <button type="button" class="btn-primary onboarding-next" id="onboarding-next-btn">${escapeHtml(t("onboarding_next_btn"))}</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // Marca como "já visto" e remove o modal do DOM — chamado ao fechar por
  // qualquer via (X, Saltar, Escape, clicar fora, ou terminar o último passo).
  const finish = () => {
    markOnboardingResolved();
    document.removeEventListener("keydown", onKeydown, true);
    overlay.remove();
  };
  const onKeydown = (e) => {
    if (e.key === "Escape") { e.preventDefault(); finish(); }
    else if (e.key === "Enter") { e.preventDefault(); goToNextOnboardingStep(overlay, finish); }
  };

  overlay.addEventListener("click", (e) => { if (e.target === overlay) finish(); });
  overlay.querySelector(".onboarding-close").addEventListener("click", finish);
  overlay.querySelector(".onboarding-skip").addEventListener("click", finish);
  overlay.querySelector(".onboarding-next").addEventListener("click", () => goToNextOnboardingStep(overlay, finish));
  document.addEventListener("keydown", onKeydown, true);

  renderOnboardingStep(overlay);
}

// Avança um passo; no último passo, o botão "Começar" fecha o tour em vez de avançar.
function goToNextOnboardingStep(overlay, finish) {
  if (ONBOARDING_STEPS[onboardingStepIndex].isLast) { finish(); return; }
  onboardingStepIndex += 1;
  renderOnboardingStep(overlay);
}

// Preenche o conteúdo do passo atual (ícone, título, texto, pontos de
// progresso) e ajusta o rótulo do botão principal no último passo.
function renderOnboardingStep(overlay) {
  const step = ONBOARDING_STEPS[onboardingStepIndex];
  overlay.querySelector("#onboarding-icon").innerHTML = step.icon;
  overlay.querySelector("#onboarding-title").textContent = t(step.titleKey);
  overlay.querySelector("#onboarding-text").textContent = t(step.textKey);

  // Pontos de progresso: um por passo, o atual fica destacado — dá a noção
  // de "estou a meio de X passos" sem precisar de escrever "3 de 5".
  overlay.querySelector("#onboarding-dots").innerHTML = ONBOARDING_STEPS
    .map((_, i) => `<span class="onboarding-dot ${i === onboardingStepIndex ? "active" : ""}"></span>`)
    .join("");

  overlay.querySelector("#onboarding-next-btn").textContent = step.isLast ? t("onboarding_start_btn") : t("onboarding_next_btn");
}

// ------------------------------------------------------------
// Notificações toast — feedback discreto para ações (adicionar estudante,
// importar CSV, guardar previsão, etc.), sem bloquear a interface como o
// alert()/confirm() nativos. Aparecem no canto do ecrã, empilham-se se
// houver mais que uma, e desaparecem sozinhas passado um tempo (ou logo que
// se clica no "x").
// ------------------------------------------------------------

// Devolve o contentor de toasts, criando-o na primeira vez que é necessário.
function getToastContainer() {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.setAttribute("aria-live", "polite"); // leitores de ecrã anunciam novos toasts sem interromper
    document.body.appendChild(container);
  }
  return container;
}

function showToast(message, options = {}) {
  const { type = "info", duration = 4000 } = options;
  const container = getToastContainer();

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-dot"></span>
    <span class="toast-message">${escapeHtml(message)}</span>
    <button type="button" class="toast-close" aria-label="${escapeAttr(t("toast_close_aria"))}">&times;</button>
  `;
  container.appendChild(toast);

  let dismissed = false;
  const dismiss = () => {
    if (dismissed) return; // evita disparar a animação de saída duas vezes
    dismissed = true;
    toast.classList.add("toast-leaving");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
  };

  toast.querySelector(".toast-close").addEventListener("click", dismiss);
  setTimeout(dismiss, duration); // desaparece sozinho ao fim do tempo definido
  return dismiss; // devolve a função de fechar, para quem chamou poder fechar manualmente se quiser
}

// ------------------------------------------------------------
// Pequena celebração visual (micro-gamificação) — um punhado de pontos
// coloridos que saltam a partir de um elemento e desvanecem. Usada em
// momentos que merecem destaque sem exagerar: um marco redondo no número de
// estudantes do dataset (ver adddata.js) ou uma previsão que saiu melhor do
// que o esperado (ver prediction.js). Nunca bloqueia nada nem pede confirmação.
// ------------------------------------------------------------
function celebrate(anchorEl) {
  if (!anchorEl) return;
  const rect = anchorEl.getBoundingClientRect();
  celebrateAt(rect.left + rect.width / 2, rect.top + rect.height / 2);
}

// Variante que recebe diretamente um ponto do ecrã em vez de um elemento —
// útil quando o elemento de origem pode já ter sido removido do DOM (ex.:
// uma linha de tabela substituída por um refresh) entre o momento da ação e
// o momento de mostrar a celebração; nesse caso mede-se a posição ANTES do
// refresh e usa-se aqui.
function celebrateAt(originX, originY) {
  try {
    // Respeita a preferência de "movimento reduzido" do sistema operativo — não anima nada nesse caso.
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  } catch (_) { /* ignora */ }

  const pieceColors = [COLORS.primary, COLORS.positive, COLORS.primaryLight, "#F59E0B"];

  // Uma camada temporária, sobreposta a tudo, onde as partículas vão viver.
  const layer = document.createElement("div");
  layer.className = "celebrate-layer";
  document.body.appendChild(layer);

  const PIECES = 14;
  for (let i = 0; i < PIECES; i++) {
    const piece = document.createElement("span");
    piece.className = "celebrate-piece";
    // Distribui as partículas em círculo, com um pequeno desvio aleatório no ângulo e na distância.
    const angle = (Math.PI * 2 * i) / PIECES + Math.random() * 0.4;
    const distance = 55 + Math.random() * 45;
    piece.style.left = `${originX}px`;
    piece.style.top = `${originY}px`;
    piece.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
    piece.style.setProperty("--dy", `${Math.sin(angle) * distance - 25}px`);
    piece.style.background = pieceColors[i % pieceColors.length];
    layer.appendChild(piece);
  }

  setTimeout(() => layer.remove(), 900); // remove a camada depois da animação terminar
}

// ------------------------------------------------------------
// Router — troca de secção sem recarregar a página
// ------------------------------------------------------------
const PAGE_LOADERS = {}; // preenchido por cada js/pages/*.js via registerPage()

// Regista o loader de uma página; "loaded" começa false e é marcado true na primeira visita.
function registerPage(name, loaderFn) {
  PAGE_LOADERS[name] = { loaderFn, loaded: false };
}

// ------------------------------------------------------------
// Navegação com filtro pré-aplicado — usada quando se clica num elemento
// interativo de uma página (ex.: uma barra do gráfico "Taxa de aprovação por
// tempo de estudo" na Visão Geral) para ir diretamente para outra página já
// filtrada por esse valor, em vez de a pessoa ter de reaplicar o filtro à
// mão. Cada página que aceita filtros externos regista aqui um "handler"
// (ver registerPageFilterHandler, chamado a partir de profile.js/data.js).
// Se a página de destino ainda não tinha sido visitada, o filtro fica
// guardado (pendingNavFilter) para o próprio loader da página o consumir
// assim que arrancar — ver consumePendingNavFilter.
// ------------------------------------------------------------
const PAGE_FILTER_HANDLERS = {};
const pendingNavFilter = {};

function registerPageFilterHandler(name, fn) {
  PAGE_FILTER_HANDLERS[name] = fn;
}

// Consome (lê e remove) o filtro pendente de uma página — chamado uma única vez, no arranque dela.
function consumePendingNavFilter(name) {
  const filter = pendingNavFilter[name];
  delete pendingNavFilter[name];
  return filter;
}

function goToPage(name, filter) {
  // Trocar de página é sempre uma saída do "modo foco" do Esquema Mental
  // (menu escondido) — evita o menu ficar preso escondido se se navegar para
  // outra página a meio (ex.: reabrir o menu com o botão flutuante e escolher
  // logo outra página, sem passar pelo botão "Voltar" do editor).
  if (typeof setSidebarFocusMode === "function") setSidebarFocusMode(false);

  // Marca o item de menu correspondente como ativo, e mostra só a secção de página pedida.
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === name);
  });
  document.querySelectorAll(".page").forEach((section) => {
    section.classList.toggle("active", section.id === `page-${name}`);
  });

  // Quem faz scroll é a janela inteira (o conteúdo cresce dentro de .content,
  // sem scroll próprio) — sem isto, uma página nova abre exatamente na
  // posição em que a anterior tinha ficado, parecendo que abriu "lá em
  // baixo" sempre que se vinha de uma página mais comprida.
  window.scrollTo(0, 0);
  const contentEl = document.querySelector(".content");
  if (contentEl) contentEl.scrollTop = 0;

  const entry = PAGE_LOADERS[name];

  if (filter !== undefined) {
    if (entry && entry.loaded) {
      // Página já visitada antes: o loader não vai voltar a correr, por
      // isso aplica-se o filtro diretamente através do handler da página.
      const handler = PAGE_FILTER_HANDLERS[name];
      if (handler) handler(filter);
    } else {
      // Primeira visita: guarda-se o filtro para o loader da própria página
      // o ir buscar assim que arrancar (ver consumePendingNavFilter).
      pendingNavFilter[name] = filter;
    }
  }

  if (entry && !entry.loaded) {
    entry.loaded = true;
    try {
      const result = entry.loaderFn();
      // Se o loader falhar (ex: um botão em falta, um erro de rede), não
      // deixamos a página presa em "carregada mas por preencher" — mostramos
      // o erro na consola e voltamos a tentar da próxima vez que se navega
      // até aqui, em vez de a página ficar permanentemente partida.
      if (result && typeof result.catch === "function") {
        result.catch((err) => {
          console.error(`Erro ao carregar a página "${name}":`, err);
          entry.loaded = false;
        });
      }
    } catch (err) {
      console.error(`Erro ao carregar a página "${name}":`, err);
      entry.loaded = false;
    }
  }

}

document.addEventListener("DOMContentLoaded", () => {
  // Sequência de inicialização da app, corrida uma única vez quando o HTML está pronto.
  applySavedNavOrder();

  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => goToPage(btn.dataset.page));
  });

  initSidebarToggle();
  initSidebarFocusFab();
  initSidebarResize();
  initSidebarSections();
  initSidebarReorder();
  initDarkModeToggle();
  initZoomControls();
  initGlobalSearch();
  initPageHeaderInfo();
  checkApiHealth();
  loadAndApplyTheme();

  // Página inicial ao abrir a app — "home", exceto logo a seguir a uma
  // mudança de idioma (ver setLanguage em i18n.js), que recarrega a app
  // inteira e guarda aqui a página onde a pessoa estava, para reabrir no
  // mesmo sítio em vez de voltar sempre ao Início.
  let restorePage = null;
  try {
    restorePage = sessionStorage.getItem("studentperfomanceRestorePage");
    sessionStorage.removeItem("studentperfomanceRestorePage");
  } catch (_) { /* sessionStorage indisponível — segue para o Início, sem partir nada */ }
  goToPage(restorePage && PAGE_LOADERS[restorePage] ? restorePage : "home");
  startAutoRefresh();
});

// ------------------------------------------------------------
// Atualização automática — de tempos a tempos, refaz o pedido dos avisos e
// das estatísticas gerais em segundo plano, mesmo sem o utilizador mudar de
// página ou dar refresh manual. Se a contagem de avisos urgentes subir,
// atualiza o emblema da sidebar (visível em qualquer página) e avisa com um
// toast; se a página de Avisos e Alertas ou a Início estiverem visíveis
// nesse momento, o conteúdo é redesenhado com os dados novos. Um pequeno
// "Atualizado às HH:MM" junto ao estado da API mostra que a app está mesmo
// viva, sem ser preciso fazer nada.
// ------------------------------------------------------------
const AUTO_REFRESH_INTERVAL_MS = 90 * 1000; // a cada 90 segundos
let lastUrgentAlertCount = null; // guarda a última contagem, para detetar aumentos entre atualizações

// Verifica se uma dada página está atualmente visível no ecrã.
function isPageActive(name) {
  const section = document.getElementById(`page-${name}`);
  return !!section && section.classList.contains("active");
}

// Atualiza o texto "Atualizado às HH:MM" junto ao indicador de estado da API.
function updateLastRefreshedLabel() {
  const el = document.getElementById("sidebar-last-refresh");
  if (!el) return;
  const now = new Date();
  const dateLocale = getLanguage() === "en" ? "en-GB" : "pt-PT";
  const time = now.toLocaleTimeString(dateLocale, { hour: "2-digit", minute: "2-digit" });
  el.textContent = t("last_refreshed_label").replace("{time}", time);
}

async function autoRefreshTick() {
  try {
    // Pede em paralelo os alertas e as estatísticas atualizadas.
    const [alertsData, stats] = await Promise.all([Api.alerts(), Api.stats()]);
    AppCache["alerts"] = alertsData;
    AppCache["stats"] = stats;

    if (typeof updateSidebarAlertBadge === "function") updateSidebarAlertBadge(alertsData);

    // Compara a nova contagem de alertas urgentes com a anterior, para avisar só quando sobe.
    const urgentCount = alertsData.alerts ? alertsData.alerts.filter((a) => a.severity !== "info").length : 0;
    if (lastUrgentAlertCount !== null && urgentCount > lastUrgentAlertCount) {
      const novos = urgentCount - lastUrgentAlertCount;
      const key = novos === 1 ? "autorefresh_toast_one" : "autorefresh_toast_many";
      showToast(t(key).replace("{n}", novos), { type: "warning" });
    }
    lastUrgentAlertCount = urgentCount;

    // Só redesenha o conteúdo de uma página se ela estiver mesmo visível no momento.
    if (isPageActive("alerts") && typeof renderAlertsKpis === "function") {
      renderAlertsKpis(alertsData);
      renderAlertsList(alertsData.alerts);
      renderAtRiskTable(alertsData.at_risk_students);
    }
    if (isPageActive("home") && typeof loadHomeHeroStats === "function") {
      await loadHomeHeroStats();
    }
    updateLastRefreshedLabel();
  } catch (err) {
    console.error("Atualização automática falhou:", err);
  }
}

// Arranca o temporizador de atualização automática em segundo plano.
function startAutoRefresh() {
  setInterval(autoRefreshTick, AUTO_REFRESH_INTERVAL_MS);
}

// ------------------------------------------------------------
// Caixa de pesquisa global (sidebar) — escreve o nome de uma página, ou uma
// palavra relacionada com o que procuras, e Enter/clicar num resultado abre
// essa página logo, sem ser preciso saber em que grupo do menu está.
// ------------------------------------------------------------
// Índice de pesquisa: cada página tem um nome legível e uma lista de
// palavras-chave associadas (sinónimos, termos relacionados), para
// encontrar a página mesmo sem escrever o nome exato.
// "labelKey" aponta para a mesma chave nav_* usada no menu lateral (ver
// i18n.js), para o resultado de pesquisa mostrar sempre o nome traduzido
// da página, no idioma atual — nunca um "label" fixo em português.
const SEARCH_INDEX = [
  { page: "home", labelKey: "nav_home", keywords: "inicio home dashboard principal bem-vindo boas-vindas menu" },
  { page: "overview", labelKey: "nav_overview", keywords: "visao geral overview indicadores kpi notas distribuicao aprovacao reprovacao graficos estatisticas" },
  { page: "risk", labelKey: "nav_risk", keywords: "fatores risco risk habitos caracteristicas desempenho" },
  { page: "profile", labelKey: "nav_profile", keywords: "perfil estudante profile filtro filtrar comparar subgrupo media" },
  { page: "prediction", labelKey: "nav_prediction", keywords: "previsao notas prediction machine learning habitos estudo simular" },
  { page: "adddata", labelKey: "nav_adddata", keywords: "adicionar dados novo estudante inserir registar" },
  { page: "data", labelKey: "nav_data", keywords: "dados data explorador tabela filtros dataset" },
  { page: "alerts", labelKey: "nav_alerts", keywords: "avisos alertas warnings sinais atencao notificacoes" },
  { page: "segmentation", labelKey: "nav_segmentation", keywords: "segmentacao perfis kmeans clusters agrupamento grupos" },
  { page: "fichas", labelKey: "nav_fichas", keywords: "fichas desempenho pdf ficha individual relatorio recomendacao" },
  { page: "optimizer", labelKey: "nav_optimizer", keywords: "otimizador estudo optimizer nota alvo simulacao mudancas habitos" },
  { page: "customimport", labelKey: "nav_customimport", keywords: "importar dataset personalizado csv excel upload mapear colunas" },
  { page: "customstats", labelKey: "nav_customstats", keywords: "estatisticas graficos dataset personalizado colunas resumo" },
  { page: "custompredict", labelKey: "nav_custompredict", keywords: "previsoes dataset personalizado modelo notas aprovacao" },
  { page: "customtrain", labelKey: "nav_customtrain", keywords: "treinar modelo dataset personalizado machine learning" },
  { page: "customformula", labelKey: "nav_customformula", keywords: "formulas personalizadas dataset calculo expressao media soma coluna calculada excel" },
  { page: "settings", labelKey: "nav_settings", keywords: "configuracoes settings tema cor fonte letra" },
];

// Compara sem distinguir maiúsculas/minúsculas nem acentos (ex.: "previsao"
// tem de encontrar "Previsão de Notas") — o utilizador não devia ter de
// escrever acentos corretamente para encontrar uma página.
function normalizeSearchText(str) {
  return String(str || "")
    .toLowerCase()
    .normalize("NFD") // separa as letras dos seus acentos (forma decomposta)
    .replace(/[̀-ͯ]/g, ""); // remove os caracteres de acentuação isolados
}

// Procura no índice as páginas que correspondem à query, com uma pontuação
// de relevância (início do nome > nome contém > palavra-chave começa por > palavra-chave contém).
function searchPages(query) {
  const q = normalizeSearchText(query).trim();
  if (!q) return [];
  return SEARCH_INDEX
    .map((entry) => {
      const resolvedLabel = t(entry.labelKey);
      const label = normalizeSearchText(resolvedLabel);
      const keywords = normalizeSearchText(entry.keywords);
      let score = -1;
      if (label.startsWith(q)) score = 3;
      else if (label.includes(q)) score = 2;
      else if (keywords.split(" ").some((w) => w.startsWith(q))) score = 1.5;
      else if (keywords.includes(q)) score = 1;
      return { ...entry, label: resolvedLabel, score };
    })
    .filter((entry) => entry.score > -1)
    .sort((a, b) => b.score - a.score)
    .slice(0, 8); // limita a 8 resultados, para não sobrecarregar a lista
}

function initGlobalSearch() {
  const input = document.getElementById("sidebar-search-input");
  const results = document.getElementById("sidebar-search-results");
  if (!input || !results) return;

  let currentMatches = []; // resultados atualmente mostrados
  let activeIndex = -1; // índice do resultado destacado (navegação por teclado)

  // Aplica a classe "active" só ao resultado no índice atualmente selecionado.
  const updateActiveHighlight = () => {
    results.querySelectorAll(".sidebar-search-result").forEach((el, i) => {
      el.classList.toggle("active", i === activeIndex);
    });
  };

  const closeResults = () => {
    currentMatches = [];
    activeIndex = -1;
    results.innerHTML = "";
    results.classList.add("hidden");
  };

  // Navega para a página escolhida e limpa o campo/painel de resultados.
  const selectResult = (page) => {
    if (!page) return;
    goToPage(page);
    input.value = "";
    closeResults();
    input.blur();
  };

  const renderResults = () => {
    if (!input.value.trim()) { closeResults(); return; }
    const matches = searchPages(input.value);
    currentMatches = matches;
    activeIndex = matches.length ? 0 : -1; // pré-seleciona sempre o primeiro resultado

    if (!matches.length) {
      results.innerHTML = `<div class="sidebar-search-empty">${escapeHtml(t("search_no_results"))}</div>`;
      results.classList.remove("hidden");
      return;
    }
    results.innerHTML = matches.map((m) => `
      <button type="button" class="sidebar-search-result" data-page="${m.page}">${escapeHtml(m.label)}</button>
    `).join("");
    results.classList.remove("hidden");
    // mousedown (antes do blur do input) em vez de click — senão o painel
    // já se tinha fechado por perder o foco antes do clique ser processado.
    results.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("mousedown", (e) => { e.preventDefault(); selectResult(btn.dataset.page); });
    });
    updateActiveHighlight();
  };

  input.addEventListener("input", renderResults);
  input.addEventListener("focus", () => { if (input.value.trim()) renderResults(); });
  // Navegação por teclado: setas para mover a seleção, Enter para escolher, Escape para fechar.
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!currentMatches.length) return;
      activeIndex = (activeIndex + 1) % currentMatches.length; // avança e dá a volta no fim
      updateActiveHighlight();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!currentMatches.length) return;
      activeIndex = (activeIndex - 1 + currentMatches.length) % currentMatches.length; // recua e dá a volta no início
      updateActiveHighlight();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && currentMatches[activeIndex]) selectResult(currentMatches[activeIndex].page);
    } else if (e.key === "Escape") {
      closeResults();
      input.blur();
    }
  });

  // Clicar fora da caixa de pesquisa fecha o painel de resultados.
  document.addEventListener("click", (e) => {
    if (e.target.closest(".sidebar-search")) return;
    closeResults();
  });
}

// ------------------------------------------------------------
// Botão de informação em cada cabeçalho de página — a descrição/explicação
// que antes ficava sempre visível por baixo do título passa a viver dentro
// de uma pequena caixa (popover), só aberta quando se clica no ícone "i".
// Corre uma vez, sobre todos os "page-header" já presentes no HTML (todas
// as páginas da app já estão no DOM, só escondidas — ver goToPage()).
// ------------------------------------------------------------
function initPageHeaderInfo() {
  document.querySelectorAll(".page-header").forEach((header) => {
    const h1 = header.querySelector("h1");
    const p = header.querySelector("p");
    if (!h1 || !p) return;
    // Guarda a CHAVE de tradução do subtítulo (data-i18n, já presente no
    // HTML) em vez do texto já resolvido — assim o popover continua a
    // mostrar o texto certo mesmo que o idioma mude depois deste momento
    // (ver buildInfoButton, que passa a chamar t() no clique).
    const helpKey = p.getAttribute("data-i18n");
    const helpText = p.textContent;
    p.remove(); // remove o texto de ajuda original (fixo), passa a viver só no popover

    // Cria uma linha para o título e o botão de informação ficarem lado a lado.
    const row = document.createElement("div");
    row.className = "page-header-title-row";
    h1.replaceWith(row);
    row.appendChild(h1);
    row.appendChild(buildInfoButton(helpText, t("page_info_btn_label"), helpKey));
  });
}

// Constrói o botão de informação (ícone "i") partilhado pelo cabeçalho de
// cada página e por qualquer outro sítio que precise do mesmo padrão (ex.: a
// ajuda do Esquema Mental, ligada em mindmap.js). A caixa de texto (popover)
// já NÃO vive dentro deste botão — ver getGlobalInfoPopover() abaixo — porque
// o cabeçalho de cada página tem "overflow: hidden" (para conter os brilhos
// decorativos de fundo) e isso cortava a caixa sempre que o texto era um
// pouco mais comprido (ficava com o fundo a acabar a meio da frase). Em vez
// de mudar o "overflow" do cabeçalho (que faz parte do visual a manter), o
// popover passa a ser um único elemento partilhado, fora de qualquer
// cabeçalho, posicionado por posição fixa junto ao botão que foi clicado.
function buildInfoButton(helpText, label, helpKey) {
  const wrap = document.createElement("div");
  wrap.className = "page-info-wrap";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "page-info-btn";
  btn.title = label;
  btn.setAttribute("aria-label", label);
  // Ícone SVG de um "i" dentro de um círculo, desenhado inline (sem depender de biblioteca de ícones).
  btn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6.4"></circle><line x1="8" y1="7.2" x2="8" y2="11.3"></line><circle cx="8" cy="4.9" r="0.75" fill="currentColor" stroke="none"></circle></svg>`;
  btn.dataset.infoText = helpText;
  if (helpKey) btn.dataset.infoKey = helpKey; // permite reavaliar o texto no idioma atual a cada clique

  btn.addEventListener("click", (e) => {
    e.stopPropagation(); // não deixa este clique fechar imediatamente o popover pelo listener global
    const text = btn.dataset.infoKey ? t(btn.dataset.infoKey) : btn.dataset.infoText;
    toggleGlobalInfoPopover(btn, text);
  });

  wrap.appendChild(btn);
  return wrap;
}

// Popover único, partilhado por todos os botões de informação da app —
// vive diretamente no <body>, por isso nunca fica sujeito ao "overflow:
// hidden" de nenhum cabeçalho/cartão/painel. Ao abrir, mede o botão clicado
// (getBoundingClientRect) e posiciona-se logo abaixo dele, ajustando para
// nunca sair da janela visível (nem por baixo, nem pelos lados).
let globalInfoPopoverEl = null; // referência ao elemento do popover, criado uma única vez
let globalInfoPopoverOpenBtn = null; // botão que abriu o popover atualmente visível (se algum)

// Devolve o elemento do popover, criando-o na primeira chamada (padrão singleton).
function getGlobalInfoPopover() {
  if (globalInfoPopoverEl) return globalInfoPopoverEl;
  const el = document.createElement("div");
  el.className = "page-info-popover hidden";
  document.body.appendChild(el);
  globalInfoPopoverEl = el;
  return el;
}

// Calcula e aplica a posição do popover, logo abaixo do botão, sem sair da janela visível.
function positionGlobalInfoPopover(btn) {
  const popover = getGlobalInfoPopover();
  const rect = btn.getBoundingClientRect();
  // Mede depois de visível (max-width já se aplica) para saber a largura real.
  const popRect = popover.getBoundingClientRect();
  let left = rect.left;
  left = Math.min(left, window.innerWidth - popRect.width - 12); // não deixa sair pela direita
  left = Math.max(12, left); // nem pela esquerda
  let top = rect.bottom + 8;
  // Se não couber por baixo do botão (ex.: botão perto do fundo da janela),
  // mostra-se por cima em vez de ficar cortado no fundo do ecrã.
  if (top + popRect.height > window.innerHeight - 12 && rect.top - popRect.height - 8 > 12) {
    top = rect.top - popRect.height - 8;
  }
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function toggleGlobalInfoPopover(btn, helpText) {
  const popover = getGlobalInfoPopover();
  const wasOpenForThisBtn = !popover.classList.contains("hidden") && globalInfoPopoverOpenBtn === btn;
  popover.classList.add("hidden");
  globalInfoPopoverOpenBtn = null;
  if (wasOpenForThisBtn) return; // clicar de novo no mesmo botão fecha o popover (toggle)

  popover.textContent = helpText;
  popover.classList.remove("hidden");
  globalInfoPopoverOpenBtn = btn;
  positionGlobalInfoPopover(btn);
}

// Clicar fora do popover ou do botão que o abriu fecha-o.
document.addEventListener("click", (e) => {
  if (e.target.closest(".page-info-wrap") || e.target.closest(".page-info-popover")) return;
  const popover = getGlobalInfoPopover();
  popover.classList.add("hidden");
  globalInfoPopoverOpenBtn = null;
});
// Reposicionar em vez de deixar "descolado" do botão quando a janela muda de
// tamanho (ex.: redimensionar a janela da app) enquanto o popover está aberto.
window.addEventListener("resize", () => {
  if (globalInfoPopoverOpenBtn) positionGlobalInfoPopover(globalInfoPopoverOpenBtn);
});

// ------------------------------------------------------------
// Eliminar/descartar notificações (Avisos e Alertas, Prazos Próximos) — os
// avisos são calculados a cada pedido à API, nunca guardados como registos
// próprios, por isso "eliminar" um aviso guarda a sua "chave" no browser e
// filtra-o das próximas vezes que a lista for calculada (volta a aparecer
// se deixar de ser válido e mais tarde surgir outro aviso igual).
// ------------------------------------------------------------

// Gera uma chave curta e estável a partir do texto do aviso (hash simples), para o identificar depois.
function alertDismissKey(text) {
  let hash = 0;
  const str = String(text || "");
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0; // força o resultado a permanecer um inteiro de 32 bits
  }
  return `alert-${hash}`;
}

// Lê a lista de chaves de avisos dispensados, guardada em localStorage.
function getDismissedAlerts() {
  try {
    return JSON.parse(localStorage.getItem("dismissedAlerts") || "[]");
  } catch (_) {
    return [];
  }
}

function isAlertDismissed(key) {
  return getDismissedAlerts().includes(key);
}

function dismissAlert(key) {
  const dismissed = getDismissedAlerts();
  if (!dismissed.includes(key)) {
    dismissed.push(key);
    try { localStorage.setItem("dismissedAlerts", JSON.stringify(dismissed)); } catch (_) { /* ignora */ }
  }
}

// Ponto de quebra a partir do qual a sidebar deixa de empurrar o conteúdo e
// passa a um painel sobreposto (ver a secção "Responsividade" em style.css,
// que usa este mesmo valor em @media). Mantido num único sítio para nunca
// desalinhar o comportamento em JS do que a CSS decide mostrar.
const RESPONSIVE_SIDEBAR_BREAKPOINT = 860;
function isMobileViewport() {
  // Defensivo: em qualquer ambiente sem matchMedia (não deve acontecer em
  // navegadores modernos, mas mais vale prevenir — a app também corre
  // embutida numa janela nativa via pywebview), assume-se ecrã largo em vez
  // de deixar um erro aqui impedir o resto do arranque da aplicação.
  try {
    return window.matchMedia(`(max-width: ${RESPONSIVE_SIDEBAR_BREAKPOINT}px)`).matches;
  } catch (_) {
    return false;
  }
}

// ------------------------------------------------------------
// Abrir/fechar o menu lateral — o botão fica sempre visível na borda da
// sidebar. Em ecrã largo, o estado (aberto/só ícones) fica guardado no
// browser, para o menu continuar como o deixaste da próxima vez. Em ecrã
// estreito, o mesmo botão em vez disso abre/fecha o menu como um painel
// sobreposto (com fundo escurecido) — nunca ao mesmo tempo "sobreposto" e
// "só ícones", que seria uma combinação sem sentido nenhum.
// ------------------------------------------------------------
function initSidebarToggle() {
  const sidebar = document.getElementById("sidebar");
  const btn = document.getElementById("sidebar-toggle-btn");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!sidebar || !btn) return;

  // Aplica o estado colapsado/expandido e atualiza o texto acessível do botão.
  const applyState = (collapsed) => {
    sidebar.classList.toggle("collapsed", collapsed);
    const label = collapsed ? t("sidebar_open_label") : t("sidebar_close_label");
    btn.title = label;
    btn.setAttribute("aria-label", label);
  };

  let collapsed = false;
  try {
    collapsed = localStorage.getItem("sidebarCollapsed") === "true";
  } catch (_) { /* localStorage indisponível — assume menu aberto */ }
  applyState(collapsed);
  // Nunca começar em ecrã estreito já com o modo "só ícones" (a preferência
  // de desktop fica guardada na mesma para quando a janela voltar a crescer).
  if (isMobileViewport()) sidebar.classList.remove("collapsed");

  const closeMobileSidebar = () => {
    sidebar.classList.remove("sidebar-mobile-open");
    if (backdrop) backdrop.classList.remove("visible");
  };
  const openMobileSidebar = () => {
    sidebar.classList.add("sidebar-mobile-open");
    if (backdrop) backdrop.classList.add("visible");
  };
  // Exposta para outros pontos (ex.: clicar numa página do menu) poderem
  // fechar o painel sobreposto sem duplicar esta lógica.
  window.closeMobileSidebar = closeMobileSidebar;

  btn.addEventListener("click", () => {
    if (isMobileViewport()) {
      // Em ecrã estreito, o botão alterna o painel sobreposto em vez do modo "só ícones".
      if (sidebar.classList.contains("sidebar-mobile-open")) closeMobileSidebar();
      else openMobileSidebar();
      return;
    }
    const next = !sidebar.classList.contains("collapsed");
    applyState(next);
    try { localStorage.setItem("sidebarCollapsed", String(next)); } catch (_) { /* ignora */ }
  });

  if (backdrop) backdrop.addEventListener("click", closeMobileSidebar);

  // Escolher uma página num ecrã estreito fecha o painel sobreposto a
  // seguir — senão ficava a tapar o conteúdo depois de já teres escolhido.
  document.querySelectorAll(".nav-item").forEach((navBtn) => {
    navBtn.addEventListener("click", () => { if (isMobileViewport()) closeMobileSidebar(); });
  });

  // Se a janela crescer para lá do ponto de quebra com o painel ainda
  // aberto, fecha-o sozinho (volta ao comportamento normal de secretário).
  window.addEventListener("resize", () => {
    if (!isMobileViewport()) closeMobileSidebar();
  });
}

// ------------------------------------------------------------
// "Modo foco": esconde a sidebar por completo (nem a coluna só de ícones do
// estado "collapsed" normal — desaparece a 100%), deixando só um botão
// flutuante no canto superior esquerdo para a voltar a mostrar. Usado pelo
// editor do Esquema Mental (ver openMindmapEditor/backToGallery em
// mindmap.js) para dar o máximo de espaço possível ao canvas, como um
// programa de desenho (Figma, Miro). Qualquer troca de página normal
// (goToPage) sai automaticamente deste modo, para nunca ficar "preso".
// ------------------------------------------------------------
function setSidebarFocusMode(hidden) {
  const sidebar = document.getElementById("sidebar");
  const fab = document.getElementById("sidebar-expand-fab");
  if (!sidebar) return;
  sidebar.classList.toggle("fully-hidden", hidden);
  if (fab) fab.classList.toggle("visible", hidden);
  // Sem a sidebar a ocupar espaço, o limite de largura do conteúdo (pensado
  // para páginas normais, com menu visível) deixava uma faixa enorme vazia
  // à direita — ver .content.content-wide em style.css.
  const content = document.querySelector(".content");
  if (content) content.classList.toggle("content-wide", hidden);
  // O cabeçalho da página (ícone + título + descrição) também some no modo
  // foco — no editor do Esquema Mental a identidade já vive na barra fina do
  // topo (ver .mindmap-topbar), por isso o cabeçalho grande deixa de ser
  // preciso e só rouba altura ao canvas. Ver .page-header.page-header-hidden
  // em style.css e o ajuste de altura em .mindmap-canvas-wrap.
  const activeHeader = document.querySelector(".page.active .page-header");
  if (activeHeader) activeHeader.classList.toggle("page-header-hidden", hidden);
}
window.setSidebarFocusMode = setSidebarFocusMode; // exposta globalmente para outros ficheiros (ex.: mindmap.js)

function initSidebarFocusFab() {
  const fab = document.getElementById("sidebar-expand-fab");
  if (!fab) return;
  fab.addEventListener("click", () => setSidebarFocusMode(false));
}

// ------------------------------------------------------------
// Redimensionar o menu lateral — passar o rato sobre o limite direito da
// sidebar mostra o cursor de redimensionamento; arrastar aumenta/diminui a
// largura (entre um mínimo e um máximo, para o menu nunca ficar demasiado
// apertado nem ocupar espaço a mais). A largura escolhida fica guardada no
// browser, tal como o estado aberto/fechado. Só funciona com o menu aberto
// — colapsado tem largura fixa, só com ícones.
// ------------------------------------------------------------
function initSidebarResize() {
  const sidebar = document.getElementById("sidebar");
  const handle = document.getElementById("sidebar-resize-handle");
  if (!sidebar || !handle) return;

  const MIN_WIDTH = 200;
  const MAX_WIDTH = 420;
  const DEFAULT_WIDTH = 260;

  // Aplica a largura via variável CSS, usada pelo layout da sidebar.
  const applyWidth = (px) => {
    document.documentElement.style.setProperty("--sidebar-width", `${px}px`);
  };

  let saved = null;
  try { saved = parseInt(localStorage.getItem("sidebarWidth"), 10); } catch (_) { /* localStorage indisponível */ }
  if (saved && !Number.isNaN(saved)) {
    applyWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, saved)));
  }

  let dragging = false;
  let startX = 0;
  let startWidth = 0;

  const onPointerMove = (e) => {
    if (!dragging) return;
    // Nova largura = largura inicial + distância percorrida pelo rato, sempre dentro dos limites.
    const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + (e.clientX - startX)));
    applyWidth(next);
  };

  const stopDrag = () => {
    if (!dragging) return;
    dragging = false;
    sidebar.classList.remove("resizing");
    document.body.classList.remove("sidebar-resizing");
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", stopDrag);
    try { localStorage.setItem("sidebarWidth", String(Math.round(sidebar.getBoundingClientRect().width))); } catch (_) { /* ignora */ }
  };

  handle.addEventListener("pointerdown", (e) => {
    if (sidebar.classList.contains("collapsed")) return; // não redimensiona com o menu colapsado
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startWidth = sidebar.getBoundingClientRect().width;
    sidebar.classList.add("resizing");
    document.body.classList.add("sidebar-resizing");
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", stopDrag);
  });

  // Duplo clique no limite repõe a largura predefinida.
  handle.addEventListener("dblclick", () => {
    applyWidth(DEFAULT_WIDTH);
    try { localStorage.setItem("sidebarWidth", String(DEFAULT_WIDTH)); } catch (_) { /* ignora */ }
  });
}

// ------------------------------------------------------------
// Abrir/fechar cada grupo do menu (Análise de Dados, Avisos e Alertas,
// Ferramentas de Estudo, Configurações). Tal como o cronómetro Pomodoro,
// os grupos começam sempre fechados a cada arranque da aplicação — o estado
// aberto/fechado só é lembrado durante a sessão atual, não entre arranques.
// ------------------------------------------------------------

// Aplica o estado aberto/fechado a um grupo do menu (botão do título + lista de itens).
function setNavSectionCollapsed(labelBtn, itemsEl, key, collapsed) {
  labelBtn.classList.toggle("collapsed", collapsed);
  labelBtn.setAttribute("aria-expanded", String(!collapsed));
  itemsEl.classList.toggle("collapsed", collapsed);
}

function initSidebarSections() {
  document.querySelectorAll(".nav-section-label[data-section]").forEach((labelBtn) => {
    const key = labelBtn.dataset.section;
    const itemsEl = document.querySelector(`.nav-section-items[data-section-items="${key}"]`);
    if (!itemsEl) return;

    // Começa sempre fechado ao iniciar a app.
    setNavSectionCollapsed(labelBtn, itemsEl, key, true);

    labelBtn.addEventListener("click", () => {
      const collapsed = !labelBtn.classList.contains("collapsed");
      setNavSectionCollapsed(labelBtn, itemsEl, key, collapsed);
    });
  });
}

// ------------------------------------------------------------
// Reorganizar os submenus do menu lateral: cada item de cada secção tem uma
// pequena pega de arrastar (só visível ao passar o rato — ver .nav-drag-
// handle em style.css), sem precisar de nenhum interruptor à parte para
// ativar. Arrasta-se para cima/baixo DENTRO da mesma secção (não é possível
// mover um item para outra secção, só reordenar os já existentes ali). A
// ordem escolhida fica guardada no browser (localStorage), por isso persiste
// entre sessões mas é só deste computador/perfil, tal como a largura da
// sidebar ou o tema escuro.
// Usa Pointer Events (não o drag-and-drop nativo do HTML) para se comportar
// exatamente como o redimensionamento da sidebar acima — mais previsível
// dentro da janela da aplicação de secretária.
// ------------------------------------------------------------
const NAV_ORDER_STORAGE_KEY = "studentperfomanceNavOrderV1";

// Lê a ordem guardada de todas as secções (um objeto { secção: [ids...] }).
function loadNavOrder() {
  try {
    const raw = localStorage.getItem(NAV_ORDER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}

function saveNavOrder(order) {
  try { localStorage.setItem(NAV_ORDER_STORAGE_KEY, JSON.stringify(order)); } catch (_) { /* localStorage indisponível — só não persiste */ }
}

// Aplica, a cada arranque, a ordem guardada da última vez que o utilizador
// reorganizou o menu — corre antes de tudo o resto ligado à sidebar.
function applySavedNavOrder() {
  const order = loadNavOrder();
  document.querySelectorAll(".nav-section-items[data-section-items]").forEach((itemsEl) => {
    const key = itemsEl.dataset.sectionItems;
    const savedIds = order[key];
    if (!savedIds || !savedIds.length) return;
    const items = Array.from(itemsEl.children).filter((el) => el.classList.contains("nav-item"));
    const byId = new Map(items.map((el) => [el.dataset.page, el]));
    // Reinsere os itens pela ordem guardada, removendo-os do mapa à medida que são colocados.
    savedIds.forEach((id) => {
      const el = byId.get(id);
      if (el) {
        itemsEl.appendChild(el);
        byId.delete(id);
      }
    });
    // Itens que não estavam na ordem guardada (ex.: uma página nova,
    // acrescentada numa atualização depois da última vez que se reorganizou)
    // ficam no fim, pela ordem original — nunca desaparecem nem se perdem.
    byId.forEach((el) => itemsEl.appendChild(el));
  });
}

// Lê a ordem atual dos itens de uma secção do DOM e grava-a em localStorage.
function persistSectionOrder(itemsEl) {
  const key = itemsEl.dataset.sectionItems;
  if (!key) return;
  const ids = Array.from(itemsEl.children)
    .filter((el) => el.classList.contains("nav-item"))
    .map((el) => el.dataset.page);
  const order = loadNavOrder();
  order[key] = ids;
  saveNavOrder(order);
}

function initSidebarReorder() {
  document.querySelectorAll(".nav-section-items[data-section-items]").forEach((itemsEl) => {
    Array.from(itemsEl.children).filter((el) => el.classList.contains("nav-item")).forEach((item) => {
      // Adiciona a pega de arrastar (ícone de 6 pontos) no início de cada item de menu.
      const handle = document.createElement("span");
      handle.className = "nav-drag-handle";
      handle.title = t("nav_drag_handle_title");
      handle.setAttribute("aria-hidden", "true");
      handle.innerHTML = `<svg viewBox="0 0 10 16"><circle cx="2.5" cy="3" r="1.1"></circle><circle cx="7.5" cy="3" r="1.1"></circle><circle cx="2.5" cy="8" r="1.1"></circle><circle cx="7.5" cy="8" r="1.1"></circle><circle cx="2.5" cy="13" r="1.1"></circle><circle cx="7.5" cy="13" r="1.1"></circle></svg>`;
      item.insertBefore(handle, item.firstChild);

      // Um clique isolado na pega (sem arrastar) não deve navegar para a
      // página — a pega serve só para arrastar.
      handle.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); });

      let dragging = false;
      let moved = false; // só true depois de o rato se mover o suficiente (distingue clique de arrasto)
      let startY = 0;

      handle.addEventListener("pointerdown", (e) => {
        if (e.button !== undefined && e.button !== 0) return; // só o botão esquerdo do rato
        e.preventDefault();
        e.stopPropagation();
        dragging = true;
        moved = false;
        startY = e.clientY;
        try { handle.setPointerCapture(e.pointerId); } catch (_) { /* ignora */ }
      });

      handle.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        if (!moved && Math.abs(e.clientY - startY) > 3) {
          // Só considera "a arrastar" depois de um pequeno limiar de movimento (evita cliques acidentais).
          moved = true;
          item.classList.add("nav-item-dragging");
          document.body.classList.add("nav-reordering");
        }
        if (!moved) return;
        // Descobre sobre que outro item da MESMA secção o rato está, e troca
        // de posição em tempo real — arrastar para cima ou para baixo do
        // ponto médio do item alvo decide se fica antes ou depois dele.
        const siblings = Array.from(itemsEl.children).filter((el) => el.classList.contains("nav-item") && el !== item);
        const target = siblings.find((el) => {
          const r = el.getBoundingClientRect();
          return e.clientY >= r.top && e.clientY <= r.bottom;
        });
        if (target) {
          const targetRect = target.getBoundingClientRect();
          const before = e.clientY < targetRect.top + targetRect.height / 2;
          itemsEl.insertBefore(item, before ? target : target.nextSibling);
        }
      });

      const endDrag = (e) => {
        if (!dragging) return;
        dragging = false;
        try { handle.releasePointerCapture(e.pointerId); } catch (_) { /* ignora */ }
        document.body.classList.remove("nav-reordering");
        if (moved) {
          item.classList.remove("nav-item-dragging");
          persistSectionOrder(itemsEl); // guarda a nova ordem só se realmente houve arrasto
        }
      };
      handle.addEventListener("pointerup", endDrag);
      handle.addEventListener("pointercancel", endDrag);
    });
  });
}

// ------------------------------------------------------------
// Tema e fonte (Configurações) — aplicados globalmente ao arrancar,
// para se manterem em qualquer página da aplicação.
// ------------------------------------------------------------
window.APP_THEMES = []; // lista de temas disponíveis, carregada da API e partilhada globalmente

async function loadAndApplyTheme() {
  try {
    const [settings, themesData] = await Promise.all([Api.getSettings(), Api.themes()]);
    window.APP_THEMES = themesData.themes;
    applyTheme(settings.theme);
    applyFont(settings.font);
  } catch (err) {
    console.error("Não foi possível carregar o tema:", err);
  }
}

window.APP_CURRENT_THEME = null; // id do tema atualmente aplicado, para outras páginas (ex.: settings.js) consultarem

function applyTheme(themeId) {
  const theme = (window.APP_THEMES || []).find((t) => t.id === themeId);
  if (!theme) return;
  // Aplica cada cor do tema como uma variável CSS na raiz do documento.
  Object.entries(theme.colors).forEach(([key, value]) => {
    document.documentElement.style.setProperty(key, value);
  });
  // Diz ao Chromium se deve desenhar os controlos nativos (ícone do
  // calendário/relógio nos campos de data/hora, scrollbars, checkboxes) no
  // estilo claro ou escuro — sem isto, esses elementos ficavam sempre claros
  // mesmo com um tema escuro aplicado, por não seguirem as variáveis CSS.
  document.documentElement.style.colorScheme = theme.mode === "escuro" ? "dark" : "light";
  window.APP_CURRENT_THEME = themeId;
  updateDarkModeButton(theme.mode);
}

function applyFont(font) {
  document.body.style.fontFamily = `'${font}', sans-serif`;
}

// ------------------------------------------------------------
// Botão rápido de modo escuro — alterna entre o último tema claro e o
// último tema escuro usados (guardados no browser), sem ser preciso ir a
// Configurações. A escolha fica também guardada no servidor (/settings),
// tal como qualquer troca de tema feita em Configurações.
// ------------------------------------------------------------

// Atualiza o texto/estado visual do botão de modo escuro consoante o modo atual.
function updateDarkModeButton(mode) {
  const btn = document.getElementById("dark-mode-toggle-btn");
  if (!btn) return;
  const isDark = mode === "escuro";
  btn.textContent = isDark ? t("darkmode_to_light_btn") : t("darkmode_to_dark_btn"); // mostra a ação seguinte, não o estado atual
  btn.classList.toggle("active", isDark);
  const label = isDark ? t("darkmode_to_light_title") : t("darkmode_to_dark_title");
  btn.title = label;
  btn.setAttribute("aria-label", label);
}

async function toggleDarkMode() {
  const themes = window.APP_THEMES || [];
  const current = themes.find((t) => t.id === window.APP_CURRENT_THEME);
  const currentlyDark = !!current && current.mode === "escuro";

  let nextThemeId;
  try {
    if (currentlyDark) {
      // A ir para claro: memoriza o tema escuro atual, e recupera o último tema claro usado.
      localStorage.setItem("lastDarkTheme", window.APP_CURRENT_THEME);
      nextThemeId = localStorage.getItem("lastLightTheme") || "indigo";
    } else {
      // A ir para escuro: memoriza o tema claro atual, e recupera o último tema escuro usado.
      localStorage.setItem("lastLightTheme", window.APP_CURRENT_THEME || "indigo");
      nextThemeId = localStorage.getItem("lastDarkTheme") || "escuro_indigo";
    }
  } catch (_) {
    // Sem localStorage disponível, usa sempre os temas por omissão de cada modo.
    nextThemeId = currentlyDark ? "indigo" : "escuro_indigo";
  }

  applyTheme(nextThemeId);
  try {
    await Api.saveSettings({ theme: nextThemeId });
  } catch (err) {
    console.error("Não foi possível guardar o tema:", err);
  }
}

function initDarkModeToggle() {
  const btn = document.getElementById("dark-mode-toggle-btn");
  if (!btn) return;
  btn.addEventListener("click", toggleDarkMode);
}

// ------------------------------------------------------------
// Zoom da aplicação — escala o tamanho de letra base; como quase todo o
// CSS usa "rem", isto amplia/reduz a interface quase por completo.
// ------------------------------------------------------------
const ZOOM_STEPS = [75, 85, 100, 115, 130, 145, 160]; // níveis de zoom disponíveis, em percentagem
let currentZoomIndex = ZOOM_STEPS.indexOf(100); // começa sempre no nível 100%

// Aplica a percentagem de zoom ao tamanho de letra da página inteira e guarda a escolha.
function applyZoom(percent) {
  document.documentElement.style.fontSize = `${percent}%`;
  const label = document.getElementById("zoom-reset-btn");
  if (label) label.textContent = `${percent}%`;
  try { localStorage.setItem("uiZoomPercent", String(percent)); } catch (_) { /* ignora */ }
}

function initZoomControls() {
  const outBtn = document.getElementById("zoom-out-btn");
  const inBtn = document.getElementById("zoom-in-btn");
  const resetBtn = document.getElementById("zoom-reset-btn");
  if (!outBtn || !inBtn || !resetBtn) return;

  let saved = 100;
  try {
    const stored = parseInt(localStorage.getItem("uiZoomPercent"), 10);
    if (ZOOM_STEPS.includes(stored)) saved = stored;
  } catch (_) { /* ignora */ }
  currentZoomIndex = ZOOM_STEPS.indexOf(saved) !== -1 ? ZOOM_STEPS.indexOf(saved) : ZOOM_STEPS.indexOf(100);
  applyZoom(ZOOM_STEPS[currentZoomIndex]);

  outBtn.addEventListener("click", () => {
    currentZoomIndex = Math.max(0, currentZoomIndex - 1); // nunca desce abaixo do primeiro nível
    applyZoom(ZOOM_STEPS[currentZoomIndex]);
  });
  inBtn.addEventListener("click", () => {
    currentZoomIndex = Math.min(ZOOM_STEPS.length - 1, currentZoomIndex + 1); // nunca sobe além do último nível
    applyZoom(ZOOM_STEPS[currentZoomIndex]);
  });
  resetBtn.addEventListener("click", () => {
    currentZoomIndex = ZOOM_STEPS.indexOf(100);
    applyZoom(100);
  });
}

// Verifica se a API está a responder e mostra o estado (ligada/não encontrada) na sidebar,
// incluindo o número total de estudantes quando a ligação tem sucesso.
async function checkApiHealth() {
  const badge = document.getElementById("sidebar-status");
  try {
    await Api.health();
    const stats = await cached("stats", Api.stats);
    badge.textContent = t("api_health_connected").replace("{n}", stats.n_students);
    badge.className = "status-badge status-ok";
  } catch (err) {
    badge.textContent = t("api_health_error");
    badge.className = "status-badge status-error";
    badge.title = t("api_health_error_title");
  }
}

// ------------------------------------------------------------
// Escapar texto para HTML — usado sempre que se insere texto vindo do
// utilizador ou dos dados (nomes, rótulos, etiquetas) dentro de innerHTML,
// para nunca deixar passar tags/scripts por acidente. Vive aqui (main.js,
// carregado antes de todas as páginas) precisamente para ser um utilitário
// verdadeiramente partilhado — antes vivia só em notes.js (Central de
// Notas), o que deixou de fazer sentido depois de essa página ter sido
// removida por estar fora do âmbito do trabalho, já que várias outras
// páginas (Perfil do Estudante, Adicionar Dados, Previsão, Fatores de
// Risco) continuam a precisar destas duas funções.
// ------------------------------------------------------------
// Escapa texto para uso seguro dentro do conteúdo HTML (entre tags).
function escapeHtml(str) {
  return String(str || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
// Escapa texto para uso seguro dentro de um atributo HTML (ex.: title="...", também escapa aspas).
function escapeAttr(str) {
  return String(str || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ------------------------------------------------------------
// Utilitários de formatação
// ------------------------------------------------------------
// Formata um número com um dado nº de casas decimais; devolve "–" para valores em falta/inválidos.
function fmtNum(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return Number(value).toFixed(decimals);
}
// Formata uma fração (0-1) como percentagem com símbolo "%".
function fmtPct(value, decimals = 1) {
  if (value === null || value === undefined) return "–";
  return `${(value * 100).toFixed(decimals)}%`;
}

// ------------------------------------------------------------
// Animação de contagem — em vez de um número aparecer estático, conta a
// subir/descer até ao valor final. Funciona com qualquer texto que comece
// por um número (ex.: "14.2 / 20", "72%", "312") — só a parte numérica
// anima, o resto do texto (sufixo) fica sempre igual. Se o elemento já
// tinha um valor animado antes (ver dataset.animValue), a próxima contagem
// parte desse valor em vez de partir sempre de zero — importante para os
// KPIs que se atualizam sozinhos (ver startAutoRefresh).
// ------------------------------------------------------------
function animateNumberText(el, text, duration = 700) {
  if (!el) return;
  const str = String(text ?? "");
  // Extrai a parte numérica inicial da string (incluindo sinal negativo e separadores).
  const match = str.match(/^-?\d[\d.,]*/);
  if (!match) {
    // Texto sem número no início (ex.: "–") — mostra tal como está, sem animar.
    el.textContent = str;
    delete el.dataset.animValue;
    return;
  }

  const numStr = match[0];
  const suffix = str.slice(numStr.length); // resto do texto após o número (ex.: " / 20", "%")
  const decimals = numStr.includes(".") ? numStr.split(".")[1].length : 0;
  const target = parseFloat(numStr.replace(/,/g, ""));
  if (Number.isNaN(target)) {
    el.textContent = str;
    delete el.dataset.animValue;
    return;
  }

  let reduceMotion = false;
  try {
    reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (_) { /* ignora */ }
  if (reduceMotion) {
    // Preferência de acessibilidade "movimento reduzido": mostra o valor final direto, sem animação.
    el.textContent = `${target.toFixed(decimals)}${suffix}`;
    el.dataset.animValue = String(target);
    return;
  }

  // Parte do último valor animado guardado (se existir), senão de zero.
  const previous = parseFloat(el.dataset.animValue ?? "");
  const start = Number.isNaN(previous) ? 0 : previous;
  const startTime = performance.now();

  function tick(now) {
    const progress = Math.min(1, (now - startTime) / duration);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cúbico: começa rápido, desacelera no fim
    const current = start + (target - start) * eased;
    el.textContent = `${current.toFixed(decimals)}${suffix}`;
    if (progress < 1) {
      requestAnimationFrame(tick);
    } else {
      // Garante que o valor final fica exato (sem arredondamentos residuais da animação).
      el.textContent = `${target.toFixed(decimals)}${suffix}`;
      el.dataset.animValue = String(target);
    }
  }
  requestAnimationFrame(tick);
}

// ------------------------------------------------------------
// Construtor de cartões KPI — o valor de cada cartão entra em branco e
// "conta" até ao número final (ver animateNumberText), em vez de aparecer
// estático de imediato.
// ------------------------------------------------------------
function renderKpiCards(containerId, items) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  items.forEach(({ label, value, delta, deltaPositive }) => {
    const card = document.createElement("div");
    card.className = "kpi-card";
    card.innerHTML = `
      <div class="kpi-label">${label}</div>
      <div class="kpi-value"></div>
      ${delta ? `<div class="kpi-delta ${deltaPositive ? "positive" : "negative"}">${delta}</div>` : ""}
    `;
    container.appendChild(card);
    animateNumberText(card.querySelector(".kpi-value"), value);
  });
}

// ------------------------------------------------------------
// Skeleton loaders — placeholders animados mostrados enquanto os dados de
// uma página ainda não chegaram da API, em vez de um espaço em branco por
// um instante (ver .skeleton em style.css, já usado antes só na
// Segmentação de Perfis — agora reaproveitado de forma genérica).
// ------------------------------------------------------------
function showSkeletonPlaceholders(containerId, options = {}) {
  const { count = 3, cardClass = "kpi-card", height } = options;
  const container = document.getElementById(containerId);
  if (!container) return;
  const style = height ? ` style="height:${height}"` : "";
  // Gera "count" divs vazias, com a classe do cartão + "skeleton" (a animação vem do CSS).
  container.innerHTML = Array.from({ length: count })
    .map(() => `<div class="${cardClass} skeleton"${style}></div>`)
    .join("");
}

// ------------------------------------------------------------
// Gauge circular (conic-gradient) usado na página de Previsão
// ------------------------------------------------------------
function setGauge(elementId, valueId, percent, colorStops) {
  const gauge = document.getElementById(elementId);
  const valueEl = document.getElementById(valueId);
  // Converte a percentagem (0-100) em graus (0-360) para o gradiente cónico.
  const deg = Math.max(0, Math.min(100, percent)) * 3.6;
  gauge.style.background = `conic-gradient(${colorStops} ${deg}deg, var(--border) ${deg}deg 360deg)`;
}

// ------------------------------------------------------------
// Cor para célula do heatmap de correlação (escala diverging azul-vermelho)
// ------------------------------------------------------------
function correlationColor(value) {
  // value entre -1 e 1
  const v = Math.max(-1, Math.min(1, value));
  if (v >= 0) {
    // branco -> vermelho: correlação positiva
    const intensity = Math.round(v * 255);
    return `rgb(255, ${255 - intensity}, ${255 - intensity})`;
  } else {
    // branco -> azul: correlação negativa
    const intensity = Math.round(-v * 255);
    return `rgb(${255 - intensity}, ${255 - intensity}, 255)`;
  }
}

// ------------------------------------------------------------
// Estilo partilhado para gráficos Chart.js (aspeto minimalista)
// ------------------------------------------------------------
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.color = COLORS.muted;
Chart.defaults.borderColor = COLORS.border;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
