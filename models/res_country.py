# -*- coding: utf-8 -*-
from odoo import fields, models, api


class ResCountry(models.Model):
    _inherit = "res.country"

    rut_natural = fields.Char("RUT persona natural", size=11)
    rut_juridica = fields.Char("RUT persona juridica", size=11)
    rut_otro = fields.Char("RUT otro", size=11)


    @api.constrains('address_format')
    def _check_address_format(self):
        for record in self:
            if record.address_format:
                address_fields = self.env['res.partner']._formatting_address_fields() + ['state_code', 'state_name', 'country_code', 'country_name', 'company_name', 'comuna_name']
                try:
                    record.address_format % {i: 1 for i in address_fields}
                except (ValueError, KeyError):
                    raise UserError(_('The layout contains an invalid format key'))
