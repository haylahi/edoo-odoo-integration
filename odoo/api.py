import requests
from django.conf import settings
import xmlrpclib
import time
import services
import json


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

    CUSTOM_SETTINGS = {
        'family_code_prefix': settings.ODOO_SETTINGS['FAMILY_CODE_PREFIX']
    }


def post_client(data):
    url, db, username, password = get_odoo_settings()

    uid = services.authenticate_user(url, db, username, password)

    odoo_client_id = models.execute_kw(db, uid, password,
        'res.partner', 'create',
        [{
            'name': data['name'],
        }]
    )

    odoo_client = models.execute_kw(db, uid, password,
        'res.partner', 'search_read',
        [[['id', '=', odoo_client_id]]]
    )

    return odoo_client[0]


def get_client(client_id):
    url, db, username, password = get_odoo_settings()

    uid = services.authenticate_user(url, db, username, password)

    models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

    client = models.execute_kw(db, uid, password,
        'res.partner', 'search_read',
        [[['id', '=', client_id]]]
    )

    if not len(client):
        return None

    return client[0]


def put_client(client_id, data):
    return requests.put("{0}{1}/{2}".format(Odoo.BASE_URL, Odoo.CLIENTS, client_id),
                        data=data.update(CONTEXT))


def get_contracts():
    return requests.get("{0}{1}".format(Odoo.CONTEXT.get('HOST', ''), Odoo.CONTRACTS))


def set_contract(client_id, data):
    return requests.put("{0}{1}/{2}/{3}".format(Odoo.BASE_URL, Odoo.CLIENTS, client_id, Odoo.CONTRACTS),
                        data=data.update(CONTEXT))


def get_discounts():
    return requests.get("{0}{1}".format(Odoo.BASE_URL, Odoo.DISCOUNTS), data=CONTEXT)


def set_discount(client_id, data):
    return requests.put("{0}{1}/{2}/{3}".format(Odoo.BASE_URL, Odoo.CLIENTS, client_id, Odoo.DISCOUNTS),
                        data=data.update(CONTEXT))


def get_odoo_settings():
    return [
        Odoo.CONTEXT['host'],
        Odoo.CONTEXT['db'],
        Odoo.CONTEXT['username'],
        Odoo.CONTEXT['password']
    ]


def get_allowed_invoice_journals():
    return settings.ODOO_SETTINGS['ALLOWED_INVOICE_JOURNALS']


def get_allowed_payment_journals():
    return settings.ODOO_SETTINGS['ALLOWED_PAYMENT_JOURNALS']


