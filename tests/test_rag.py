from pathlib import Path

import pytest

from data_agent.rag import AccessScope, KnowledgeIndex, KnowledgeManifest, KnowledgeQA, LLMAnswerModel, load_knowledge_index


def test_knowledge_ingest_search_revoke_and_republish(tmp_path: Path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("# 权限申请\n\n需要先选角色，然后选择有效期。", encoding="utf-8")
    index = KnowledgeIndex()
    manifest = KnowledgeManifest(knowledge_base_id="kb", tenant_id="t1", document_id="guide", title="指南", source_uri="kb://guide", version="v1", access_policy_id="analysts")
    index.ingest(source, manifest)
    index.ingest(source, manifest)
    scope = AccessScope(tenant_id="t1", policy_ids=frozenset({"analysts"}))
    assert len(index.search("权限申请角色", scope=scope).results) == 1
    assert not index.search("权限申请角色", scope=AccessScope(tenant_id="t2", policy_ids=frozenset({"analysts"}))).results
    assert not index.search("权限申请角色", scope=AccessScope(tenant_id="t1", policy_ids=frozenset())).results
    index.revoke("kb", "guide")
    assert not index.search("权限申请角色", scope=scope).results
    source.write_text("# 权限申请\n\n先选择角色，再填写理由。", encoding="utf-8")
    index.ingest(source, manifest.model_copy(update={"version": "v2"}))
    result = index.search("权限申请理由", scope=scope)
    assert len(result.results) == 1
    assert result.results[0].version == "v2"


def test_knowledge_requires_policy_and_confined_source(tmp_path: Path) -> None:
    source = tmp_path / "guide.txt"
    source.write_text("权限指南", encoding="utf-8")
    with pytest.raises(ValueError):
        KnowledgeManifest(knowledge_base_id="kb", tenant_id="t", document_id="d", title="x", source_uri="kb://d", version="v1", access_policy_id="")
    index = KnowledgeIndex()
    manifest = KnowledgeManifest(knowledge_base_id="kb", tenant_id="t", document_id="d", title="x", source_uri="kb://d", version="v1", access_policy_id="p")
    with pytest.raises(ValueError):
        index.ingest(source, manifest, allowed_root=tmp_path / "another")


def test_knowledge_answer_cites_only_authorized_evidence(tmp_path: Path) -> None:
    source = tmp_path / "guide.txt"
    source.write_text("申请权限时选择角色并填写理由。", encoding="utf-8")
    index = KnowledgeIndex()
    index.ingest(source, KnowledgeManifest(knowledge_base_id="kb", tenant_id="t", document_id="d", title="指南", source_uri="kb://d", version="v1", access_policy_id="p"))
    qa = KnowledgeQA(index)
    result = qa.answer("如何申请权限", scope=AccessScope(tenant_id="t", policy_ids=frozenset({"p"})))
    assert result.status == "retrieved"
    assert result.citations[0]["source_uri"] == "kb://d"
    assert "申请权限" in result.answer
    assert qa.answer("如何申请权限", scope=AccessScope(tenant_id="t", policy_ids=frozenset())).status == "insufficient_evidence"


def test_manifest_loader_only_imports_explicit_files(tmp_path: Path) -> None:
    import json

    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "approved.md").write_text("# 订单\n订单表粒度为一行一单。", encoding="utf-8")
    (root / "private.md").write_text("秘密资料", encoding="utf-8")
    metadata = KnowledgeManifest(knowledge_base_id="kb", tenant_id="t", document_id="approved", title="订单", source_uri="kb://approved", version="v1", access_policy_id="p")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"path": "approved.md", "metadata": metadata.model_dump(mode="json")}]), encoding="utf-8")
    index = load_knowledge_index(manifest, allowed_root=root)
    scope = AccessScope("t", frozenset({"p"}))
    assert index.search("订单表", scope=scope).results
    assert not index.search("秘密资料", scope=scope).results


def test_answer_model_rejects_fabricated_citation(tmp_path: Path) -> None:
    class Model:
        def invoke(self, prompt):
            return '{"answer":"随意回答","citation_ids":["99"]}'

    source = tmp_path / "guide.md"
    source.write_text("# 权限\n权限申请要填写理由。", encoding="utf-8")
    index = KnowledgeIndex()
    index.ingest(source, KnowledgeManifest(knowledge_base_id="kb", tenant_id="t", document_id="d", title="指南", source_uri="kb://d", version="v1", access_policy_id="p"))
    result = KnowledgeQA(index, model=LLMAnswerModel(Model())).answer("如何申请权限", scope=AccessScope("t", frozenset({"p"})))
    assert result.status == "retrieved"
    assert result.citations[0]["document_id"] == "d"
