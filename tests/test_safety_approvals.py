from __future__ import annotations

from core.safety.approvals import build_cloud_financial_preview


def test_cloud_financial_preview_contains_path():
    items = [{"source_type": "file_content", "provenance": "/tmp/finance.xlsx"}]
    preview = build_cloud_financial_preview(items, redaction_summary={"file_content": 0})
    assert preview["details"]["file_paths"][0] == "/tmp/finance.xlsx"
    assert preview["details"]["redaction_summary"]["file_content"] == 0