def get_account_statement(client_id, comercial_id, filters):
    url, db, username, password = get_odoo_settings()
    comercial_id = int(comercial_id)
    client_id = int(client_id)

    allowed_invoice_journals = get_allowed_invoice_journals()
    allowed_payment_journals = get_allowed_payment_journals()

    uid = services.authenticate_user(url, db, username, password)

    models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

    query_filters = [
        '|',
        ['partner_id', '=', comercial_id],
        ['commercial_partner_id', '=', comercial_id],
        ['journal_id', 'in', allowed_invoice_journals]
    ]

    if ('date_start' in filters):
        # Throw error if date_start does not match format '%Y-%m-%d'
        time.strptime(filters['date_start'], '%Y-%m-%d')

        query_filters.append(['date', '>=', filters['date_start']])

    if ('date_end' in filters):
        # Throw error if date_end does not match format '%Y-%m-%d'
        time.strptime(filters['date_end'], '%Y-%m-%d')

        query_filters.append(['date', '<=', filters['date_end']])

    """
    --------------------------------------------
    Invoices
    --------------------------------------------
    """

    # Get client invoices.
    account_invoices = models.execute_kw(db, uid, password,
        'account.invoice', 'search_read',
        [query_filters],
        {'order': 'company_id, date_invoice'}
    )

    account_invoice_line_ids = []

    transactions_by_company = []
    company_invoices = []
    prev_company_id = None
    prev_company_name = None

    # Get the information that interests us, grouping by company.
    for account_invoice in account_invoices:
        company_id = account_invoice['company_id'][0]
        company_name = account_invoice['company_id'][1]

        if (prev_company_id and prev_company_id != company_id):
            transactions_by_company.append({
                'company_id': prev_company_id,
                'company_name': prev_company_name,
                'invoices': company_invoices,
                'payments': [],
                'balance': 0
            })

            company_invoices = []

        invoice  = {
            'id': account_invoice['id'],
            'number': account_invoice['number'],
            'date_invoice': account_invoice['date_invoice'],
            'date_due': account_invoice['date_due'],
            'amount_total': account_invoice['amount_total'],
            'invoice_line_ids': account_invoice['invoice_line_ids'],
            'reconciled': account_invoice['reconciled'],
            'journal_id': account_invoice['journal_id']
        }

        account_invoice_line_ids.extend(account_invoice['invoice_line_ids'])

        company_invoices.append(invoice)
        prev_company_id = company_id
        prev_company_name = company_name

    # The algorithm of the previous loop does not add the last company_invoices.
    # Add it if the loop was entered.
    if prev_company_id:
        transactions_by_company.append({
            'company_id': prev_company_id,
            'company_name': prev_company_name,
            'invoices': company_invoices,
            'payments': [],
            'balance': 0
        })

    # Get the details of the invoices to get the descriptions.
    account_invoice_lines = models.execute_kw(db, uid, password,
        'account.invoice.line', 'search_read',
        [[['id', 'in', account_invoice_line_ids]]]
    )

    invoice_line_indexed = {}
    for account_invoice_line in account_invoice_lines:
        invoice_line_indexed[account_invoice_line['id']] = {
            'display_name': account_invoice_line['display_name'],
            'price_subtotal': account_invoice_line['price_subtotal']
        }

    # Include descriptions.
    for company_data in transactions_by_company:
        for invoice in company_data['invoices']:
            invoice['invoice_lines'] = map(
                lambda x: {
                    'id': x,
                    'display_name': invoice_line_indexed[x]['display_name'],
                    'price_subtotal': invoice_line_indexed[x]['price_subtotal']
                },
                invoice['invoice_line_ids']
            )

            # This key will no longer serve us.
            invoice.pop('invoice_line_ids')

    query_filters = [
        ['partner_id', '=', client_id],
        ['journal_id', 'in', allowed_payment_journals]
    ]

    if ('date_start' in filters):
        # Throw error if date_start does not match format '%Y-%m-%d'
        time.strptime(filters['date_start'], '%Y-%m-%d')

        query_filters.append(['payment_date', '>=', filters['date_start']])

    if ('date_end' in filters):
        # Throw error if date_end does not match format '%Y-%m-%d'
        time.strptime(filters['date_end'], '%Y-%m-%d')

        query_filters.append(['payment_date', '<=', filters['date_end']])


    """
    --------------------------------------------
    Payments
    --------------------------------------------
    """

    # Get client payments.
    account_payments = models.execute_kw(db, uid, password,
        'account.payment', 'search_read',
        [query_filters],
        {'order': 'company_id, payment_date'}
    )

    company_payments = [];
    prev_company_id = None
    prev_company_name = None

    # Get the information that interests us, grouping by company.
    for account_payment in account_payments:
        company_id = account_payment['company_id'][0]
        company_name = account_payment['company_id'][1]

        if (prev_company_id and prev_company_id != company_id):
            # Add payment info to the respective company.
            for company_data in transactions_by_company:
                if (company_data['company_id'] == company_id):
                    company_data['payments'] = company_payments
                    break

            company_payments = []

        payment = {
            'id': account_payment['id'],
            'display_name': account_payment['display_name'],
            'payment_date': account_payment['payment_date'],
            'amount': account_payment['amount'],
            'state': account_payment['state'],
            'journal_id': account_payment['journal_id']
        }

        company_payments.append(payment)
        prev_company_id = company_id
        prev_company_name = company_name

    # The algorithm of the previous loop does not add the last company_payments.
    # Add it if the loop was entered.

    if prev_company_id:
        # Add payment info to the respective company.
        for company_data in transactions_by_company:
            if (company_data['company_id'] == prev_company_id):
                company_data['payments'] = company_payments
                break

    """
    --------------------------------------------
    Balance calc for each company
    --------------------------------------------
    """

    account_acount_ids = models.execute_kw(db, uid, password,
        'account.account', 'search',
        [[['internal_type', '=', 'receivable']]]
    )

    # Get invoice lines.
    account_move_lines = models.execute_kw(db, uid, password,
        'account.move.line', 'search_read',
        [[
            ['partner_id', '=', client_id],
            ['date', '<', filters['date_start']],
            ['account_id', 'in', account_acount_ids]
        ]],
        {'order': 'company_id'}
    )

    prev_company_id = None
    current_balance = 0

    for account_move_line in account_move_lines:
        company_id = account_move_line['company_id'][0]

        if (prev_company_id and prev_company_id != company_id):
            # Add balance to the respective company.
            for company_data in transactions_by_company:
                if (company_data['company_id'] == company_id):
                    company_data['balance'] = current_balance
                    break

            current_balance = 0

        current_balance += account_move_line['balance']
        prev_company_id = company_id


    if prev_company_id:
        # Add balance to the respective company.
        for company_data in transactions_by_company:
            if (company_data['company_id'] == prev_company_id):
                company_data['balance'] = current_balance
                break


    return transactions_by_company


