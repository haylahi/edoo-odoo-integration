# -*- coding: utf-8 -*-

import json
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import ugettext as _

from userprofiles.models import (
    StudentTutorRelationship,
    TutorProfile,
    StudentProfile)

from utils.controllers import ControllerResponse
from utils import services as utilities
from integrations.services import get_integration_id

import services
from forms import (
    ContractForm,
    TutorPermissionsFormset,
    PaymentResponsableConfigurationForm
)
from integrations.services import set_integration_configuration

from userprofiles.models import StudentProfile

'''
integration configurations keys:

client_id
payment_responsable_client_id
payment_responsable_comercial_id
allow_view_account_statement
allow_view_voucher


'''


def registration(request, student_id):

    # Get the student profile
    student_profile = StudentProfile.objects.get(id=student_id)

    # Get the student tutors
    relationships = StudentTutorRelationship.objects.filter(student_profile=student_profile)
    student_tutors = [relationship.tutor for relationship in relationships]

    response = ControllerResponse(request, _(u"Mensaje de respuesta por defecto"))

    payment_configuration_form = PaymentResponsableConfigurationForm()
    permissions_formset = TutorPermissionsFormset(initial=[
        {
            'tutor': tutor,
            'allow_view_account_statement': True,
            'allow_view_voucher': False
        }
        for tutor in student_tutors
    ], )

    response.sets({
        'student_profile': student_profile,
        'student_tutors': student_tutors,
        'payment_configuration_form': payment_configuration_form,
        'permissions_formset': permissions_formset
    })

    return response


def register_student(request, request_data, student_id):
    # Get the student profile
    student_profile = StudentProfile.objects.get(id=student_id)

    # Get the student tutors
    relationships = StudentTutorRelationship.objects.filter(student_profile=student_profile)
    student_tutors = [relationship.tutor for relationship in relationships]

    response = ControllerResponse(request, _(u"Mensaje de respuesta por defecto"))

    payment_configuration_form = PaymentResponsableConfigurationForm(request_data)
    permissions_formset = TutorPermissionsFormset(request_data)

    if payment_configuration_form.is_valid() and permissions_formset.is_valid():

        # Billing data
        comercial_id = payment_configuration_form.cleaned_data.get('comercial_id')
        comercial_address = payment_configuration_form.cleaned_data.get('comercial_address')
        comercial_number = payment_configuration_form.cleaned_data.get('comercial_number')
        client_id = payment_configuration_form.cleaned_data.get('client_id')
        comercial_name = payment_configuration_form.cleaned_data.get('comercial_name')

        # TODO: xmlshit ----------------------------------------------------------------------
        set_integration_configuration(
            integration_key='odoo',
            object_instance=student_profile,
            key='client_id',
            value='{}'.format(client_id)
        )

        set_integration_configuration(
            integration_key='odoo',
            object_instance=student_profile,
            key='payment_responsable_client_id',
            value='{}'.format('payment_responsable_client_id')
        )

        set_integration_configuration(
            integration_key='odoo',
            object_instance=student_profile,
            key='payment_responsable_comercial_id',
            value='{}'.format('payment_responsable_comercial_id')
        )
        # TODO: xmlshit ----------------------------------------------------------------------

        # Save configuration for each tutor
        for tutor_configuration in permissions_formset.cleaned_data:
            tutor = tutor_configuration['tutor']
            allow_view_account_statement = tutor_configuration['allow_view_account_statement']
            allow_view_voucher = tutor_configuration['allow_view_voucher']

            set_integration_configuration(
                integration_key='odoo',
                object_instance=relationships.filter(tutor=tutor).first(),
                key='allow_view_account_statement',
                value='{}'.format(allow_view_account_statement)
            )

            set_integration_configuration(
                integration_key='odoo',
                object_instance=relationships.filter(tutor=tutor).first(),
                key='allow_view_voucher',
                value='{}'.format(allow_view_voucher)
            )

        # Return a redirect
        return ControllerResponse(
            request,
            _(u"Cliente registrado exitosamente en Odoo"),
            message_position='default',
            redirect='registration_backend_register_student'
        )

    response.sets({
        'student_profile': student_profile,
        'student_tutors': student_tutors,
        'payment_configuration_form': payment_configuration_form,
        'permissions_formset': permissions_formset
    })

    return response


def tutor_invoice(request):

    username = request.GET.get('username', None)

    user = User.objects.get(username=username)
    client_id = get_integration_id(user)

    success, response = services.call_client(client_id)

    return JsonResponse(response)


def set_contract(request, username, request_data, redirect_url=None):
    """ Student registration manager. """

    # Validate permission
    request.user.can(
        'userprofiles.add_studentprofile',
        raise_exception=True)

    # Build redirect response
    redirect_response = HttpResponseRedirect(request.META['HTTP_REFERER'])
    if redirect_url:
        redirect_response = HttpResponseRedirect(redirect_url)

    # Retrieve from HTTP
    contract_form = ContractForm(
        data=request_data)

    if contract_form.is_valid():
        contract_id = contract_form.cleaned_data.get('contract_id')
        products = contract_form.cleaned_data.get('products')
        payments_responsible = contract_form.cleaned_data.get('payments_responsible')
        name = contract_form.cleaned_data.get('name')
        nit = contract_form.cleaned_data.get('nit')
        phone = contract_form.cleaned_data.get('phone')
        address = contract_form.cleaned_data.get('address')
        # tutors_visibility = contract_form.cleaned_data.get('tutors_visibility')

        # Get users
        user = User.objects.get(username=username)
        tutor = User.objects.get(username=payments_responsible)

        # Get integration object
        client_id = get_integration_id(user)
        tutor_client_id = get_integration_id(tutor)

        contract_data = {
            'contract_id': contract_id,
            'products': products
        }

        tutor_client_data = {
            'invoice_identifier': nit,
            'invoice_name': name,
            'invoice_phone': phone,
            'invoice_address': address
        }

        client_data = {
            'super_client_id': tutor_client_id
        }

        u_success, u_response = services.set_contract(client_id, contract_data)

        t_success, t_response = services.update_client(client_id, client_data)

        c_success, c_response = services.update_client(tutor_client_id, tutor_client_data)

        redirect_response = HttpResponseRedirect(reverse('registration_backend'))

        return ControllerResponse(
            request,
            _(u"Registro completado exitosamente"),
            message_position='default',
            redirect=redirect_response)

    # Else
    response = ControllerResponse(
        request,
        _(u"Se encontraron algunos problemas en el formulario de estudiante"),
        message_position='default',
        redirect=redirect_response)

    # Transport data and errors
    utilities.transport_form_through_session(
        request,
        contract_form,
        'contract_form')

    response.set_error()
    return response


def search_clients(request, query):
    return JsonResponse(services.search_clients(query), safe=False)
