# Testes para o endpoint GET /model-metrics (src/api.py) — métricas dos
# modelos treinados, incluindo comparação com um baseline ingénuo.
from fastapi import HTTPException

from src.api import model_metrics


def test_model_metrics_returns_expected_sections():
    # O resultado deve ter exatamente estas 4 secções.
    result = model_metrics()
    assert set(result.keys()) == {
        "regressao_habitos", "regressao_completo", "classificacao", "baseline_ingenuo",
    }


def test_model_metrics_never_leaks_internal_model_path():
    # Detalhes internos (caminho do ficheiro do modelo no disco) nunca devem ser expostos à API.
    result = model_metrics()
    for section in result.values():
        assert "model_path" not in section


def test_model_metrics_regression_sections_have_r2_mae_rmse():
    # Cada secção de regressão deve indicar o melhor modelo e as métricas completas.
    result = model_metrics()
    for variant in ("regressao_habitos", "regressao_completo"):
        section = result[variant]
        assert section["best_model"] in section["results"]
        for metrics in section["results"].values():
            assert "R2" in metrics and "MAE" in metrics and "RMSE" in metrics
            assert "CV_R2_mean" in metrics


def test_model_metrics_classification_section_has_full_metrics():
    # A secção de classificação (aprovado/reprovado) deve ter todas as métricas usuais.
    section = model_metrics()["classificacao"]
    assert section["best_model"] in section["results"]
    for metrics in section["results"].values():
        for key in ("Accuracy", "Precision", "Recall", "F1", "ROC_AUC", "CV_F1_mean"):
            assert key in metrics


def test_model_metrics_missing_file_raises_404(tmp_path, monkeypatch):
    # Se o ficheiro de métricas não existir no disco, o endpoint deve devolver 404, não rebentar.
    from src import api as api_module

    monkeypatch.setattr(api_module.config, "REPORTS_DIR", tmp_path)
    try:
        model_metrics()
        assert False, "esperava-se HTTPException para ficheiro em falta"
    except HTTPException as exc:
        assert exc.status_code == 404


# ----------------------------------------------------------------------------
# Baseline "ingénuo" (prever sempre a média da turma) — referência mínima
# para mostrar que os modelos reais acrescentam valor real.
# ----------------------------------------------------------------------------
def test_compute_naive_baseline_structure():
    # O baseline deve prever sempre um valor dentro da escala válida, com erro positivo.
    from src.data_processing import get_processed_data
    from src.train_model import compute_naive_baseline

    result = compute_naive_baseline(get_processed_data())
    assert 0 <= result["predicted_value"] <= 20
    assert result["MAE"] > 0
    assert result["RMSE"] > 0
    assert result["RMSE"] >= result["MAE"]  # RMSE nunca é menor que o MAE


def test_model_metrics_includes_baseline_section():
    # A secção de baseline deve trazer as métricas de erro e a % de melhoria dos modelos reais.
    result = model_metrics()
    baseline = result["baseline_ingenuo"]
    assert "MAE" in baseline and "RMSE" in baseline and "predicted_value" in baseline
    assert "melhoria_habitos_pct" in baseline
    assert "melhoria_completo_pct" in baseline


def test_model_metrics_real_models_beat_the_baseline():
    # Se isto falhar, o modelo "a sério" está a ter um desempenho pior do
    # que simplesmente prever a média — sinal de um problema grave no
    # treino, não só nesta funcionalidade.
    result = model_metrics()
    baseline_mae = result["baseline_ingenuo"]["MAE"]
    habitos_best = result["regressao_habitos"]["results"][result["regressao_habitos"]["best_model"]]
    completo_best = result["regressao_completo"]["results"][result["regressao_completo"]["best_model"]]
    assert habitos_best["MAE"] < baseline_mae
    assert completo_best["MAE"] < baseline_mae


def test_model_metrics_completo_improves_more_than_habitos_over_baseline():
    # O modelo com G1/G2 tem sempre muito mais poder preditivo do que só
    # com hábitos — a melhoria face ao baseline devia refletir isso.
    result = model_metrics()
    baseline = result["baseline_ingenuo"]
    assert baseline["melhoria_completo_pct"] > baseline["melhoria_habitos_pct"]
