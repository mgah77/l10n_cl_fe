# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api
from . import controllers, models, wizard, report
import logging


_logger = logging.getLogger(__name__)
incompatible_modules = ['l10n_cl', 'l10n_latam_base', 'l10n_latam_invoice_document', 'l10n_latam_account_sequence']

def _check_pre_init(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    modules = env["ir.module.module"].sudo().search([
        ('name', 'in', incompatible_modules)
    ])
    if modules:
        _logger.warning("Existen módulos incompatibles")
        cr.execute("""
            UPDATE ir_model_data set module = 'l10n_cl_fe'
            WHERE name IN ('UF', 'UTM', 'OTR') AND module = 'l10n_cl' AND model='res.currency'
            """)

def _set_default_configs(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICPSudo = env["ir.config_parameter"].sudo()
    ICPSudo.set_param("account.auto_send_dte", 1)
    ICPSudo.set_param("account.auto_send_email", True)
    ICPSudo.set_param("account.auto_send_persistencia", 24)

    #Eliminar incompatibilidad con l10n_cl
    modules = env["ir.module.module"].sudo().search([
        ('name', 'in', incompatible_modules),
        ('state', '!=', 'uninstalled'),
    ])

    if modules:
        rut_type = env.ref("l10n_cl.it_RUT")
        cr.execute("""
            UPDATE res_partner
            SET document_number = vat,
                vat = CONCAT('CL', REPLACE(REPLACE(vat, '.', ''), '-', ''))
            WHERE l10n_latam_identification_type_id = %s
        """, (rut_type.id,))

        """ @TODO otras asimilaciones y desinstalar """
