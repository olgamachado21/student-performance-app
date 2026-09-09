# StudentPerfomance — Desempenho Académico e Hábitos de Estudo

Aplicação em Python (com base de dados SQL e interface em HTML/CSS/JS, disponível como
página web ou como janela de aplicação de desktop) que analisa a relação entre hábitos
de estudo/estilo de vida e o desempenho académico de estudantes, e treina modelos de
Machine Learning capazes de prever a nota final e a probabilidade de aprovação a partir
desses hábitos.

## Motivação

Milhares de estudantes pesquisam diariamente "como estudar melhor", "quantas horas devo
estudar" ou "como melhorar as notas" — mas encontram sobretudo opiniões, não respostas
baseadas em dados. Este projeto usa dados reais de estudantes para identificar quais
hábitos (tempo de estudo, faltas, consumo de álcool, tempo livre, apoio familiar, etc.)
influenciam efetivamente o desempenho escolar, e disponibiliza essa análise através de
modelos preditivos e de uma interface web interativa.

## Screenshots

> _Adiciona aqui 2-3 capturas de ecrã da app (ex.: Visão Geral, Previsão de Notas,
> Esquema Mental) — arrasta as imagens para `docs/screenshots/` e referencia-as assim:_
> `![Visão Geral](docs/screenshots/visao-geral.png)`

## Dataset

`data/raw/StudentsPerfomance.xlsx` — 649 registos de estudantes (ensino secundário,
Portugal), com 33 variáveis: dados demográficos e familiares, hábitos de estudo e estilo
de vida (tempo de estudo, faltas, consumo de álcool, tempo livre, atividades
extracurriculares, acesso a internet, etc.) e notas em três períodos (G1, G2, G3, escala
0-20).

## Arquitetura

```
Excel (dados originais)
        │  ETL (src/etl.py)
        ▼
Base de dados SQL  ──►  Students_Raw  /  Students_Clean
 (SQL Server via SSMS, ou SQLite local para testes)
        │
        ▼
Limpeza, outliers, normalização, análise estatística, Machine Learning
        │
        ▼
API REST (FastAPI, src/api.py) — serve também a interface (web/) na mesma porta
        │
        ├──► Browser:  http://127.0.0.1:8000
        └──► Janela nativa (desktop_app.py, pywebview)
```

## Estrutura do projeto

