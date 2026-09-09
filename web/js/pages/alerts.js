// ============================================================
// Página: Avisos e Alertas
// Mostra os alertas automáticos gerados pelo backend (src/alerts.py) e a
// tabela de estudantes atualmente classificados como "em risco".
// ============================================================

registerPage("alerts", async () => {
  // Mostra 2 placeholders animados enquanto os KPIs carregam.
  showSkeletonPlaceholders("alerts-kpis", { count: 2 });
  try {
    // Usa cache para evitar pedidos repetidos à API sempre que se volta a esta página.
    const data = await cached("alerts", Api.alerts);
    renderAlertsKpis(data);
    renderAlertsList(data.alerts);
    renderAtRiskTable(data.at_risk_students);
    updateSidebarAlertBadge(data);
  } catch (err) {
    console.error(err);
    document.getElementById("alerts-kpis").innerHTML =
      `<div class="info-box">Não foi possível carregar os avisos. Confirma que a API está a correr.</div>`;
  }
});

function renderAlertsKpis(data) {
  // Dois cartões de resumo: contagem absoluta e percentagem de estudantes em risco.
  renderKpiCards("alerts-kpis", [
    { label: "Estudantes em risco", value: data.n_at_risk },
    { label: "Taxa de risco", value: fmtPct(data.risk_rate) },
  ]);
}

function renderAlertsList(alerts) {
  const container = document.getElementById("alerts-list");
  // Filtra os alertas que o utilizador já dispensou anteriormente (guardados em localStorage).
  const visible = alerts.filter((a) => !isAlertDismissed(alertDismissKey(a.title + a.description)));

  if (visible.length === 0) {
    container.innerHTML = `<div class="info-box">Sem avisos por agora.</div>`;
    return;
  }

  // Gera um cartão por alerta, com cor/severidade, texto, botão de ação
  // opcional (navega para outra página) e botão de eliminar notificação.
  container.innerHTML = visible.map((a) => {
    const key = alertDismissKey(a.title + a.description);
    return `
      <div class="alert-card severity-${a.severity}">
        <div class="alert-icon severity-${a.severity}"></div>
        <div class="alert-body">
          <div class="alert-title">${a.title}</div>
          <div class="alert-description">${a.description}</div>
          ${a.action_page ? `<button class="alert-action" data-target="${a.action_page}">${a.action_label} →</button>` : ""}
        </div>
        <span class="severity-pill severity-${a.severity}">${a.severity}</span>
        <button class="alert-dismiss-btn" data-dismiss-alert="${key}" type="button" title="Eliminar notificação" aria-label="Eliminar notificação">&times;</button>
      </div>
    `;
  }).join("");

  // Botões de ação (ex.: "Ver estudantes →") navegam para a página indicada.
  container.querySelectorAll(".alert-action").forEach((btn) => {
    btn.addEventListener("click", () => goToPage(btn.dataset.target));
  });
  // Botões de eliminar: marcam o alerta como dispensado (persistente), removem
  // o cartão do DOM sem recarregar a página, e mostram a mensagem "sem avisos"
  // se a lista ficar vazia.
  container.querySelectorAll("[data-dismiss-alert]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation(); // não deixa o clique "atravessar" para o cartão inteiro
      dismissAlert(btn.dataset.dismissAlert);
      const card = btn.closest(".alert-card");
      if (card) card.remove();
      if (!container.querySelector(".alert-card")) {
        container.innerHTML = `<div class="info-box">Sem avisos por agora.</div>`;
      }
    });
  });
}

function renderAtRiskTable(students) {
  const tbody = document.querySelector("#alerts-table tbody");
  // Uma linha por estudante em risco, com os campos mais relevantes para diagnóstico rápido.
  const rows = students.map((s) => `
    <tr>
      <td>${s.student_id}</td>
      <td>${s.sex}</td>
      <td>${s.age}</td>
      <td>${s.studytime}</td>
      <td>${s.absences}</td>
      <td>${s.failures}</td>
      <td>${s.G3}</td>
      <td><button type="button" class="table-note-btn" data-note-student="${s.student_id}">+ nota</button></td>
    </tr>
  `).join("");
  // Se não houver estudantes em risco, mostra uma linha única de aviso em vez de tabela vazia.
  tbody.innerHTML = rows || `<tr><td colspan="8">Sem estudantes em risco.</td></tr>`;
  // Comentários (ver openStudentNotesModal em main.js): abre o modal já com
  // o contexto "Estudantes em risco", para se saber que o comentário nasceu
  // aqui e não de uma anotação livre no Perfil do Estudante.
  tbody.querySelectorAll("[data-note-student]").forEach((btn) => {
    btn.addEventListener("click", () => openStudentNotesModal(btn.dataset.noteStudent, "Estudantes em risco (Avisos e Alertas)"));
  });
}

// Cria, atualiza ou remove o emblema de contagem no item "Avisos e Alertas"
// do menu lateral — chamado tanto ao abrir a página como pela atualização
// automática em segundo plano (ver startAutoRefresh em main.js), por isso
// tem de refletir sempre a contagem mais recente, não só a da primeira vez.
function updateSidebarAlertBadge(data) {
  const navItem = document.querySelector('.nav-item[data-page="alerts"]');
  if (!navItem) return;
  // Só conta alertas que não sejam meramente informativos (urgente/aviso).
  const urgentCount = data.alerts ? data.alerts.filter((a) => a.severity !== "info").length : 0;

  let badge = navItem.querySelector(".nav-badge");
  if (urgentCount <= 0) {
    // Sem alertas urgentes: remove o emblema, se existir.
    if (badge) badge.remove();
    return;
  }
  if (!badge) {
    // Ainda não existe o elemento do emblema: cria-o e adiciona ao item do menu.
    badge = document.createElement("span");
    badge.className = "nav-badge";
    navItem.appendChild(badge);
  }
  badge.textContent = urgentCount;
}
