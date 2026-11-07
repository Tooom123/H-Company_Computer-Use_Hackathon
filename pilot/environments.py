"""Fixed demo identities; selecting a profile does not open or reset Odoo."""

ENVIRONMENTS = {
    'minimal': {
        'id': 'odoo-minimal-v1',
        'label': 'Odoo · laboratoire initial',
        'entry_url': 'http://holo.localhost:18090/web/login',
        'company': 'HACKATHON — Boutique Démo — DONNÉES FICTIVES',
        'fixture_version': 'initial',
    },
    'rich': {
        'id': 'odoo-rich-v2.1',
        'label': 'Odoo · démo enrichie',
        'entry_url': 'http://holo-rich.localhost:18091/odoo/crm',
        'company': 'Holo — Déjà Bu Démo · DONNÉES FICTIVES',
        'fixture_version': '20261107-v2.1',
    },
}


def get_environment(name: str) -> dict:
    try:
        return dict(ENVIRONMENTS[name])
    except KeyError:
        raise ValueError(f'Unknown demo environment: {name}') from None
