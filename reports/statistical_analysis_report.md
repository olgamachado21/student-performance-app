# Relatório de Análise Estatística

## Comparação entre 2 grupos (teste t de Student)

**internet** vs `G3`: médias {'no': 11.21, 'yes': 12.26} | t=-3.8753, p=0.0001 | significativo (5%)? **sim**

**romantic** vs `G3`: médias {'no': 12.21, 'yes': 11.69} | t=2.1379, p=0.033 | significativo (5%)? **sim**

**higher** vs `G3`: médias {'yes': 12.36, 'no': 9.09} | t=11.4018, p=0.0 | significativo (5%)? **sim**

**schoolsup** vs `G3`: médias {'yes': 11.34, 'no': 12.09} | t=-2.7204, p=0.0076 | significativo (5%)? **sim**

## Comparação entre múltiplos grupos (ANOVA)

**studytime** vs `G3`: médias por grupo {'1': 11.0, '2': 12.19, '3': 13.23, '4': 13.25} | F=17.8807, p=0.0 | significativo (5%)? **sim**

**goout** vs `G3`: médias por grupo {'1.0': 11.06, '2.0': 12.72, '3.0': 12.25, '4.0': 12.0, '5.0': 11.08} | F=6.7312, p=0.0 | significativo (5%)? **sim**

**failures** vs `G3`: médias por grupo {'0': 12.57, '1': 9.09, '2': 9.06, '3': 8.36} | F=52.6336, p=0.0 | significativo (5%)? **sim**

## Regressão linear simples

**G3 ~ studytime**: coeficiente=0.9389, R²=0.0712, p=0.0 | significativo (5%)? **sim**
> Cada unidade adicional em 'studytime' está associada a uma variação de 0.94 pontos em 'G3' (R²=0.071).

**G3 ~ absences**: coeficiente=-0.1009, R²=0.0198, p=0.000322 | significativo (5%)? **sim**
> Cada unidade adicional em 'absences' está associada a uma variação de -0.10 pontos em 'G3' (R²=0.020).

**G3 ~ failures**: coeficiente=-1.9869, R²=0.1615, p=0.0 | significativo (5%)? **sim**
> Cada unidade adicional em 'failures' está associada a uma variação de -1.99 pontos em 'G3' (R²=0.162).

**G3 ~ alcohol_avg**: coeficiente=-0.6973, R²=0.0492, p=0.0 | significativo (5%)? **sim**
> Cada unidade adicional em 'alcohol_avg' está associada a uma variação de -0.70 pontos em 'G3' (R²=0.049).
