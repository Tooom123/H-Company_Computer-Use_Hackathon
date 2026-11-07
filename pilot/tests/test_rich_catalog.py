"""Offline contract and oracle separation checks for the rich read-only campaign."""

from pathlib import Path

import pytest
import yaml

from hcs_agent.contract import InterventionRequest
from hcs_agent.procedures import Procedure
from pilot.rich_catalog import DEFAULT_RICH_SCENARIOS, RICH_PROCEDURES, load_rich_catalog


def test_read_only_rich_cards_bind_with_real_engine_schema():
    cards = load_rich_catalog()
    assert [card['id'] for card in cards] == list(RICH_PROCEDURES)
    for card in cards:
        assert card['requires_reference'] is False
        assert 'depends_on' not in card
        procedure = Procedure.model_validate(yaml.safe_load(
            (DEFAULT_RICH_SCENARIOS.parent / f"{card['procedure_id']}.yaml").read_text()
        ))
        request = InterventionRequest(
            software='odoo', software_version='20.0', goal=card['prompt'],
            procedure_id=card['procedure_id'], mode='act',
        )
        bound = procedure.bound(request)
        assert not procedure.parameters
        assert procedure.id == card['procedure_id']
        assert 'holo-rich.localhost:18091' in bound.agent_instructions
        assert 'Holo — Déjà Bu Démo · DONNÉES FICTIVES' in bound.agent_instructions
        assert 'holo.localhost:18090' not in bound.agent_instructions
        assert 'HACKATHON — Boutique Démo' not in bound.verification_instructions
        assert 'Aucune modification métier' in bound.plan().planned_changes[0]
        assert 'correct_environment' in bound.checks
        assert any('Créer, modifier' in action for action in bound.plan().forbidden_actions)


def test_crm_oracle_is_not_in_actor_goal_plan_or_instructions():
    card = load_rich_catalog()[0]
    procedure = Procedure.model_validate(yaml.safe_load(
        (DEFAULT_RICH_SCENARIOS.parent / f"{card['procedure_id']}.yaml").read_text()
    ))
    bound = procedure.bound(InterventionRequest(
        software='odoo', goal=card['prompt'], procedure_id=procedure.id, mode='act',
    ))
    actor = card['prompt'] + bound.agent_instructions + bound.plan().model_dump_json()
    for expected in ('350', 'Premier contact', 'Relancer et documenter', '4 novembre 2026'):
        assert expected not in actor
        assert expected in ' '.join(bound.checks.values())
    assert 'Revue opérateur' not in card['prompt']


@pytest.mark.parametrize('corruption', ['missing', 'duplicate', 'unknown', 'no_prompt'])
def test_invalid_rich_catalog_fails_before_run(tmp_path: Path, corruption: str):
    source = DEFAULT_RICH_SCENARIOS.read_text()
    if corruption == 'missing':
        source = source.replace('## R10 —', '## Supprimé —')
    elif corruption == 'duplicate':
        source += '\n## R01 — Doublon\n\n> Demande supplémentaire.\n'
    elif corruption == 'unknown':
        source = source.replace('## R10 —', '## R11 —')
    else:
        source = source.replace('> Dans CRM,', 'Dans CRM,', 1)
    target = tmp_path / 'scenarios.md'
    target.write_text(source)
    with pytest.raises(ValueError):
        load_rich_catalog(target)
