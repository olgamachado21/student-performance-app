from src.api import group_stats, statistical_tests

# Ideia G: Contexto familiar e socioeconómico — colunas do dataset original
# (escola, zona, explicações pagas, educação/profissão dos pais, motivo de
# escolha da escola) que já estavam limpas na base de dados mas nunca
# tinham sido expostas na interface. Reaproveita compare_two_groups,
# compare_multiple_groups e simple_linear_regression, já testados em
# test_statistics_analysis.py — aqui testa-se apenas a composição no
# endpoint /statistical-tests e a extensão do /group-stats.

# Chaves esperadas no resultado de /statistical-tests, relacionadas com o
# contexto familiar/socioeconómico do estudante.
FAMILY_CONTEXT_KEYS = [
    "paid", "school", "address", "mjob", "fjob", "reason",
    "medu_regression", "fedu_regression", "schoolsup",
]


def test_statistical_tests_includes_family_context_keys():
    # Todas as novas chaves de contexto familiar devem estar presentes no resultado.
    result = statistical_tests()
    for key in FAMILY_CONTEXT_KEYS:
        assert key in result


def test_statistical_tests_still_includes_original_habit_keys():
    # Não pode ter partido nada do que já existia.
    result = statistical_tests()
    for key in ["internet", "higher", "studytime_regression", "failures_regression", "alcohol_regression"]:
        assert key in result


def test_statistical_tests_two_group_comparisons_have_two_categories():
    # Variáveis binárias (sim/não, escola, zona) devem ter exatamente 2 categorias comparadas.
    result = statistical_tests()
    for key in ["paid", "school", "address", "schoolsup"]:
        assert len(result[key]["categorias"]) == 2
        assert "p_value" in result[key]
        assert "significativo_5pct" in result[key]


def test_statistical_tests_multi_group_comparisons_have_anova_fields():
    # Variáveis com múltiplas categorias (profissão, motivo) devem usar ANOVA.
    result = statistical_tests()
    for key in ["mjob", "fjob", "reason"]:
        assert "f_stat" in result[key]
        assert len(result[key]["medias_por_grupo"]) >= 3


def test_statistical_tests_parental_education_regressions_are_valid():
    # As regressões de educação dos pais (Medu/Fedu) devem ter R² válido.
    result = statistical_tests()
    for key in ["medu_regression", "fedu_regression"]:
        assert 0 <= result[key]["r2"] <= 1
        assert "coeficiente" in result[key]


def test_statistical_tests_school_categories_are_gp_and_ms():
    # As únicas escolas do dataset original são GP e MS.
    result = statistical_tests()
    assert set(result["school"]["categorias"].keys()) == {"GP", "MS"}


def test_statistical_tests_schoolsup_is_the_counterintuitive_direction():
    # Motivo de existir este destaque na interface (com nota de causalidade
    # inversa): quem tem apoio educativo extra tem, em média, nota MAIS
    # BAIXA — não é um erro de sinal, é o resultado real medido nos dados.
    result = statistical_tests()
    cats = result["schoolsup"]["categorias"]
    assert cats["yes"] < cats["no"]


def test_statistical_tests_studytime_effect_is_weaker_with_prior_failures():
    # Motivo de existir a nota de calibração no Otimizador (Ideia J): o
    # efeito de estudar mais é bem mais fraco (e deixa de ser
    # estatisticamente significativo) em quem já reprovou antes.
    result = statistical_tests()
    no_failures = result["studytime_regression_no_failures"]
    with_failures = result["studytime_regression_with_failures"]
    assert no_failures["significativo_5pct"] is True
    assert with_failures["coeficiente"] < no_failures["coeficiente"]


def test_group_stats_works_with_multi_category_variable():
    # group_stats já era genérico (qualquer coluna do dataset), mas nunca
    # tinha sido chamado com uma variável categórica de 5 categorias —
    # confirma que não assume binário nem numérico.
    result = group_stats(variable="Mjob")
    assert set(result["categories"]) == {"at_home", "health", "other", "services", "teacher"}
    assert len(result["avg_grade"]) == len(result["categories"])
    assert len(result["n_students"]) == len(result["categories"])


def test_group_stats_works_with_binary_string_variable():
    # E também deve funcionar com uma variável binária de texto (zona urbana/rural).
    result = group_stats(variable="address")
    assert set(result["categories"]) == {"U", "R"}


def test_group_stats_unknown_column_still_raises():
    # Uma coluna inexistente continua a ser rejeitada com erro HTTP.
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        group_stats(variable="coluna_que_nao_existe")
