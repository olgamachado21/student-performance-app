"""
Ponto de entrada único da aplicação.

Corre o pipeline completo, do princípio ao fim:
    1) ETL: importa o Excel original para a base de dados SQL (Students_Raw) e grava os dados limpos/transformados (Students_Clean).
    2) Análise exploratória: gera gráficos e relatório de insights.
    3) Análise estatística: testes de comparação entre grupos e regressão simples.
    4) Machine Learning: treina, avalia e guarda os modelos de previsão.

Uso:
    python main.py              # corre o pipeline completo
    python main.py --skip-etl   # reaproveita os dados já na base de dados
    python main.py --only eda   # corre só uma etapa: etl | eda | stats | ml

Acronyms:
    ETL: Extract, Transform, Load
    EDA: Exploratory Data Analysis
    ML: Machine Learning
"""

# IMPORTS
from __future__ import annotations

import argparse
import sys
import time

from src import database
from src.eda import run_eda
from src.etl import run_etl
from src.statistics_analysis import run_statistical_analysis
from src.train_model import run_training

# Execução das etapas do pipeline, com mensagens de progresso e tempo de execução.
def _step(name: str, func, *args, **kwargs):
    print(f"\n{'=' * 60}\n▶ {name}\n{'=' * 60}")
    start = time.time()
    result = func(*args, **kwargs)
    print(f"✔ {name} concluído em {time.time() - start:.1f}s")
    return result

# Função principal que corre o pipeline completo, ou apenas uma etapa, dependendo dos argumentos passados.
def run_pipeline(skip_etl: bool = False, only: str | None = None):
    steps = {
        "etl": lambda: _step("ETL (importação e limpeza para a base de dados)", run_etl),
        "eda": lambda: _step("Análise Exploratória de Dados", run_eda),
        "stats": lambda: _step("Análise Estatística", run_statistical_analysis),
        "ml": lambda: _step("Treino dos Modelos de Machine Learning", run_training),
    }
    # Execução de apenas uma etapa, se especificada.
    if only:
        if only not in steps: # Se a estapa especificada não for válida, exibe uma mensagem de erro e termina a execução.
            print(f"Etapa desconhecida: '{only}'. Opções: {list(steps)}") # Mensagem de erro
            sys.exit(1) # Termina a execução do programa com código de erro 1
        steps[only]() # Executa a etapa especifica
        return # Termina a execução do programa após a execução da etapa específica
    # Execução do pipeline completo
    if not skip_etl: # Se não for para pular a etapa ETL, executa a etapa ETL.
        steps["etl"]() # Executa a etapa ETL
    elif not database.table_exists("Students_Clean"): # Se a tabela não existir na BD, exibe um aviso e executa a etapa ETL mesmo com o argumento --skip-etl.
        print("Aviso: --skip-etl indicado mas não há dados na BD. A correr ETL na mesma.") # Mensagem de aviso
        steps["etl"]() # Executa a etapa ETL

    steps["eda"]() # Executa a etapa de Análise Exploratória de Dados
    steps["stats"]() # Executa a etapa de Análise Estatística
    steps["ml"]() # Executa a etapa de Treino dos Modelos de Machine Learning

    print("\n" + "=" * 60) # Linha de separação 
    print("Pipeline completo! Consulta a pasta 'reports/' para os relatórios") # Mensagem de conclusão do pipeline
    print("e gráficos, e 'models/' para os modelos treinados.") # Mensagem de conclusão do pipeline
    print("Para abrir a interface: uvicorn src.api:app --reload") # Mensagem de instrução para abrir a interface
    print("depois: cd web && python -m http.server 5500  (abre http://localhost:5500)") # Mensagem de insturção para abrir a interface
    print("=" * 60)


if __name__ == "__main__": # Se o script for executado diretamente (não import)
    parser = argparse.ArgumentParser(description="Pipeline de análise de desempenho académico.") # Cria um parser de argumentos para a linha de comando
    parser.add_argument("--skip-etl", action="store_true", help="Reaproveita os dados já carregados na BD.") # Adiciona um argumento opcional --skip-etl para pular a etapa ETL
    parser.add_argument("--only", choices=["etl", "eda", "stats", "ml"], help="Corre apenas uma etapa.") # Adiciona um argumento opcional --only para executar apenas uma etapa específica do pipeline
    args = parser.parse_args() # Analisa os argumentos passados na linha de comando

    run_pipeline(skip_etl=args.skip_etl, only=args.only) # Executa o pipeline com os argumentos passados na linha de comando