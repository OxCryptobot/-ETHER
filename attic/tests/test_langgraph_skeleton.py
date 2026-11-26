from gems.selenite.langgraph_skeleton import draft, critique, PlanState


def test_draft_and_critique():
    state: PlanState = {"objective": "write hello", "steps": [], "notes": ""}
    state = draft(state)
    assert len(state["steps"]) >= 2
    state = critique(state)
    assert "critiqued" in state["notes"]
