import requests
from django.conf import settings
import xmlrpclib
import time
import services

if not hasattr(settings, 'ODOO_SETTINGS'):
    raise Exception('No settings found for Odoo.')


class Odoo:
    CONTRACTS = "contracts"
    CLIENTS = "clients"
    DISCOUNTS = "discounts"
    ACCOUNT_STATEMENT = "account-statement"

    CONTEXT = {
        'host': settings.ODOO_SETTINGS['HOST'],
        'db': settings.ODOO_SETTINGS['DB'],
        'username': settings.ODOO_SETTINGS['USERNAME'],
        'password': settings.ODOO_SETTINGS['PASSWORD']
    }


def post_client(data):
    return requests.post("{0}{1}".format(Odoo.BASE_URL, Odoo.CLIENTS),
                         data=data.update(CONTEXT))


def get_client(client_id):
    url = "{0}{1}/{2}".format(Odoo.BASE_URL, Odoo.CLIENTS, client_id)
    return requests.get(url, data=CONTEXT)


def put_client(client_id, data):
    return requests.put("{0}{1}/{2}".format(Odoo.BASE_URL, Odoo.CLIENTS, client_id),
                        data=data.update(CONTEXT))


def get_contracts():
    return requests.get("{0}{1}".format(Odoo.BASE_URL, Odoo.CONTRACTS), data=CONTEXT)


def set_contract(client_id, data):
    return requests.put("{0}{1}/{2}/{3}".format(Odoo.BASE_URL, Odoo.CLIENTS, client_id, Odoo.CONTRACTS),
                        data=data.update(CONTEXT))


def get_discounts():
    return requests.get("{0}{1}".format(Odoo.BASE_URL, Odoo.DISCOUNTS), data=CONTEXT)


def set_discount(client_id, data):
    return requests.put("{0}{1}/{2}/{3}".format(Odoo.BASE_URL, Odoo.CLIENTS, client_id, Odoo.DISCOUNTS),
                        data=data.update(CONTEXT))


def get_account_statement(client_id, filters):
    url, db, username, password = \
    Odoo.CONTEXT['host'], Odoo.CONTEXT['db'], Odoo.CONTEXT['username'], Odoo.CONTEXT['password']

    common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
    uid = common.authenticate(db, username, password, {})

    models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

    query_filters = [
        ['partner_id', '=', client_id],
        ['reconciled', '=', False],
    ]

    if ('date_start' in filters):
        # Throw error if date_start does not match format '%Y-%m-%d'
        time.strptime(filters['date_start'], '%Y-%m-%d')

        query_filters.append(['date', '>=', filters['date_start']],)

    if ('date_end' in filters):
        # Throw error if date_end does not match format '%Y-%m-%d'
        time.strptime(filters['date_end'], '%Y-%m-%d')

        query_filters.append(['date', '<=', filters['date_end']],)

    cliet_account_moves = models.execute_kw(db, uid, password,
        'account.move.line', 'search_read',
        [query_filters],
    )

    account_ids = list(set(map(
        lambda record: record['account_id'][0],
        cliet_account_moves
    )))

    accounts_filtered = models.execute_kw(db, uid, password,
        'account.account', 'search',
        [[
            ['id', 'in', account_ids],
            '|',
            ['internal_type', '=', 'receivable'],
            ['internal_type', '=', 'liquidity'],
        ]]
    )

    account_state = []

    for record in cliet_account_moves:
        if (record['account_id'][0] not in accounts_filtered):
            continue

        move = {
            "id": record['id'],
            "date": record['date'],
            "name": record['name'],
            "description": "Descripcion pendiente de definir!",
            "reference": "Referencia pendiente de definir!",
        }

        debit = record['debit']
        credit = record['credit']

        if (debit > 0):
            move["amount"] = debit

        if (credit > 0):
            move["amount"] = credit

        account_state.append(move)

    return account_state
