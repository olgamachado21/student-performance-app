# Relatório de Modelação — Previsão de Desempenho Académico

## 1. Regressão — prever nota final (G3)

### Variante: `habitos`
Melhor modelo: **LinearRegression**

| Modelo | R2 | MAE | RMSE | CV R2 (média ± dp) |
|---|---|---|---|---|
| LinearRegression | 0.3078 | 1.7111 | 2.2767 | 0.2671 ± 0.0608 |
| RandomForestRegressor | 0.246 | 1.7824 | 2.3762 | 0.3051 ± 0.0518 |
| GradientBoostingRegressor | 0.2672 | 1.7588 | 2.3426 | 0.2173 ± 0.0608 |

### Variante: `completo`
Melhor modelo: **LinearRegression**

| Modelo | R2 | MAE | RMSE | CV R2 (média ± dp) |
|---|---|---|---|---|
| LinearRegression | 0.8639 | 0.7055 | 1.0096 | 0.8779 ± 0.0267 |
| RandomForestRegressor | 0.8429 | 0.7291 | 1.0847 | 0.8853 ± 0.0267 |
| GradientBoostingRegressor | 0.8609 | 0.6694 | 1.0208 | 0.8743 ± 0.0308 |

## 2. Classificação — aprovado vs reprovado (apenas hábitos, sem G1/G2)
Melhor modelo: **RandomForestClassifier**

| Modelo | Accuracy | Precision | Recall | F1 | ROC-AUC | CV F1 (média ± dp) |
|---|---|---|---|---|---|---|
| LogisticRegression | 0.8154 | 0.8707 | 0.9182 | 0.8938 | 0.6414 | 0.9171 ± 0.0137 |
| RandomForestClassifier | 0.8385 | 0.856 | 0.9727 | 0.9106 | 0.6786 | 0.917 ± 0.0063 |
| GradientBoostingClassifier | 0.8308 | 0.8729 | 0.9364 | 0.9035 | 0.6927 | 0.9169 ± 0.011 |

## 3. Importância das variáveis (modelo de hábitos, top 15)
- `num__failures`: 0.1015
- `cat__school_GP`: 0.0524
- `cat__higher_no`: 0.0475
- `cat__higher_yes`: 0.0447
- `num__absences`: 0.0429
- `num__famrel`: 0.0424
- `cat__school_MS`: 0.0391
- `num__Walc`: 0.0328
- `num__Fedu`: 0.0327
- `num__age`: 0.0324
- `num__freetime`: 0.0321
- `num__Medu`: 0.0294
- `num__goout`: 0.0294
- `num__Dalc`: 0.0276
- `num__health`: 0.0253

## Conclusão
O modelo que inclui as notas de períodos anteriores (G1/G2) tem, como esperado, maior poder preditivo - mas o modelo baseado apenas em hábitos e contexto (sem G1/G2) já explica uma parte relevante da variação da nota final, confirmando que fatores como tempo de estudo, faltas, reprovações anteriores e consumo de álcool têm impacto mensurável no desempenho académico.