def search_clients(query):
    url, db, username, password = get_odoo_settings()

    uid = services.authenticate_user(url, db, username, password)
    models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

    partners = models.execute_kw(db, uid, password,
        'res.partner', 'search_read',
        [[['name', 'ilike', query], ['child_ids', '!=', False]]]
    )

    partner_ids = list(map(lambda x: int(x['id']), partners))

    comercial_partners = models.execute_kw(db, uid, password,
        'res.partner', 'search_read',
        [[['parent_id', 'in', partner_ids], ['type', '=', 'invoice']]]
    )

    result = []

    for partner in partners:
        print 'Current partner id: ', partner['id']
        # Look for comercial partner

        # Logic 1
        cm = next((x for x in comercial_partners if x['parent_id'][0] == partner['id']), None)

        # Logic 2
        # cm = None
        # for comercial_partner in comercial_partners:
        #     if comercial_partner['parent_id'][0] == partner['id']:
        #         cm = comercial_partner
        #         break

        addresses = [cm['street'], cm['street2'], cm['city']] if cm else []

        client_object = {
            'display_as': 'user',
            'client_id': partner['id'],
            'comercial_id': cm['id'] if cm else None,
            'comercial_name': cm['name'] if cm else None,
            'comercial_number': cm['vat'] if cm else None,
            'comercial_address': " ".join(address for address in addresses if address),
            'profile_picture': None,
            'first_name': partner['name'],
            'role': "Cliente registrado"
        }

        result.append(client_object)

    return result


def register_client(
        student_client_id,
        student_profile,
        student_tutors,
        client_id,
        comercial_id,
        comercial_address,
        comercial_number,
        comercial_name):
    url, db, username, password = get_odoo_settings()

    uid = services.authenticate_user(url, db, username, password)
    models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

    # Scenario 1: creation
    if not student_client_id:
        if client_id or comercial_id:
            raise Exception('Inconsistent parameters.')

        family_code_prefix = Odoo.CUSTOM_SETTINGS['family_code_prefix']

        # Create family contact
        family_code = family_code_prefix + student_profile.code
        tutors_emails = map(lambda x: x.user.email, student_tutors) if student_tutors else []

        family_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [{
            'ref': family_code,
            'name': student_profile.user.last_name,
            'email': ",".join(tutors_emails)
        }])

        # Create family comercial contact
        comercial_code = family_code_prefix + student_profile.code + family_code_prefix

        family_comercial_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [{
            'ref': comercial_code,
            'street': comercial_address,
            'vat': comercial_number,
            'name': comercial_name,
            'email': '',
            'parent_id': family_id,
            'type': 'invoice'
        }])

        # Create student contact
        student_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [{
            'ref': student_profile.code,
            'name': student_profile.user.first_name + ' ' + student_profile.user.last_name,
            'email': student_profile.user.email,
            'parent_id': family_id
        }])

        # Response
        client_id = student_id
        payment_responsable_client_id = family_id
        payment_responsable_comercial_id = family_comercial_id


    # TODO: transform into the following shape

    return (
        client_id,
        payment_responsable_client_id,
        payment_responsable_comercial_id
    )


def get_payment_responsable_data(client_id):
    url, db, username, password = get_odoo_settings()

    uid = services.authenticate_user(url, db, username, password)
    models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

    partner = models.execute_kw(db, uid, password,
        'res.partner', 'search_read',
        [[['id', '=', client_id]]]
    )

    if len(partner) != 1:
        raise Exception('No client found for id ' + client_id)

    partner = partner[0]

    comercial_partners = models.execute_kw(db, uid, password,
        'res.partner', 'search_read',
        [[['parent_id', '=', partner['id']], ['type', '=', 'invoice']]]
    )

    # A client must have one comercial partner
    if len(comercial_partners) == 0:
        raise Exception('No comercial partner found for client ' + client_id)
    elif len(comercial_partners) > 1:
        raise Exception('More than one comercial partner found for client ' + client_id)

    comercial_partner = comercial_partners[0]

    addresses = [
        comercial_partner['street'],
        comercial_partner['street2'],
        comercial_partner['city']
    ]

    payment_responsable_client_id = client_id
    payment_responsable_comercial_id = comercial_partner['id']
    payment_responsable_comercial_name = comercial_partner['name']
    payment_responsable_comercial_number = comercial_partner['vat']
    payment_responsable_comercial_address = " ".join(address for address in addresses if address)

    return {
        'display_as': 'user',
        'client_id': payment_responsable_client_id,
        'comercial_id': payment_responsable_comercial_id,
        'comercial_name': payment_responsable_comercial_name,
        'comercial_number': payment_responsable_comercial_number,
        'comercial_address': payment_responsable_comercial_address,
        'profile_picture': "http://lh3.googleusercontent.com/-zhYZ2MAkVfQ/AAAAAAAAAAI/AAAAAAAAAAA/RDrrSIIg9Jw/photo.jpg",
        'first_name': "Cliente S. A.",
        'role': "Cliente registrado"
    }
