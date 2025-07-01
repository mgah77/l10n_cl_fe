from odoo import fields, models


class SiiRegionalOffices(models.Model):
    _name = "sii.regional.offices"
    _description = "Unidades SII"

    name = fields.Char("Regional Office Name")
    city_ids = fields.Many2many("res.city", string="Ciudades",)
