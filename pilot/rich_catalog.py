"""Read-only cards for the rich Odoo campaign; keep verifier answers out of prompts."""

from pathlib import Path
import re


RICH_PROCEDURES = {
    'R01': 'odoo_rich_crm_read_opportunity',
    'R02': 'odoo_rich_project_read_overdue',
    'R03': 'odoo_rich_purchase_read_partial',
    'R04': 'odoo_rich_purchase_read_backorder',
    'R05': 'odoo_rich_manufacturing_read_bom',
    'R06': 'odoo_rich_sales_read_quote',
    'R07': 'odoo_rich_invoice_read_draft',
    'R08': 'odoo_rich_expenses_read_note',
    'R09': 'odoo_rich_maintenance_read_request',
    'R10': 'odoo_rich_calendar_read_meeting',
}

DEFAULT_RICH_SCENARIOS = Path(__file__).resolve().parents[1] / 'docs/scenarios/odoo-rich-scenarios.md'


def load_rich_catalog(path: Path | None = None) -> list[dict]:
    """Load only the first spoken quotation, never the operator's oracle below it.

    R01–R10 are independent, read-only cases. They must not inherit the old
    numerical >= 5 purchase-workflow rules or the old 01–10 procedure mapping.
    Missing, duplicated or reordered cards fail at startup.
    """
    source = (path or DEFAULT_RICH_SCENARIOS).read_text(encoding='utf-8')
    cards = []
    for match in re.finditer(r'^## (R\d{2}) — ([^\n]+)\n(.*?)(?=^## |\Z)', source, re.M | re.S):
        number, title, body = match.groups()
        if number not in RICH_PROCEDURES:
            raise ValueError(f'Unknown rich scenario {number}')
        quoted = re.search(r'^> (.+(?:\n> .+)*)', body, re.M)
        if not quoted:
            raise ValueError(f'Missing spoken prompt for rich scenario {number}')
        cards.append({
            'id': number,
            'title': title,
            'prompt': quoted.group(1).replace('\n> ', ' ').strip(),
            'procedure_id': RICH_PROCEDURES[number],
            'requires_reference': False,
        })
    if [card['id'] for card in cards] != list(RICH_PROCEDURES):
        raise ValueError('The rich catalog must contain R01–R10 exactly once, in order')
    return cards
