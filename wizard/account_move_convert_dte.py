import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from datetime import datetime
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)


class AccountMoveConvertDTE(models.TransientModel):
    _name = "account.move.convert.dte"

    @api.model
    def default_get(self, fields):
        res = super(AccountMoveConvertDTE, self).default_get(fields)
        move_ids = self.env['account.move'].browse(self.env.context['active_ids']) if self.env.context.get('active_model') == 'account.move' else self.env['account.move']
        if any(not m.document_class_id.es_voucher() for m in move_ids):
            raise UserError("Solo se pueden retimbrar Vouchers")
        if 'company_id' in fields:
            res['company_id'] = move_ids.company_id.id or self.env.company.id
        if 'move_ids' in fields:
            res['move_ids'] = [(6, 0, move_ids.ids)]
        return res

    move_ids = fields.Many2many(
        'account.move', 
        domain=[
            ('state', '=', 'posted'),
            ('document_class_id.dte', '=', False)
        ]
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Use Specific Journal',
        required=True,
        compute='_compute_journal_id',
        readonly=False,
        store=True,
        check_company=True,
        help='If empty, uses the journal of the journal entry to be reversed.',
    )
    jdc_id = fields.Many2one(
        "account.journal.sii_document_class",
        string="Documents Type",
        check_company=True,
    )
    company_id = fields.Many2one('res.company', required=True, readonly=True)

    @api.depends('move_ids')
    def _compute_journal_id(self):
        for record in self:
            if record.journal_id:
                record.journal_id = record.journal_id
            else:
                journals = record.move_ids.journal_id.filtered(lambda x: x.active)
                record.journal_id = journals[0] if journals else None

    def convert(self):
        to_send = {}
        for inv in self.move_ids:
            inv.journal_document_class_id = self.jdc_id
            inv.document_class_id = self.jdc_id.sii_document_class_id
            inv._set_next_sequence()
            inv.sii_result = "NoEnviado"
            if inv.journal_id.restore_mode or self._context.get("restore_mode", False):
                inv.sii_result = "Proceso"
            else:
                inv._validaciones_uso_dte()
                inv._timbrar()
                to_send.setdefault(inv.company_id, self.env['account.move'])
                to_send[inv.company_id] += inv
        for company, invoices in to_send.items():
            ISCP = self.env["ir.config_parameter"].sudo()
            tiempo_pasivo = datetime.now()
            tipo_trabajo = 'envio'
            self.env["sii.cola_envio"].create(
                {
                    "company_id": company.id,
                    "doc_ids": invoices.ids,
                    "model": "account.move",
                    "user_id": self.env.uid,
                    "tipo_trabajo": tipo_trabajo,
                    "date_time": tiempo_pasivo,
                    "send_email": False
                    if company.dte_service_provider == "SIICERT"
                    or not ISCP.get_param("account.auto_send_email", default=True)
                    else True,
                }
            )