# Relatório de Análise Exploratória — Desempenho Académico e Hábitos de Estudo
Dataset: 650 estudantes.
Nota final média (G3): **12.02 / 20**
Taxa de aprovação geral (G3 >= 10): **84.6%**

## Variáveis mais correlacionadas positivamente com a nota final
- `G2`: correlação de 0.94
- `G1`: correlação de 0.87
- `studytime`: correlação de 0.27
- `Medu`: correlação de 0.26
- `Fedu`: correlação de 0.21

## Variáveis mais correlacionadas negativamente com a nota final
- `failures`: correlação de -0.40
- `Dalc`: correlação de -0.21
- `Walc`: correlação de -0.18
- `absences`: correlação de -0.14
- `traveltime`: correlação de -0.13

## Taxa de aprovação por tempo de estudo semanal
- Nível 1: 76.4% de aprovação
- Nível 2: 86.6% de aprovação
- Nível 3: 92.8% de aprovação
- Nível 4: 94.4% de aprovação

## Taxa de aprovação por acesso a internet em casa
- Internet = no: 78.8% de aprovação
- Internet = yes: 86.4% de aprovação

## Nota média por nível de consumo de álcool (médio semanal)
- (0.0, 1.5]: 12.53 / 20
- (1.5, 3.0]: 11.65 / 20
- (3.0, 5.0]: 10.53 / 20

## Figuras geradas
- `01_distribuicao_notas.png`
- `02_matriz_correlacao.png`
- `03_habitos_vs_nota.png`
- `04_categoricas_vs_nota.png`
- `05_taxa_aprovacao_estudo.png`