```
student_performance_app/
├── main.py                      # ponto de entrada: corre o pipeline de dados/ML
├── desktop_app.py                # abre a app numa janela nativa (pywebview)
├── sql/
│   └── schema.sql               # script T-SQL para criar a BD no SSMS
├── data/raw/                    # dados originais (Excel)
├── src/
│   ├── config.py                # caminhos, ligação à BD, colunas e parâmetros
│   ├── database.py              # camada de acesso à base de dados (SQLAlchemy)
│   ├── etl.py                   # importação Excel -> BD, limpeza -> BD
│   ├── data_processing.py       # limpeza, outliers, normalização, novas variáveis
│   ├── eda.py                   # análise exploratória (gráficos + relatório)
│   ├── statistics_analysis.py   # testes estatísticos e regressão simples
│   ├── train_model.py           # treino, avaliação e seleção de modelos de ML
│   ├── predict.py               # funções de previsão prontas a usar
│   ├── alerts.py                 # avisos automáticos (estudantes/dataset em risco)
│   ├── segmentation.py           # segmentação de perfis (K-Means + nomeação automática)
│   ├── reports_pdf.py            # fichas de desempenho e relatório de turma (PDF, reportlab)
│   ├── add_student.py            # adicionar novo estudante (G3 previsto pelo modelo)
│   ├── optimizer.py              # otimizador de estudo (plano de mudança de hábitos)
│   ├── notes.py                  # central de notas (7 tipos de nota)
│   ├── settings.py               # configurações gerais (tema de cores, fonte)
│   ├── backup.py                 # cópias de segurança da base de dados (agendadas/manuais)
│   ├── bulk_import.py            # importação em lote de estudantes via CSV
│   ├── chatbot.py                 # assistente conversacional baseado em regras
│   ├── custom_dataset.py          # importação e análise de datasets genéricos (não só alunos)
│   ├── data_export.py             # exportação do dataset completo em CSV
│   ├── data_quality.py            # deteção de valores atípicos ao adicionar dados
│   ├── exam_week.py               # checklist de semana de exames (Simulador)
│   ├── formula_engine.py          # motor de fórmulas personalizadas (dataset genérico)
│   ├── prediction_tracking.py     # histórico de previsões e precisão do modelo ao longo do tempo
│   ├── suggestions.py             # sugestão de valores prováveis ao adicionar um estudante
│   └── api.py                   # API REST (FastAPI) — backend da interface web
├── web/                         # interface HTML/CSS/JS (consome a API)
│   ├── index.html               # esqueleto das páginas (SPA, sem recarregar)
│   ├── css/style.css            # estilo (paleta indigo, cartões, hover, gauges)
│   └── js/
│       ├── api.js               # cliente da API (fetch)
│       ├── main.js              # router SPA, cache em memória, utilitários de UI
│       ├── chatbot.js            # janela flutuante do assistente conversacional
│       ├── pages/                # lógica de cada secção (1 ficheiro por página)
│       └── vendor/chart.umd.js  # Chart.js incluído localmente (sem CDN)
├── models/                      # modelos treinados (.joblib), gerados
├── reports/
│   ├── figures/                 # gráficos gerados pela EDA
│   ├── eda_report.md
│   ├── statistical_analysis_report.md
│   ├── model_report.md
│   └── model_metrics.json
├── tests/                       # testes automatizados (pytest)
├── .env.example                 # modelo de configuração (BD, etc.)
├── requirements.txt              # bibliotecas Python necessárias
├── Procfile                      # comando de arranque para alojamento na nuvem
├── runtime.txt                   # versão do Python para alojamento na nuvem
└── README.md
```

## Instalação

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copia `.env.example` para `.env` e ajusta conforme o motor de base de dados que
pretendes usar (ver secção seguinte).

## Base de dados

Por omissão (`DB_DRIVER=sqlite`), a aplicação usa uma base de dados SQLite local em
`data/student_performance.db` — não precisas de instalar nada, funciona de imediato.

Para usar SQL Server (SSMS):

1. Abre `sql/schema.sql` no SQL Server Management Studio e executa-o — cria a base de
   dados `StudentPerformanceDB` e as tabelas `Students_Raw` e `Students_Clean`.
2. No `.env`, define `DB_DRIVER=mssql` e ajusta `MSSQL_SERVER` para o nome da tua
   instância (ex.: `localhost\SQLEXPRESS`).
3. Garante que tens instalado o driver ODBC ("ODBC Driver 17 for SQL Server") e o
   pacote `pyodbc` (`pip install pyodbc` — não vem no `requirements.txt` por
   omissão, porque só é preciso neste modo; o modo SQLite, usado por omissão,
   não precisa dele).

Toda a aplicação lê/escreve através de `src/database.py`, por isso trocar de motor não
implica alterar mais nenhum ficheiro.

## Como usar

**Pipeline completo** (ETL -> análise exploratória -> análise estatística -> ML):
```bash
python main.py
```
Opções: `python main.py --skip-etl` (reaproveita dados já na BD) ou
`python main.py --only eda` (corre apenas uma etapa: `etl` | `eda` | `stats` | `ml`).
Corre isto pelo menos uma vez antes de abrir a interface, para gerar os modelos
em `models/`.

**Abrir a interface — duas formas, a app é a mesma:**

- **Como aplicação de desktop** (janela própria, sem browser nem terminal visível):
  ```bash
  python desktop_app.py
  ```
  Isto arranca a API em segundo plano e abre logo a janela. É só isto.

