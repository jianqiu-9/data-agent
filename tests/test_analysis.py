from data_agent.analysis import DataAnalysisAgent


def test_analysis_reconciles_explicit_measure_and_keeps_query_id() -> None:
    result = {"status": "succeeded", "query_id": "Q1", "row_count": 2, "rows": [{"region": "华东", "gmv": "12.50"}, {"region": "华南", "gmv": "7.25"}]}
    analysis = DataAnalysisAgent().summarize(result, measures=["gmv"])
    assert analysis["status"] == "verified"
    assert analysis["totals"]["gmv"] == "19.75"
    assert analysis["query_id"] == "Q1"
    assert analysis["dimensions"] == ["region"]


def test_analysis_rejects_incomplete_result_and_unknown_measure() -> None:
    result = {"status": "succeeded", "query_id": "Q1", "row_count": 100, "rows": [{"gmv": "12.50"}]}
    assert DataAnalysisAgent().summarize(result, measures=["gmv"])["status"] == "partial"
    assert DataAnalysisAgent().summarize(result, measures=["missing"])["status"] == "insufficient_evidence"


def test_analysis_rejects_malformed_rows_and_nonfinite_measure() -> None:
    base = {"status": "succeeded", "query_id": "Q1", "row_count": 1}
    assert DataAnalysisAgent().summarize({**base, "rows": ["bad"]}, measures=["gmv"])["status"] == "insufficient_evidence"
    assert DataAnalysisAgent().summarize({**base, "rows": [{"gmv": "NaN"}]}, measures=["gmv"])["status"] == "insufficient_evidence"
