"""Home Assistant over its REST API, with one address and long-lived token for the whole app:
sensor states for the weather station, and to-do lists (e.g. Apple Reminders copied there
by an iPhone Shortcut) for the plan's to-dos."""
import datetime

import requests


def _connection(cfg):
    ha = cfg.get('home_assistant') or {}
    if not ha.get('url') or not ha.get('token'):
        raise RuntimeError('no Home Assistant address and token set')
    return ha['url'].rstrip('/'), {'Authorization': f"Bearer {ha['token']}"}


def ping(cfg):
    """Raises unless Home Assistant answers with this address and token."""
    url, headers = _connection(cfg)
    requests.get(f'{url}/api/', headers=headers, timeout=10).raise_for_status()


def state(cfg, entity):
    """An entity's state and unit, e.g. ('59.4', '°F'). Unknown or unavailable is an error."""
    url, headers = _connection(cfg)
    r = requests.get(f'{url}/api/states/{entity}', headers=headers, timeout=10)
    r.raise_for_status()
    d = r.json()
    if d['state'] in ('unknown', 'unavailable'):
        raise RuntimeError(f"{entity} is {d['state']}")
    return d['state'], d.get('attributes', {}).get('unit_of_measurement')


def todo_items(cfg, entity, today):
    """The open items of a to-do list that are due today or earlier, or have no due date."""
    url, headers = _connection(cfg)
    r = requests.post(f'{url}/api/services/todo/get_items?return_response', headers=headers, timeout=10,
                      json={'entity_id': entity, 'status': ['needs_action']})
    r.raise_for_status()
    items = r.json()['service_response'][entity]['items']
    return [i['summary'].strip() for i in items
            if i.get('summary', '').strip() and (not i.get('due') or datetime.date.fromisoformat(i['due'][:10]) <= today)]
