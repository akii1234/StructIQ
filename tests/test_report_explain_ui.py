from StructIQ.reporting.report_generator import generate_report_html


_MINIMAL_PLAN = {
    "decision": "action_required",
    "tasks": [],
    "dominated_tasks": [],
    "changes": [],
    "impact": {},
    "execution_plan": [],
    "plan_summary": "",
}
_MINIMAL_INSIGHTS = {
    "services": [],
    "anti_patterns": [],
    "recommendations": [],
    "system_summary": "",
}


def test_explain_section_present_in_report():
    """HTML report must contain the ask-a-question UI block."""
    html = generate_report_html(
        run_id="test-run-123",
        phase1_output={"files": [], "classified_files": [], "modules": {}},
        dep_graph={"nodes": [], "edges": []},
        dep_analysis={"cycles": [], "coupling_scores": [], "entry_points": []},
        arch_insights=_MINIMAL_INSIGHTS,
        mod_plan=_MINIMAL_PLAN,
    )
    assert "test-run-123" in html
    assert "explain" in html.lower() or "ask" in html.lower()


def test_explain_section_contains_run_id_in_fetch_url():
    """The fetch URL in the explain block must include the actual run_id."""
    html = generate_report_html(
        run_id="my-special-run-456",
        phase1_output={"files": [], "classified_files": [], "modules": {}},
        dep_graph={"nodes": [], "edges": []},
        dep_analysis={"cycles": [], "coupling_scores": [], "entry_points": []},
        arch_insights=_MINIMAL_INSIGHTS,
        mod_plan=_MINIMAL_PLAN,
    )
    assert "/explain/my-special-run-456" in html
