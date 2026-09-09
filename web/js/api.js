// ============================================================
// Cliente da API — StudentPerfomance (Desempenho Académico e Hábitos de Estudo)
// A API deve estar a correr localmente:
//     uvicorn src.api:app --reload
// A própria API serve esta página (mesmo endereço/porta), por isso o valor
// por omissão é "" (pedidos relativos, mesma origem). Só precisas de mudar
// isto se estiveres a servir o frontend a partir de outro endereço/porta.
// ============================================================

// Prefixo comum a todos os pedidos; "" significa "mesma origem" (relativo).
const API_BASE_URL = "";

const Api = {
  // Pedido GET genérico: monta o URL completo, valida o status HTTP e devolve o JSON.
  async _get(path) {
    const res = await fetch(`${API_BASE_URL}${path}`);
    if (!res.ok) {
      throw new Error(`Erro ${res.status} ao chamar ${path}`);
    }
    return res.json();
  },

  // Pedido POST genérico: envia "body" como JSON; tenta extrair a mensagem de
  // erro detalhada do FastAPI (campo "detail") antes de recorrer a uma
  // mensagem genérica com o código de estado HTTP.
  async _post(path, body) {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Erro ${res.status} ao chamar ${path}`);
    }
    return res.json();
  },

  // Pedido PATCH genérico: usado para atualizações parciais de um recurso existente.
  async _patch(path, body) {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Erro ${res.status} ao chamar ${path}`);
    }
    return res.json();
  },

  // Pedido PUT genérico: usado para substituir um recurso por inteiro.
  async _put(path, body) {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Erro ${res.status} ao chamar ${path}`);
    }
    return res.json();
  },

  // Pedido DELETE genérico: o corpo é opcional (nem todos os DELETE precisam de payload).
  async _delete(path, body) {
    const opts = { method: "DELETE" };
    if (body !== undefined) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(`${API_BASE_URL}${path}`, opts);
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Erro ${res.status} ao chamar ${path}`);
    }
    return res.json();
  },

  // -- Endpoints simples (sem parâmetros) ----------------------------------
  health: () => Api._get("/health"),
  meta: () => Api._get("/meta"),
  stats: () => Api._get("/stats"),
  gradeDistribution: () => Api._get("/grade-distribution"),
  passFailCounts: () => Api._get("/pass-fail-counts"),
  correlations: () => Api._get("/correlations"),
  // scatter: pontos (x,y) + regressão simples entre duas variáveis à escolha.
  scatter: (x, y) => Api._get(`/scatter?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}`),
  featureImportance: () => Api._get("/feature-importance"),
  groupStats: (variable) => Api._get(`/group-stats?variable=${encodeURIComponent(variable)}`),
  statisticalTests: () => Api._get("/statistical-tests"),
  modelMetrics: () => Api._get("/model-metrics"),
  outliers: () => Api._get("/outliers"),
  defaults: () => Api._get("/defaults"),

  // Lista de estudantes com filtros opcionais — monta a query string só com
  // os parâmetros efetivamente fornecidos, usando valores por omissão razoáveis.
  students: (filters) => {
    const params = new URLSearchParams();
    if (filters.sex) params.set("sex", filters.sex);
    if (filters.internet) params.set("internet", filters.internet);
    if (filters.higher) params.set("higher", filters.higher);
    params.set("studytime_min", filters.studytime_min ?? 1);
    params.set("studytime_max", filters.studytime_max ?? 4);
    params.set("limit", filters.limit ?? 200);
    return Api._get(`/students?${params.toString()}`);
  },

  // -- Previsão (Simulador) ------------------------------------------------
  predict: (payload) => Api._post("/predict", payload),
  predictExplain: (payload) => Api._post("/predict/explain", payload),

  // Instantâneos (snapshots) de previsões guardadas para validar contra a nota real depois.
  savePredictionSnapshot: (payload) => Api._post("/predict/snapshots", payload),
  predictionSnapshots: () => Api._get("/predict/snapshots"),
  recordPredictionSnapshotActual: (id, actualGrade) =>
    Api._post(`/predict/snapshots/${encodeURIComponent(id)}/actual`, { actual_grade: actualGrade }),
  deletePredictionSnapshot: (id) => Api._delete(`/predict/snapshots/${encodeURIComponent(id)}`),

  examWeekChecklist: (payload) => Api._post("/exam-week/checklist", payload),

  predictionValidation: () => Api._get("/predict/validation"),
  predictionAccuracyOverTime: () => Api._get("/predict/accuracy-over-time"),

  // -- Alertas --------------------------------------------------------------
  alerts: () => Api._get("/alerts"),

  // -- Comentários/notas por estudante (ver src/notes.py) --------------------
  studentNotes: (studentId) => Api._get(`/notes?student_id=${encodeURIComponent(studentId)}`),
  addStudentNote: (studentId, text, context) =>
    Api._post("/notes", { student_id: studentId, text, context: context || null }),
  deleteStudentNote: (id) => Api._delete(`/notes/${encodeURIComponent(id)}`),

  // -- Segmentação (clustering configurável) --------------------------------
  segmentationFeatures: () => Api._get("/segmentation-features"),
  segmentation: (nClusters, features) => {
    const params = new URLSearchParams();
    params.set("n_clusters", nClusters);
    if (features && features.length) params.set("features", features.join(","));
    return Api._get(`/segmentation?${params.toString()}`);
  },

  // -- Fichas/estudantes ----------------------------------------------------
  fichaUrl: (studentId) => `${API_BASE_URL}/ficha/${encodeURIComponent(studentId)}`,
  addStudent: (payload) => Api._post("/students/add", payload),
  suggestValues: (knownFields) => Api._post("/students/suggest-values", knownFields),
  checkValues: (knownFields) => Api._post("/students/check-values", knownFields),

  // Importação em lote (CSV) — usa FormData em vez de JSON, por isso não
  // reaproveita o _post genérico (que fixa Content-Type: application/json).
  async bulkImportStudents(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE_URL}/students/bulk-import`, {
      method: "POST",
      body: formData, // o browser define automaticamente o Content-Type multipart correto
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Erro ${res.status} ao importar o ficheiro`);
    }
    return res.json();
  },

  // Tabela paginada de estudantes (Explorador de Dados), com filtros e paginação.
  studentsTable: (filters) => {
    const params = new URLSearchParams();
    if (filters.school) params.set("school", filters.school);
    if (filters.perf_band) params.set("perf_band", filters.perf_band);
    if (filters.at_risk !== "" && filters.at_risk !== undefined && filters.at_risk !== null) {
      params.set("at_risk", filters.at_risk);
    }
    params.set("page", filters.page ?? 1);
    params.set("page_size", filters.page_size ?? 20);
    return Api._get(`/students/table?${params.toString()}`);
  },

  // Devolve só o URL (não faz o pedido) — usado para abrir o download diretamente numa nova aba.
  exportCsvUrl: (filters) => {
    const params = new URLSearchParams();
    if (filters.school) params.set("school", filters.school);
    if (filters.perf_band) params.set("perf_band", filters.perf_band);
    if (filters.at_risk !== "" && filters.at_risk !== undefined && filters.at_risk !== null) {
      params.set("at_risk", filters.at_risk);
    }
    return `${API_BASE_URL}/students/export-csv?${params.toString()}`;
  },

  // -- Otimizador de estudo --------------------------------------------------
  optimizer: (studentId, targetGrade) =>
    Api._get(`/optimizer?student_id=${encodeURIComponent(studentId)}&target_grade=${encodeURIComponent(targetGrade)}`),
  cohortSimulation: (deltas) => Api._post("/optimizer/cohort-simulation", deltas),

  // -- Relatórios (Ideias 2 e 3) ------------------------------------------
  classReportUrl: () => `${API_BASE_URL}/reports/class`,
  fichasLoteUrl: (onlyAtRisk = true, limit = 100) =>
    `${API_BASE_URL}/reports/fichas-lote?only_at_risk=${onlyAtRisk ? "true" : "false"}&limit=${encodeURIComponent(limit)}`,

  // -- Gráfico radar (Ideia 4) ---------------------------------------------
  profileRadar: (filters) => {
    const params = new URLSearchParams();
    if (filters.sex) params.set("sex", filters.sex);
    if (filters.internet) params.set("internet", filters.internet);
    if (filters.higher) params.set("higher", filters.higher);
    params.set("studytime_min", filters.studytime_min ?? 1);
    params.set("studytime_max", filters.studytime_max ?? 4);
    return Api._get(`/profile/radar?${params.toString()}`);
  },

  // -- Configurações: Temas + Alertas --------------------------------------
  themes: () => Api._get("/themes"),
  getSettings: () => Api._get("/settings"),
  saveSettings: (payload) => Api._post("/settings", payload),

  // -- Configurações: Cópias de segurança -----------------------------------
  // Um backup automático corre sozinho em segundo plano (ver src/backup.py);
  // estes endpoints servem o botão manual e a lista/restauro/apagar na UI.
  backupStatus: () => Api._get("/backup/status"),
  listBackups: () => Api._get("/backup"),
  createBackup: () => Api._post("/backup", {}),
  restoreBackup: (id) => Api._post(`/backup/${encodeURIComponent(id)}/restore`, {}),
  deleteBackup: (id) => Api._delete(`/backup/${encodeURIComponent(id)}`),

  // -- Assistente (chatbot baseado em regras) ------------------------------
  chatbotAsk: (question) => Api._post("/chatbot/ask", { question }),
  chatbotExamples: () => Api._get("/chatbot/examples"),

  // -- Dataset Personalizado ------------------------------------------------
  // Área independente e genérica: upload de QUALQUER ficheiro próprio ->
  // importação direta (sem mapear colunas) -> estatísticas/fórmulas sempre
  // disponíveis, Previsões só quando o ficheiro tem colunas parecidas com as
  // de estudantes (detetadas automaticamente), e Treinar Modelo genérico (o
  // utilizador escolhe a coluna-alvo e as colunas-recurso) — ver
  // src/custom_dataset.py. O upload usa FormData, tal como bulkImportStudents.
  async customDatasetUpload(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE_URL}/custom-dataset/upload`, { method: "POST", body: formData });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Erro ${res.status} ao carregar o ficheiro`);
    }
    return res.json();
  },

  customDatasetStaged: () => Api._get("/custom-dataset/staged"),
  customDatasetImport: () => Api._post("/custom-dataset/import", {}),
  customDatasetStatus: () => Api._get("/custom-dataset/status"),
  customDatasetStats: () => Api._get("/custom-dataset/stats"),
  customDatasetPredict: (page = 1, pageSize = 20) =>
    Api._get(`/custom-dataset/predict?page=${encodeURIComponent(page)}&page_size=${encodeURIComponent(pageSize)}`),
  customDatasetTrain: (targetCol, featureCols) =>
    Api._post("/custom-dataset/train", { target_col: targetCol, feature_cols: featureCols }),
  customDatasetTrainMetrics: () => Api._get("/custom-dataset/train"),
  customDatasetDelete: () => Api._delete("/custom-dataset"),

  // Fórmulas personalizadas: o utilizador escreve a sua própria expressão
  // (ex.: "G1*0.3 + G2*0.3 + G3*0.4" ou "media(G3) onde studytime >= 3"),
  // avaliada em segurança no backend (ver src/formula_engine.py).
  customDatasetFormula: (formula, page = 1, pageSize = 20) =>
    Api._post(`/custom-dataset/formula?page=${encodeURIComponent(page)}&page_size=${encodeURIComponent(pageSize)}`, { formula }),
};
