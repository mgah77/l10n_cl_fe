import ast
import logging
from datetime import datetime, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ColaEnvio(models.Model):
    _name = "sii.cola_envio"
    _description = "Cola de envío DTE Persistente al SII"

    doc_ids = fields.Char(string="Id Documentos",)
    model = fields.Char(string="Model destino",)
    user_id = fields.Many2one("res.users",)
    tipo_trabajo = fields.Selection(
        [
            ("pasivo", "pasivo"),
            ("envio", "Envío"),
            ("consulta", "Consulta"),
            ("persistencia", "Persistencia Respuesta"),
        ],
        string="Tipo de trabajo",
    )
    active = fields.Boolean(string="Active", default=True,)
    n_atencion = fields.Char(string="Número de Atención",)
    set_pruebas = fields.Boolean(string="Set de pruebas",
                                 default=False)
    date_time = fields.Datetime(string="Auto Envío al SII",)
    send_email = fields.Boolean(string="Auto Enviar Email", default=False,)
    company_id = fields.Many2one("res.company", string="Company")
    intento = fields.Integer(string="Intento", default=0, readonly=True)

    def enviar_email(self, doc):
        doc.send_exchange()

    def _es_doc(self, doc):
        if hasattr(doc, "sii_message"):
            return doc.sii_message
        return True

    def _procesar_tipo_trabajo(self):
        self.intento += 1
        admin = self.env.ref("base.user_admin")
        if self.user_id in [self.env.ref("base.user_root"), self.env.ref("base.public_user")] :
            self.user_id = admin.id
        if self.user_id.id != admin.id and not self.user_id.active:
            _logger.warning("¡Usuario %s desactivado!" % self.user_id.name)
            return
        docs = (
            self.env[self.model]
            .with_context(user=self.user_id.id, company_id=self.company_id.id,
                          set_pruebas=self.set_pruebas)
            .browse(ast.literal_eval(self.doc_ids))
        )
        if self.tipo_trabajo == "persistencia":
            if self.date_time and datetime.now() >= self.date_time:
                for doc in docs:
                    if (
                        doc.partner_id
                        and doc.sii_xml_request.create_date <= (datetime.now() + timedelta(days=8))
                        and self.env["sii.respuesta.cliente"].search(
                            [
                                ("id", "in", doc.respuesta_ids.ids),
                                ("company_id", "=", self.company_id.id),
                                ("recep_envio", "=", "no_revisado"),
                                ("type", "=", "RecepcionEnvio"),
                            ]
                        )
                    ):
                        self.enviar_email(doc)
                    else:
                        docs -= doc
                if not docs:
                    self.unlink()
                else:
                    persistente = (
                        self.env["ir.config_parameter"].sudo().get_param("account.auto_send_persistencia", default=24)
                    )
                    self.date_time = datetime.now() + timedelta(hours=int(persistente))

            return
        if self.tipo_trabajo == "pasivo":
            if docs[0].sii_xml_request and docs[0].sii_xml_request.state in [
                "Aceptado",
                "Enviado",
                "Rechazado",
                "Anulado",
            ]:
                self.unlink()
                return
            try:
                envio_id = docs.do_dte_send(self.n_atencion)
                if envio_id.sii_send_ident:
                    self.tipo_trabajo = "consulta"
            except Exception as e:
                _logger.warning("Error en Envío automático %s" % str(e), exc_info=True)
            return
        if self._es_doc(docs[0]) and docs[0].sii_result in ["Proceso", "Reparo", "Rechazado", "Anulado"]:
            if self.send_email and docs[0].sii_result in ["Proceso", "Reparo"]:
                for doc in docs:
                    if not doc.partner_id:
                        docs -= doc
                        continue
                    self.enviar_email(doc)
                if not docs:
                    self.unlink()
                    return
                self.tipo_trabajo = "persistencia"
                persistente = (
                    self.env["ir.config_parameter"].sudo().get_param("account.auto_send_persistencia", default=24)
                )
                self.date_time = datetime.now() + timedelta(hours=int(persistente))
                return
            self.unlink()
            return
        if self.tipo_trabajo == "consulta":
            try:
                docs.ask_for_dte_status()
            except Exception as e:
                _logger.warning("Error en Consulta, %s" % str(e), exc_info=True)
        elif self.tipo_trabajo == "envio" and (
            not docs[0].sii_xml_request
            or not docs[0].sii_xml_request.sii_send_ident
            or docs[0].sii_xml_request.state not in ["Aceptado", "Enviado", "EnProceso"]
        ):
            envio_id = False
            try:
                envio_id = docs.with_context(user=self.user_id.id, company_id=self.company_id.id).do_dte_send(
                    self.n_atencion
                )
                if envio_id.sii_send_ident:
                    self.tipo_trabajo = "consulta"
            except Exception as e:
                _logger.warning("Error en envío Cola: %s" % str(e), exc_info=True)
        elif (
            self.tipo_trabajo == "envio"
            and docs[0].sii_xml_request
            and (
                docs[0].sii_xml_request.sii_send_ident
                or docs[0].sii_xml_request.state in ["Aceptado", "Enviado", "Rechazado", "EnProceso"]
            )
        ):
            self.tipo_trabajo = "consulta"

    def reset_intentos(self):
        query = """
            UPDATE sii_cola_envio
            SET intento = 0
            WHERE intento >= 10
            AND create_date <= (NOW() - INTERVAL '1 day')
        """
        self.env.cr.execute(query)

    @api.model
    def _cron_procesar_cola(self):
        self.reset_intentos()
        query = [
            ("active", "=", True),
            ('intento', '<=', 10),
        ]
        ids = self.search(query + [('tipo_trabajo', '=', 'envio'),], limit=20)
        if ids:
            for c in ids:
                try:
                    c._procesar_tipo_trabajo()
                except Exception as e:
                    _logger.warning(f"error al procesartipo trabajo envio: {e}", exc_info=True)
        ids = self.search(query + [
            ('tipo_trabajo', '=', 'pasivo'),
            ('date_time', '<=', datetime.now())], limit=20)
        if ids:
            for c in ids:
                try:
                    c._procesar_tipo_trabajo()
                except Exception as e:
                    _logger.warning(f"error al procesartipo trabajo pasivo {e}", exc_info=True)
        ids = self.search(query + [('tipo_trabajo', '=', 'consulta')], limit=20)
        if ids:
            for c in ids:
                try:
                    c._procesar_tipo_trabajo()
                except Exception as e:
                    _logger.warning(f"error al procesar tipo trabajo consulta {e}", exc_info=True)
        ids = self.search(query + [('tipo_trabajo', '=', 'persistencia')], limit=20)
        if ids:
            for c in ids:
                try:
                    c._procesar_tipo_trabajo()
                except Exception as e:
                    _logger.warning(f"error al procesartipo trabajo persistencia {e}", exc_info=True)
