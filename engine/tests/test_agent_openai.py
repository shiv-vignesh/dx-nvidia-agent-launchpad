from app.adapters.agent_openai import OpenAIAgent


def test_parse_plain_json():
    content = '{"mentioned_meds": ["insulin", "heparin"], "mentioned_vitals": ["SpO2"]}'
    e = OpenAIAgent._parse(content)
    assert e.mentioned_meds == ["insulin", "heparin"]
    assert e.mentioned_vitals == ["SpO2"]


def test_parse_json_in_code_fence_and_prose():
    content = (
        "Here is what the nurse mentioned:\n"
        "```json\n"
        '{"mentioned_meds": ["insulin"], "mentioned_vitals": []}\n'
        "```\n"
        "Let me know if you need more."
    )
    e = OpenAIAgent._parse(content)
    assert e.mentioned_meds == ["insulin"]
    assert e.mentioned_vitals == []


def test_parse_garbage_is_safe_empty():
    # a grounded agent must not invent mentions; unparseable -> nothing mentioned
    e = OpenAIAgent._parse("I could not determine the medications.")
    assert e.mentioned_meds == []
    assert e.mentioned_vitals == []
