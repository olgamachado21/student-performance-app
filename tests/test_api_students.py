# Testes para o endpoint GET /students (src/api.py) — foco nas colunas de percentil.
from src.api import students


def _call(**overrides):
    # Helper que chama a função do endpoint com valores por omissão razoáveis,
    # substituídos pelos que forem indicados em cada teste.
    defaults = dict(sex=None, internet=None, higher=None, studytime_min=1, studytime_max=4, limit=649)
    defaults.update(overrides)
    return students(**defaults)


def test_students_each_row_has_percentile_fields():
    # Todos os percentis devolvidos devem estar dentro do intervalo válido (0-100).
    result = _call()
    for s in result["students"]:
        assert 0 <= s["percentile_g3"] <= 100
        assert 0 <= s["percentile_studytime"] <= 100
        assert 0 <= s["percentile_absences"] <= 100


def test_students_percentile_g3_ranks_higher_grade_higher():
    # Ordenando os estudantes pela nota, os percentis também devem vir por ordem crescente.
    result = _call()
    by_grade = sorted(result["students"], key=lambda s: s["G3"])
    # Ordenados por nota, os percentis também devem ser (fracamente) crescentes.
    percentiles = [s["percentile_g3"] for s in by_grade]
    assert percentiles == sorted(percentiles)


def test_students_percentile_stable_regardless_of_filter():
    # O percentil é sempre calculado sobre o dataset completo — filtrar não
    # deve mudar o percentil de um estudante que continua a aparecer nos
    # dois pedidos. Nota: outros ficheiros de teste (ex.: test_add_student_
    # reports.py) adicionam estudantes à mesma BD partilhada sem os
    # remover, o que pode empurrar o total para lá do limite máximo do
    # endpoint (649) — por isso só se compara a interseção dos dois
    # conjuntos, em vez de assumir que "unfiltered" tem sempre TODA a gente.
    unfiltered = {s["student_id"]: s["percentile_g3"] for s in _call()["students"]}
    filtered = _call(sex="F")["students"]
    assert len(filtered) > 0
    checked = 0
    for s in filtered:
        if s["student_id"] not in unfiltered:
            continue
        assert s["percentile_g3"] == unfiltered[s["student_id"]]
        checked += 1
    assert checked > 0


def test_students_best_grade_has_top_percentile():
    # O(s) estudante(s) com a melhor nota deve(m) ter um percentil próximo do topo.
    result = _call()
    best = max(result["students"], key=lambda s: s["G3"])
    # O(s) estudante(s) com a nota mais alta da turma deve ter percentil
    # próximo de 100 (pode não ser exatamente 100 se houver empates).
    assert best["percentile_g3"] >= 95