- **Como página web** (se preferires o browser):
  ```bash
  uvicorn src.api:app --reload
  ```
  Depois abre `http://127.0.0.1:8000` no browser.

- **Para aceder de outro dispositivo na mesma rede** (ex.: telemóvel), o `127.0.0.1`
  por omissão não chega — é preciso `--host 0.0.0.0` para aceitar ligações de fora do
  próprio computador:
  ```bash
  uvicorn src.api:app --host 0.0.0.0 --reload
  ```
  Depois, no outro dispositivo (na mesma rede Wi-Fi), abre `http://<IP-do-PC>:8000`
  no browser — o IP local do PC vê-se nas Definições de Rede do Windows (algo como
  `192.168.1.X`). A interface é responsiva, por isso funciona bem em ecrãs pequenos.

Não há dependências externas — o Chart.js está incluído em `web/js/vendor/`, não
precisa de ligação à internet. A API e a interface são servidas pelo mesmo processo,
na mesma porta (não precisas de dois terminais nem de servidor à parte para os
ficheiros web).

**Testes:**
```bash
pytest -v
```

## Alojar a app na nuvem (acesso de qualquer lado, sem depender do teu PC)

O acesso pelo telemóvel na mesma rede (secção anterior) só funciona com o teu
computador ligado. Para teres um endereço público, acessível de qualquer lado
(dados móveis incluídos) sem precisares de deixar o PC ligado, publica a app
num serviço de alojamento Python — por exemplo o [Render](https://render.com)
ou o [Railway](https://railway.com), que têm planos gratuitos suficientes para
uma demonstração/apresentação.

A app já tem os ficheiros necessários para isso, prontos a usar:

- **`requirements.txt`** — lista das bibliotecas Python necessárias.
- **`Procfile`** — diz ao serviço como arrancar a app:
  `web: uvicorn src.api:app --host 0.0.0.0 --port $PORT`
  (o `--host 0.0.0.0` aceita ligações de fora, e o `$PORT` é a porta que o
  próprio serviço atribui — não é preciso escolheres uma).
- **`runtime.txt`** — indica a versão do Python usada (`3.14.6`).

**Passos gerais** (exemplo com o Render):

1. Cria um repositório Git (ex.: no GitHub) só com a pasta
   `student_performance_app/` e envia-o (`git push`). O ficheiro `.env` nunca
   é enviado (está no `.gitignore` por segurança) — se precisares de definir
   alguma variável de ambiente (ex.: `DB_DRIVER`), fazes isso diretamente no
   painel do serviço, não num ficheiro.
2. Em render.com, cria um "New Web Service" e liga-o ao repositório.
3. Comando de build: `pip install -r requirements.txt`
4. Comando de arranque: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
   (o Render também lê isto automaticamente do `Procfile`, mas alguns
   serviços pedem para o confirmares no painel).
5. Aguarda o deploy (alguns minutos) — o serviço dá-te um endereço público
   (ex.: `https://studentperfomance.onrender.com`), que já podes abrir em
   qualquer telemóvel ou computador, em qualquer rede.

**Nota importante sobre os dados:** nos planos gratuitos destes serviços, o
disco não costuma ser permanente — de vez em quando (reinícios, novo deploy)
a base de dados volta ao estado em que foi enviada no repositório. Os 649
estudantes de demonstração continuam sempre lá, mas alterações feitas depois
de publicado (adicionar estudantes, backups criados na app, etc.) podem
perder-se nesse reinício. Isto não é um problema para uma apresentação —
só é relevante se quiseres guardar dados novos de forma permanente, o que
exigiria um disco pago ("persistent disk") ou uma base de dados alojada à
parte.

## Pipeline de dados

1. **Importação**: leitura do Excel original e carregamento em `Students_Raw` (BD).
2. **Limpeza**: correção de tipos de dados, remoção de duplicados, validação de
   intervalos, preenchimento de valores em falta.
3. **Tratamento de outliers**: método do intervalo interquartil (IQR), com
   winsorização (capping) e sinalização (`<coluna>_is_outlier`).
4. **Normalização**: z-score das principais variáveis numéricas (`<coluna>_norm`).
5. **Transformação**: criação de novas variáveis (aprovado, consumo médio de álcool,
   escolaridade média dos pais, evolução de nota entre períodos).
6. **Carregamento**: gravação do dataset final em `Students_Clean` (BD).

## Análise estatística

- **Correlações e distribuições** (`src/eda.py`)
- **Comparações entre grupos**: teste t de Student (2 grupos, ex. internet sim/não) e
  ANOVA (3+ grupos, ex. níveis de tempo de estudo), com significância a 5%.
- **Regressão linear simples**: relação entre uma única variável (ex. tempo de estudo)
  e a nota final, com coeficiente, R² e p-value.

Ver `reports/statistical_analysis_report.md`.

## Modelos de Machine Learning

Foram treinados e comparados três algoritmos para cada tarefa (Regressão Linear,
Random Forest e Gradient Boosting), com validação cruzada de 5 folds:

- **Regressão — "hábitos"**: prevê a nota final (G3) usando apenas hábitos de estudo,
  estilo de vida e contexto familiar (sem conhecer notas anteriores). Responde
  diretamente à pergunta de investigação: *que hábitos influenciam o desempenho?*
- **Regressão — "completo"**: inclui também as notas dos períodos anteriores (G1, G2)
  para maior precisão preditiva (R² ≈ 0.85).
- **Classificação**: prevê aprovado/reprovado (G3 ≥ 10) com base apenas em hábitos,
  incluindo a probabilidade de aprovação.

Resultados detalhados, incluindo importância de variáveis, em `reports/model_report.md`.

## Principais conclusões

- O tempo de estudo semanal está associado a taxas de aprovação crescentes (76% no
  nível mais baixo, 94% no mais alto) — diferença estatisticamente significativa.
- Reprovações anteriores são o fator com maior impacto negativo identificado
  (~-1,98 valores por reprovação).
- Maior consumo de álcool (dias úteis e fim de semana) está associado a notas médias
  mais baixas.
- O acesso a internet em casa está associado a notas significativamente superiores
  (p < 0,001).

## Interface

A interface (`web/`) tem dezoito secções, todas na mesma página (sem recarregar),
organizadas em três grupos:

**Análise de Dados**
- **Visão Geral**: KPIs (nota média, taxa de aprovação, faltas médias) e gráficos gerais.
- **Fatores de Risco**: correlações, importância de variáveis e exploração dinâmica de
  qualquer hábito vs nota final.
- **Perfil do Estudante**: filtros interativos para comparar subgrupos com a média geral.
- **Previsão de Notas**: formulário com os hábitos do estudante, devolvendo a nota
  prevista, a probabilidade de aprovação e recomendações baseadas nos dados.
- **Adicionar Dados**: formulário simplificado para adicionar um novo estudante ao
  dataset — a nota final (G3) é sempre prevista automaticamente pelo modelo treinado
  (nunca inserida manualmente), e o estudante fica persistido na base de dados,
  disponível em todas as outras páginas a partir daí.
- **Dados**: explorador do dataset completo (incluindo estudantes adicionados
  manualmente), com filtros (escola, nível de desempenho, risco), tabela paginada e
  formatação condicional por cor (nível de desempenho, estado de risco).

**Avisos e Alertas**
- **Avisos e Alertas**: sinais de atenção gerados automaticamente a partir do estado
  atual dos dados (ex.: taxa de risco elevada, faltas muito acima da média, notas a
  piorar em estudantes que já reprovaram), com lista dos estudantes em risco
  (critério: nota final < 10, OU já reprovou antes, OU mais de 15 faltas).
- **Segmentação de Perfis**: agrupamento automático de estudantes com hábitos e
  desempenho semelhantes, usando K-Means (3 a 8 grupos, à escolha). Cada grupo é
  nomeado automaticamente a partir dos traços mais desviantes da média geral
  (ex.: "Dedicados ao Estudo & Bom Desempenho Académico") — os nomes não são fixos,
  são calculados a partir dos dados reais de cada grupo.
- **Fichas de Desempenho**: gera um PDF individual por estudante (indicando o número),
  com um resumo das notas e uma recomendação personalizada baseada em comparações
  reais entre grupos de estudantes com o mesmo tempo de estudo (nunca texto genérico —
  só é gerada se houver pelo menos 5 estudantes em cada grupo comparado).
- **Otimizador de Estudo**: indicando o número de um estudante e uma nota-alvo,
  calcula o plano de mudança de hábitos (mais tempo de estudo, menos saídas, menos
  faltas, menos consumo de álcool) que mais aproxima a nota prevista da meta, usando
  um algoritmo guloso (hill-climbing) sobre o modelo de regressão já treinado —
  mostra a nota prevista antes/depois e a lista de mudanças sugeridas.
- **Alertas por Email**: deteta automaticamente estudantes em estado crítico (nota
  final negativa **e** mais de 10 faltas — critério mais estrito do que o "em risco"
  geral) e permite enviar um email de alerta ao encarregado de educação associado,
  com um resumo do desempenho e a mesma recomendação personalizada usada nas Fichas
  de Desempenho. Inclui: configuração do servidor SMTP (a palavra-passe fica
  guardada só na base de dados local/configurada da aplicação, nunca partilhada com
  mais lado nenhum além do próprio servidor SMTP indicado — recomenda-se sempre uma
  "palavra-passe de aplicação"), associação de emails de encarregados a estudantes, e
  envio individual ou em lote (nunca automático — exige sempre confirmação explícita).

**Ferramentas de Estudo**
- **Plano de Estudo**: metas pessoais com prazo (ex.: "Rever Matemática até sexta") e um
  cronograma de conteúdos por disciplina/tópico. O estado "Em atraso" nunca é guardado —
  é sempre calculado a partir da data/hora atual, para nunca ficar desatualizado. Inclui
  um resumo de progresso (% concluído) e alertas de prazos próximos (48h).
- **Calendário**: horário de estudo semanal em grelha (um bloco = dia, hora de
  início/fim, disciplina, assunto, estado). Cada disciplina recebe automaticamente uma
  cor consistente de uma paleta rotativa, e a página destaca sempre o próximo bloco a
  começar.
- **Central de Notas**: 7 tipos de nota, cada um com o seu editor — texto livre (negrito,
  itálico, sublinhado, destaque de 4 cores, escolha de fonte/tamanho), checklist,
  flashcards (pergunta/resposta), método de Cornell (palavras-chave, notas, resumo),
  método dos Quadrantes (sempre 4 blocos fixos), Outline (tópicos hierárquicos com
  numeração automática ao usar Tab/Shift+Tab, até 4 níveis: I. → A. → 1. → a)) e SQ3R —
  leitura ativa em 5 secções (Survey, Question, Read, Recite, Review), editáveis em
  qualquer ordem. Notas podem ser associadas a um "Tema" (para os Meus Dashboards)
  e filtradas por tema na lista.
- **Meus Dashboards**: um dashboard não é uma grelha de widgets — é um agrupamento
  lógico por tema (ex.: "Física", "Exame Final"). O nome do dashboard é usado como
  "Tema" nas Notas e nos Esquemas Mentais, por isso cada dashboard tem dois botões —
  "Notas" e "Esquemas" — que levam diretamente à Central de Notas ou ao Esquema Mental
  já filtrados por esse tema (reaproveita a mesma lógica, sem duplicar código). Apagar
  um dashboard nunca apaga o conteúdo — notas e esquemas só deixam de estar agrupados e
  voltam a aparecer nas páginas gerais; o próprio dashboard vai para a Lixeira.
- **Pomodoro**: cronómetro de foco/pausa com 4 modos — Clássico (25/5 fixo),
  Customizado (durações à escolha), Fluxo (a pausa é sempre 1/5 do tempo que passaste
  em foco) e Horas Líquidas (sem pausas cronometradas, só acumula tempo de estudo) — e 4
  estilos visuais. O cronómetro corre no browser; o total acumulado de horas líquidas
  fica guardado no servidor (sincronizado a cada 30s enquanto corre), para não se perder
  mesmo que feches a aplicação a meio de uma sessão.
- **Esquema Mental**: mini-editor de mapas mentais em SVG. Cada esquema tem uma galeria
  própria (criar, renomear, filtrar por tema, remover) e um canvas onde se criam nós de
  7 formas (retângulo, círculo, elipse, triângulo, losango, hexágono, estrela) com cor à
  escolha, se arrastam livremente, se editam com duplo clique, e se ligam uns aos outros
  em "Modo Ligar" (linha sólida/tracejada/pontilhada, seta num lado ou nos dois). Inclui
  desfazer/refazer, zoom (roda do rato) e deslocação da vista (arrastar o fundo). O
  conteúdo (nós e ligações) é guardado como um "snapshot" completo de cada vez —
  automaticamente ao fim de 1,2s de inatividade e também ao sair do editor.

Eliminar um item em qualquer Ferramenta de Estudo nunca é definitivo de imediato — o
item é guardado na Lixeira (`src/trash.py`), que pode ser gerida a partir de Configurações.

**Configurações**
- **Temas**: 10 temas de cores (6 claros, 4 escuros) e escolha de fonte, aplicados
  instantaneamente a toda a app e guardados na base de dados (persistem entre sessões,
  tanto na versão web como na janela de desktop).
- **Conta**: conta local opcional (email, utilizador, palavra-passe) — a palavra-passe
  nunca é guardada em texto simples (hash PBKDF2-HMAC-SHA256 com "salt" único por conta),
  com validação de força em tempo real. Iniciar sessão nunca bloqueia o uso da app.
- **Importar/Exportar**: exporta um backup JSON de tudo o que foi criado nas Ferramentas
  de Estudo (metas, cronograma, calendário, notas, esquemas mentais); importar um backup
  adiciona sempre registos novos, nunca substitui o que já existe. Inclui também uma
  biblioteca de ficheiros importados (.txt/.pdf) com extração automática de texto, e um
  histórico de todas as ações de import/export.
- **Lixeira**: lista tudo o que foi eliminado nas Ferramentas de Estudo (metas,
  cronograma, blocos do calendário, notas, dashboards, esquemas mentais), com restauro
  (volta a ficar disponível na ferramenta de origem) ou eliminação definitiva.

O `js/main.js` mantém uma cache em memória dos dados já pedidos à API, para que trocar
de secção seja imediato, sem repetir pedidos desnecessários.

A mesma interface está disponível de duas formas:

- **Janela de desktop** (`desktop_app.py`): usa [pywebview](https://pywebview.flowrl.com/)
  para mostrar a interface numa janela nativa do sistema operativo. Por baixo, corre a
  mesma API FastAPI num thread em segundo plano — a app fecha sozinha quando fechas a
  janela.
- **Página web** (`src/api.py` com `uvicorn`): a API serve os ficheiros de `web/`
  diretamente (via `StaticFiles`), por isso a app fica toda disponível num único
  endereço (`http://127.0.0.1:8000`), sem precisar de servidor separado para o
  frontend. Se algum dia quiseres servir o frontend a partir de outro endereço/porta,
  edita `API_BASE_URL` no topo de `web/js/api.js`.

## Licença

Todos os direitos reservados. O código está publicamente visível (para fins de
portefólio/avaliação académica), mas não há uma licença de código aberto —
copiar, reutilizar ou redistribuir este código sem autorização não é permitido.
O dataset usado (`data/raw/StudentsPerfomance.xlsx`) é o conjunto de dados
público "Student Performance" (UCI Machine Learning Repository).
