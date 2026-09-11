// ============================================================
// Página: Fichas de Desempenho (PDF)
// Permite descarregar a ficha PDF individual de um estudante (pelo ID),
// o relatório agregado da turma, e um ZIP com fichas em lote dos
// estudantes em risco.
// ============================================================

registerPage("fichas", async () => {
  // Botão, campo de input do ID do estudante e área de mensagens de erro.
  const btn = document.getElementById("ficha-generate-btn");
  const input = document.getElementById("ficha-student-id");
  const preview = document.getElementById("ficha-preview");

  btn.addEventListener("click", () => {
    // Converte o valor do input em número inteiro (base 10).
    const studentId = parseInt(input.value, 10);
    if (!studentId || studentId < 1) {
      // ID inválido (vazio, não numérico ou <= 0): mostra mensagem de erro em vez de tentar descarregar.
      preview.textContent = t("ficha_invalid_id");
      preview.classList.remove("hidden");
      return;
    }
    // Esconde qualquer mensagem de erro anterior e inicia o download da ficha PDF.
    preview.classList.add("hidden");
    downloadFileFrom(Api.fichaUrl(studentId), `ficha_estudante_${studentId}.pdf`);
  });

  // Relatório da turma (PDF agregado) — Ideia 2.
  const classReportBtn = document.getElementById("class-report-btn");
  if (classReportBtn) {
    // Botão opcional (só existe se o elemento estiver presente no HTML).
    classReportBtn.addEventListener("click", () => {
      downloadFileFrom(Api.classReportUrl(), "relatorio_turma.pdf");
    });
  }

  // Geração de fichas em lote (ZIP com todos os estudantes em risco) — Ideia 3.
  const fichasLoteBtn = document.getElementById("fichas-lote-btn");
  if (fichasLoteBtn) {
    fichasLoteBtn.addEventListener("click", () => {
      // true = só estudantes em risco; 100 = limite máximo de fichas no ZIP.
      downloadFileFrom(Api.fichasLoteUrl(true, 100), "fichas_desempenho.zip");
    });
  }
});

// Cria um link <a> temporário e "clica" nele programaticamente para forçar
// o download do ficheiro no URL indicado, com o nome de ficheiro dado.
function downloadFileFrom(url, filename) {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link); // precisa de estar no DOM para o click() funcionar em todos os browsers
  link.click();
  document.body.removeChild(link); // remove logo a seguir, já não é preciso
}
