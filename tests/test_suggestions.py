# Testes para src/suggestions.py — sugestão de valores prováveis para campos
# em falta ao adicionar um estudante, usando k-NN sobre estudantes semelhantes.
from src.add_student import FORM_FIELDS
from src.data_processing import get_processed_data
from src.suggestions import suggest_field_values


def test_no_known_fields_falls_back_to_whole_dataset():
    # Sem nenhum campo conhecido, a "vizinhança" é o dataset inteiro.
    df = get_processed_data()
    result = suggest_field_values(df, {})
    assert result["based_on"] == []
    assert result["n_similar"] == len(df)
    assert set(result["suggestions"].keys()) == set(FORM_FIELDS)


def test_all_fields_known_returns_no_suggestions():
    # Com todos os campos já preenchidos, não há nada a sugerir.
    df = get_processed_data()
    known = {
        "school": "GP", "sex": "F", "age": 17, "studytime": 2,
        "absences": 4, "failures": 0, "G1": 12, "G2": 13,
    }
    result = suggest_field_values(df, known)
    assert result["suggestions"] == {}
    assert result["n_similar"] == 0
    assert set(result["based_on"]) == set(known.keys())


def test_partial_fields_only_suggests_remaining_fields():
    # Só os campos que faltam devem aparecer nas sugestões.
    df = get_processed_data()
    result = suggest_field_values(df, {"studytime": 4, "sex": "F"})
    assert set(result["based_on"]) == {"studytime", "sex"}
    assert set(result["suggestions"].keys()) == set(FORM_FIELDS) - {"studytime", "sex"}
    # k-NN limitado ao nº de vizinhos configurado, não a todo o dataset
    assert 0 < result["n_similar"] <= 15


def test_suggestion_shifts_with_known_fields():
    df = get_processed_data()
    # Estudar mais deve, em média, sugerir notas mais altas do que estudar menos
    # (mesma direção da correlação positiva estudo -> desempenho no dataset).
    low_study = suggest_field_values(df, {"studytime": 1})
    high_study = suggest_field_values(df, {"studytime": 4})
    assert high_study["suggestions"]["G1"] >= low_study["suggestions"]["G1"]


def test_none_and_empty_values_are_ignored_as_unknown():
    # Valores None ou string vazia devem ser tratados como "campo desconhecido", não como valor real.
    df = get_processed_data()
    result = suggest_field_values(df, {"studytime": None, "sex": "", "age": 17})
    assert result["based_on"] == ["age"]
    assert "studytime" in result["suggestions"]
    assert "sex" in result["suggestions"]


def test_unknown_keys_outside_form_fields_are_ignored():
    # Chaves que não fazem parte dos campos do formulário devem ser simplesmente ignoradas.
    df = get_processed_data()
    result = suggest_field_values(df, {"G3": 15, "nome": "Ana", "studytime": 3})
    assert result["based_on"] == ["studytime"]


def test_suggested_numeric_values_are_within_valid_range():
    # Todos os valores numéricos sugeridos devem respeitar a escala válida de cada campo.
    df = get_processed_data()
    result = suggest_field_values(df, {"sex": "M"})
    s = result["suggestions"]
    assert 15 <= s["age"] <= 22
    assert 1 <= s["studytime"] <= 4
    assert 0 <= s["absences"] <= 93
    assert 0 <= s["failures"] <= 4
    assert 0 <= s["G1"] <= 20
    assert 0 <= s["G2"] <= 20


def test_suggested_categorical_values_are_valid():
    # Valores categóricos sugeridos devem pertencer às categorias válidas.
    df = get_processed_data()
    result = suggest_field_values(df, {"studytime": 3})
    s = result["suggestions"]
    assert s["school"] in {"GP", "MS"}
    assert s["sex"] in {"F", "M"}


def test_similar_students_empty_when_no_fields_known():
    # Sem campos conhecidos, não há uma vizinhança concreta a mostrar.
    df = get_processed_data()
    result = suggest_field_values(df, {})
    assert result["similar_students"] == []


def test_similar_students_populated_when_fields_known():
    # Com pelo menos um campo conhecido, deve devolver uma lista pequena de estudantes semelhantes.
    df = get_processed_data()
    result = suggest_field_values(df, {"studytime": 4, "sex": "F"})
    assert 0 < len(result["similar_students"]) <= 6
    for student in result["similar_students"]:
        assert set(student.keys()) == set(FORM_FIELDS)


def test_similar_students_respect_known_categorical_field_when_possible():
    df = get_processed_data()
    result = suggest_field_values(df, {"sex": "F"})
    # Como há muitas raparigas no dataset, os vizinhos mais próximos devem
    # coincidir no campo já indicado sempre que isso for possível.
    assert all(s["sex"] == "F" for s in result["similar_students"])
