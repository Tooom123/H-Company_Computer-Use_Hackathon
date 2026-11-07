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
        assert 'https://holo-demo.62.83.79.254.sslip.io' in bound.agent_instructions
        assert 'https://holo-demo.62.83.79.254.sslip.io' in bound.verification_instructions
        assert 'https://holo-demo.62.83.79.254.sslip.io' in bound.checks['correct_environment']
        assert 'holo-rich.localhost:18091' not in procedure.model_dump_json()
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


def test_project_stage_oracle_is_separate_from_actor_method():
    card = load_rich_catalog()[1]
    procedure = Procedure.model_validate(yaml.safe_load(
        (DEFAULT_RICH_SCENARIOS.parent / f"{card['procedure_id']}.yaml").read_text()
    ))
    bound = procedure.bound(InterventionRequest(
        software='odoo', goal=card['prompt'], procedure_id=procedure.id, mode='act',
    ))
    actor = card['prompt'] + bound.agent_instructions + bound.plan().model_dump_json()
    for stage in ('À préparer', 'En cours', 'À valider'):
        assert stage not in actor
        assert stage in bound.checks['task_stages']
    assert 'colonne' in actor and 'statut individuel' in actor
    assert 'filtres par défaut' in bound.agent_instructions
    assert 'filtres par défaut' in bound.verification_instructions
    assert 'pastilles de statut individuel' in bound.checks['task_stages']


@pytest.mark.parametrize('scenario_id, withheld_answers', [
    ('R03', ('18 unités', '9 reçues', 'Jardins Drinks', 'P00066', 'WH/IN/00049')),
    ('R05', ('KAHOL Gin', 'Livre Guide du sans alcool', 'Rondelles agrumes Citrons')),
    ('R07', ('Studio Lisière', '99,40', '93,77', '5,63', '21,90')),
])
def test_corrected_scenarios_keep_oracle_out_of_actor(scenario_id, withheld_answers):
    card = next(card for card in load_rich_catalog() if card['id'] == scenario_id)
    raw = yaml.safe_load(
        (DEFAULT_RICH_SCENARIOS.parent / f"{card['procedure_id']}.yaml").read_text()
    )
    # The verifier may know expected answers. Even a new verifier-only value must
    # remain absent from the bound actor goal, instructions and approval plan.
    oracle_marker = 'VERIFIER_ONLY_EXPECTED_VALUE_731904'
    raw['postcondition']['verification_instructions'] += ' ' + oracle_marker
    raw['postcondition']['checks'][0]['prompt'] += ' ' + oracle_marker
    procedure = Procedure.model_validate(raw)
    bound = procedure.bound(InterventionRequest(
        software='odoo', goal=card['prompt'], procedure_id=procedure.id, mode='act',
    ))
    actor = card['prompt'] + bound.agent_instructions + bound.plan().model_dump_json()
    for expected in (*withheld_answers, oracle_marker):
        assert expected not in actor
    assert oracle_marker in bound.verification_instructions
    assert oracle_marker in bound.checks['correct_environment']


def test_purchase_verification_restores_order_before_final_observation():
    procedure = Procedure.model_validate(yaml.safe_load(
        (DEFAULT_RICH_SCENARIOS.parent / 'odoo_rich_purchase_read_partial.yaml').read_text()
    ))
    bound = procedure.bound(InterventionRequest(
        software='odoo', goal='Lire la commande et la laisser ouverte.',
        procedure_id=procedure.id, mode='act',
    ))
    assert set(bound.checks) == {
        'correct_environment', 'correct_order', 'partial_quantities',
        'supplier_products_visible', 'partial_status', 'order_left_open',
    }
    assert 'dernière capture' in bound.checks['order_left_open']
    instructions = bound.verification_instructions
    assert 'reviens à la commande' in instructions
    assert 'avant ta réponse finale' in instructions
    assert 'jamais à partir d’une capture antérieure' in instructions
    assert 'false pour order_left_open' in instructions
    # Existing quantity checks remain verifier-only and are not weakened.
    assert '18 unités commandées et 9 reçues' in bound.checks['partial_quantities']


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
