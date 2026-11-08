"""The restricted live rehearsal cannot fill forms or activate save controls."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from hcs_agent import coach_v2_runtime as runtime
from hcs_agent.coach_v2 import CoachDecision, CoachProtocolError

@pytest.mark.parametrize('action,label,text', [
    ('click', 'Create skill', None), ('click', 'Create', None),
    ('click', 'Upgrade', None), ('click', 'New session', None),
    ('type', 'Name *', 'example'), ('click', 'Copy API key', None),
])
def test_readonly_rehearsal_rejects_effects_before_input(monkeypatch, action, label, text):
    url = 'https://platform.hcompany.ai/agents/skills'
    monkeypatch.setenv('HCS_V2_READONLY_REHEARSAL', '1')
    monkeypatch.setattr(runtime, 'foreground_url', lambda: url)
    target = SimpleNamespace(name=label, role='AXTextField' if action == 'type' else 'AXButton')
    desktop = Mock()
    with pytest.raises(CoachProtocolError, match='read-only'):
        runtime.perform(CoachDecision(action=action, target=1, text=text, speech='Next step.'), target, url, desktop)
    assert not desktop.mock_calls
