from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from hcs_agent.runner import _rebind_unchanged_target


def fixture():
    info = NS(bundle_id=None, is_front=True, title='Pipeline', url='https://example.org/odoo/crm',
              viewport=(0, 0, 1470, 956))
    items = [NS(role='AXTextField', name='Rechercher…', box=(600, 100, 200, 30), enabled=True, selected=False),
             NS(role='AXButton', name='CRM', box=(100, 100, 100, 30), enabled=True, selected=False)]
    return {'instruction': 'Click Rechercher…', 'kind': 'click', 'target': 0}, info, items


def test_unrelated_geometry_and_traversal_order_do_not_repeat_the_model_call():
    plan, info, items = fixture()
    fresh = list(reversed(deepcopy(items)))
    fresh[0].box = (102, 100, 100, 30)
    rebound = _rebind_unchanged_target(plan, info, items, info, fresh)
    assert rebound == {**plan, 'target': 1}
    assert plan['target'] == 0  # do not modify the actor's recorded response


@pytest.mark.parametrize('change', ['target_box', 'name', 'selected', 'enabled', 'duplicate', 'count',
                                    'url', 'front', 'viewport', 'done', 'blocked', 'info', 'invalid_index'])
def test_changed_or_ambiguous_evidence_still_requires_a_new_plan(change):
    plan, info, items = fixture()
    current, fresh = deepcopy(info), deepcopy(items)
    if change == 'target_box': fresh[0].box = (610, 100, 200, 30)
    elif change in ('name', 'selected', 'enabled'):
        setattr(fresh[1], change, 'Sales' if change == 'name' else not getattr(fresh[1], change))
    elif change == 'duplicate':
        items.append(deepcopy(items[0])); fresh.append(deepcopy(fresh[0]))
    elif change == 'count': fresh.append(deepcopy(fresh[1]))
    elif change == 'url': current.url += '/other'
    elif change == 'front': current.is_front = False
    elif change == 'viewport': current.viewport = (0, 0, 1000, 800)
    elif change in ('done', 'blocked'): plan[change] = True
    elif change == 'info': plan['kind'] = 'info'
    elif change == 'invalid_index': plan['target'] = True
    assert _rebind_unchanged_target(plan, info, items, current, fresh) is None
