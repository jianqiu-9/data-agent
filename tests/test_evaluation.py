from data_agent.evaluation import EvaluationCase, EvaluationRun, evaluate_retrieval, evaluate_tasks


def test_evaluation_counts_failures_and_versions() -> None:
    cases = [EvaluationCase(case_id="a", expected="ok", actual="ok"), EvaluationCase(case_id="b", expected="ok", actual="error")]
    run = EvaluationRun(dataset_version="v1", model_version="m1", prompt_version="p1", tool_version="t1", index_version="i1")
    report = evaluate_tasks(cases, run=run)
    assert report["task_success_rate"] == 0.5
    assert report["failed_case_ids"] == ["b"]
    assert report["versions"]["dataset"] == "v1"


def test_retrieval_recall_uses_expected_evidence_ids() -> None:
    report = evaluate_retrieval({"q1": {"d1"}, "q2": {"d2"}}, {"q1": ["d1", "d3"], "q2": ["d3"]}, k=2)
    assert report["recall_at_k"] == 0.5
