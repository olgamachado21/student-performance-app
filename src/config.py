"""
Configurações centrais do projeto: caminhos, base de dados, colunas e parâmetros.
"""
# os: para ler variáveis de ambiente (ex.: definidas no ficheiro .env).
import os
# Path: para construir caminhos de ficheiros/pastas de forma independente do
# sistema operativo (Windows, Mac, Linux).
from pathlib import Path

# --- Caminhos ---
# Pasta raiz do projeto (duas pastas acima deste ficheiro: src/config.py -> src/ -> raiz).
BASE_DIR = Path(__file__).resolve().parent.parent
# Caminho para o ficheiro Excel com os dados originais dos estudantes.
DATA_RAW_PATH = BASE_DIR / "data" / "raw" / "StudentsPerfomance.xlsx"
# Pasta onde os modelos de Machine Learning treinados (.joblib) são guardados.
MODELS_DIR = BASE_DIR / "models"
# Pasta onde os relatórios gerados (EDA, métricas do modelo, etc.) ficam guardados.
REPORTS_DIR = BASE_DIR / "reports"
# Subpasta dos relatórios só para gráficos/imagens.
FIGURES_DIR = REPORTS_DIR / "figures"
# Caminho do ficheiro da base de dados SQLite — pode ser sobreposto por
# variável de ambiente (SQLITE_DB_PATH); por omissão fica dentro de data/.
SQLITE_PATH = Path(os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "data" / "student_performance.db")))
# Pasta onde ficam as cópias de segurança da base de dados (ver
# src/backup.py) — sobreponível por variável de ambiente (STUDENTPERFOMANCE_BACKUP_DIR),
# tal como o caminho da BD, para os testes automáticos poderem usar uma
# pasta isolada sem tocar nas cópias reais do utilizador.
BACKUP_DIR = Path(os.getenv("STUDENTPERFOMANCE_BACKUP_DIR", str(BASE_DIR / "backups")))

# Cria as pastas de modelos, figuras e backups se ainda não existirem (não dá erro se já existirem).
MODELS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- Base de dados ---
# DB_DRIVER = "mssql" -> liga ao SQL Server (usar com SSMS), via pyodbc.
# DB_DRIVER = "sqlite" (omissão) -> base de dados local em ficheiro, sem necessitar
#             de servidor instalado; útil para desenvolvimento/teste.
# Definir através de variável de ambiente ou de um ficheiro .env (ver .env.example).
DB_DRIVER = os.getenv("DB_DRIVER", "sqlite")

# Definições específicas do SQL Server — só usadas quando DB_DRIVER == "mssql".
MSSQL_SERVER = os.getenv("MSSQL_SERVER", "localhost")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "StudentPerformanceDB")
MSSQL_DRIVER = os.getenv("MSSQL_ODBC_DRIVER", "ODBC Driver 17 for SQL Server")
MSSQL_TRUSTED_CONNECTION = os.getenv("MSSQL_TRUSTED_CONNECTION", "yes")  # autenticação Windows (SSMS)
MSSQL_USER = os.getenv("MSSQL_USER", "")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "")

# Nomes das duas tabelas principais: dados em bruto e dados já limpos.
TABLE_RAW = "Students_Raw"
TABLE_CLEAN = "Students_Clean"

# --- Variáveis-alvo ---
TARGET_REGRESSION = "G3"          # nota final (0-20)
TARGET_CLASSIFICATION = "aprovado"  # derivada: G3 >= 10

# Nota mínima (inclusive) para o estudante ser considerado aprovado.
PASS_THRESHOLD = 10

# --- Grupos de variáveis ---
# Notas de períodos anteriores (fortemente preditivas, mas não são "hábitos")
GRADE_COLS = ["G1", "G2"]

# Variáveis demográficas / contexto familiar
DEMOGRAPHIC_COLS = [
    "school", "sex", "age", "address", "famsize", "Pstatus",
    "Medu", "Fedu", "Mjob", "Fjob", "guardian",
]

# Variáveis de hábitos de estudo e estilo de vida — o foco do projeto
HABIT_COLS = [
    "studytime", "failures", "schoolsup", "famsup", "paid",
    "activities", "internet", "higher", "romantic",
    "freetime", "goout", "Dalc", "Walc", "health", "absences",
    "traveltime", "reason", "nursery", "famrel",
]

# Todas as colunas categóricas (texto/categorias), usadas para saber quais
# precisam de codificação (one-hot encoding) antes de entrar no modelo.
CATEGORICAL_COLS = [
    "school", "sex", "address", "famsize", "Pstatus", "Mjob", "Fjob",
    "reason", "guardian", "schoolsup", "famsup", "paid", "activities",
    "nursery", "higher", "internet", "romantic",
]

# Todas as colunas numéricas, usadas para saber quais precisam de normalização.
NUMERIC_COLS = [
    "age", "Medu", "Fedu", "traveltime", "studytime", "failures",
    "famrel", "freetime", "goout", "Dalc", "Walc", "health", "absences",
]

# Features "puras" de hábitos + demografia (sem G1/G2) -> modelo interpretativo
FEATURES_NO_GRADES = DEMOGRAPHIC_COLS + HABIT_COLS

# Features completas (com G1/G2) -> modelo de maior poder preditivo
FEATURES_WITH_GRADES = FEATURES_NO_GRADES + GRADE_COLS

# Semente aleatória fixa: garante que treinar o modelo dá sempre o mesmo
# resultado (reprodutibilidade), em vez de variar a cada execução.
RANDOM_STATE = 42
# Percentagem dos dados reservada para teste (20%) ao dividir treino/teste.
TEST_SIZE = 0.2
