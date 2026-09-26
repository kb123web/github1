from pathlib import Path

from agent_core import _default_options, _manual_recognition, _risk_flags, create_plan, update_storyboard


def test_default_plan_has_three_30_second_options():
    options = _default_options(_manual_recognition("Portable blender"))
    assert len(options) == 3
    assert all(sum(shot["duration"] for shot in option["storyboard"]) == 30 for option in options)


def test_storyboard_update_limits_duration_and_fields():
    plan = create_plan("Portable blender", Path("."))
    result = update_storyboard(plan, [{"duration": 99, "scene": "A", "visual": "B", "dialogue": "C", "subtitle": "D"}])
    assert result["selected_storyboard"][0]["duration"] == 12


def test_risk_flags():
    assert _risk_flags("100% best")
    assert _risk_flags("guarantee cure")
