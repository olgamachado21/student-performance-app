// ============================================================
// Assistente da StudentPerfomance — janela de conversa flutuante (frontend).
// Fala com POST /chatbot/ask (ver src/chatbot.py): um motor baseado em
// regras, sem LLM externo, que responde sempre com dados reais e atuais
// do dataset. Disponível em qualquer página da app. Interface minimalista
// de propósito: sem lista de perguntas sugeridas — só o campo de escrita.
// ============================================================

// Estado global simples: se o painel já foi aberto uma vez (para não repetir
// a mensagem de boas-vindas), e se há um pedido em curso (evita duplo envio).
let chatbotOpened = false;
let chatbotBusy = false;

function initChatbot() {
  const fab = document.getElementById("chatbot-fab"); // botão flutuante (Floating Action Button)
  const panel = document.getElementById("chatbot-panel");
  const closeBtn = document.getElementById("chatbot-panel-close");
  const form = document.getElementById("chatbot-form");
  const input = document.getElementById("chatbot-input");
  if (!fab || !panel || !form || !input) return; // elementos não existem nesta versão do HTML

  fab.addEventListener("click", () => toggleChatbotPanel());
  closeBtn.addEventListener("click", () => setChatbotOpen(false));

  // Tecla Escape fecha o painel, mas só se já estiver aberto.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panel.classList.contains("open")) setChatbotOpen(false);
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault(); // impede o recarregamento da página que um <form> normal faria
    const question = input.value.trim();
    if (!question || chatbotBusy) return; // ignora perguntas vazias ou envio duplicado
    input.value = "";
    sendChatbotQuestion(question);
  });

  // Pequeno indicador convidando a experimentar o assistente, na primeira
  // vez que a app carrega — desaparece assim que se abre o painel.
  const badge = document.getElementById("chatbot-fab-badge");
  if (badge) {
    setTimeout(() => {
      if (!chatbotOpened) {
        badge.textContent = "?";
        badge.classList.remove("hidden");
      }
    }, 1800);
  }
}

// Alterna o painel entre aberto/fechado, consoante o estado atual.
function toggleChatbotPanel() {
  const panel = document.getElementById("chatbot-panel");
  setChatbotOpen(!panel.classList.contains("open"));
}

function setChatbotOpen(open) {
  const panel = document.getElementById("chatbot-panel");
  const fab = document.getElementById("chatbot-fab");
  const badge = document.getElementById("chatbot-fab-badge");
  if (!panel) return;

  panel.classList.toggle("open", open);
  panel.classList.toggle("hidden", !open);
  if (fab) fab.classList.toggle("chatbot-fab-active", open); // destaca o botão enquanto o painel está aberto

  if (open) {
    if (badge) badge.classList.add("hidden"); // esconde o indicador "?" assim que se abre
    if (!chatbotOpened) {
      // Primeira vez que se abre: mostra a mensagem de boas-vindas do assistente.
      chatbotOpened = true;
      appendChatbotMessage(
        "assistant",
        "Olá! Sou o assistente da StudentPerfomance. Escreve a tua pergunta abaixo — os dados vêm sempre do dataset atual, nunca inventados."
      );
    }
    // Foca automaticamente o campo de texto, com um pequeno atraso para
    // garantir que a animação de abertura do painel já começou.
    const input = document.getElementById("chatbot-input");
    if (input) setTimeout(() => input.focus(), 50);
  }
}

// Adiciona uma "bolha" de mensagem (utilizador ou assistente) ao histórico da conversa.
function appendChatbotMessage(role, text) {
  const messages = document.getElementById("chatbot-messages");
  if (!messages) return null;
  const bubble = document.createElement("div");
  bubble.className = `chatbot-msg chatbot-msg-${role}`;
  // Escapa o texto (evita injeção de HTML) e depois converte quebras de linha em <br>.
  bubble.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight; // desloca sempre para a mensagem mais recente
  return bubble;
}

// Mostra uma bolha com 3 pontinhos animados, simulando "o assistente está a escrever".
function appendChatbotTyping() {
  const messages = document.getElementById("chatbot-messages");
  if (!messages) return null;
  const bubble = document.createElement("div");
  bubble.className = "chatbot-msg chatbot-msg-assistant chatbot-msg-typing";
  bubble.innerHTML = `<span class="chatbot-typing-dot"></span><span class="chatbot-typing-dot"></span><span class="chatbot-typing-dot"></span>`;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

async function sendChatbotQuestion(question) {
  chatbotBusy = true;
  const sendBtn = document.getElementById("chatbot-send-btn");
  if (sendBtn) sendBtn.disabled = true; // evita cliques repetidos enquanto aguarda resposta

  appendChatbotMessage("user", question);
  const typingBubble = appendChatbotTyping();

  try {
    const result = await Api.chatbotAsk(question);
    if (typingBubble) typingBubble.remove(); // remove os pontinhos assim que a resposta chega
    appendChatbotMessage("assistant", result.answer || "Não consegui obter uma resposta.");
  } catch (err) {
    console.error("Erro ao perguntar ao assistente:", err);
    if (typingBubble) typingBubble.remove();
    appendChatbotMessage("assistant", "Não consegui responder agora — confirma que a API está a correr e tenta novamente.");
    showToast("Não foi possível contactar o assistente.", { type: "error" });
  } finally {
    chatbotBusy = false;
    if (sendBtn) sendBtn.disabled = false;
  }
}

// O chatbot inicializa-se assim que o HTML estiver totalmente carregado,
// independentemente de qual página da app estiver aberta (é global).
document.addEventListener("DOMContentLoaded", initChatbot);
