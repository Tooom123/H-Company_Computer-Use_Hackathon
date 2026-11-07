"""Public scenario cards: prompts only, never the expected answers in the source."""
from pathlib import Path
import re

PROCEDURES = {
    '01': 'odoo_inventory_read_product',
    '02': 'odoo_inventory_compare_stock',
    '03': 'odoo_supplier_read_contact',
    '04': 'odoo_inventory_missing_reference',
    '05': 'odoo_purchase_prepare_draft',
    '06': 'odoo_purchase_confirm_order',
    '07': 'odoo_purchase_receive_partial',
    '08': 'odoo_purchase_read_backorder',
    '09': 'odoo_purchase_complete_remainder',
    '10': 'odoo_purchase_audit_completed',
}


def load_catalog(path: Path) -> list[dict]:
    source = path.read_text(encoding='utf-8')
    cards = []
    for match in re.finditer(r'^## (\d{2}) — ([^\n]+)\n(.*?)(?=^## |\Z)', source, re.M | re.S):
        number, title, body = match.groups()
        if number not in PROCEDURES:
            continue
        # Only the first quoted user request. Never include oracle paragraphs/tables.
        quoted = re.search(r'^> (.+(?:\n> .+)*)', body, re.M)
        if not quoted:
            raise ValueError(f'Missing spoken prompt for scenario {number}')
        prompt = quoted.group(1).replace('\n> ', ' ').strip()
        card = {'id': number, 'title': title, 'prompt': prompt,
                'procedure_id': PROCEDURES[number], 'requires_reference': int(number) >= 5}
        if int(number) >= 6:
            card['depends_on'] = f'{int(number) - 1:02d}'
        cards.append(card)
    if [card['id'] for card in cards] != list(PROCEDURES):
        raise ValueError('The catalog must contain the ten Odoo scenarios in order')
    return cards
