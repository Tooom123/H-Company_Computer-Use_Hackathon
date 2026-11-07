"""Private launcher configuration. Never include credential values in errors."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit


def browser_credentials(directory: Path, *, expected_origin: str) -> dict[str, str]:
    """Load the existing two-layer demo login, scoped to one HTTPS origin."""
    try:
        public = json.loads((directory / 'public-access.json').read_text())
        odoo = json.loads((directory / 'demo-access.json').read_text())
        url = urlsplit(public['url'])
        if (url.scheme != 'https' or url.username or url.password or
                f'{url.scheme}://{url.netloc}' != expected_origin):
            raise ValueError()
        values = {'basic_username': public['login'], 'basic_password': public['password'],
                  'odoo_username': odoo['login'], 'odoo_password': odoo['password']}
        if not all(isinstance(value, str) and value.strip() for value in values.values()):
            raise ValueError()
        return values
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('Private browser access files are missing, invalid, or belong to another origin.') from None
