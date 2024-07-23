from odoo import models, fields, _
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    estafeta_shipping_charge_ids = fields.One2many("estafeta.shipping.charge", "picking_id",
                                                   string="Estafeta Rate")
    estafeta_shipping_charge_id = fields.Many2one("estafeta.shipping.charge", string="Estafeta Service")
    estafeta_no_of_packages = fields.Integer(string='Number of Packages', default=1)

    estafeta_code = fields.Char(string="Tracking code", copy=False, readonly=1)
    estafeta_english_name = fields.Char(string="English Name", copy=False, readonly=1)
    estafeta_local_date_time = fields.Char(string="Local Date Time", copy=False, readonly=1)
    estafeta_spanish_name = fields.Char(string="spanish Name", copy=False, readonly=1)
    estafeta_warehouse_code = fields.Char(string="Warehouse Code", copy=False, readonly=1)
    estafeta_warehouse_name = fields.Char(string="Warehouse Name", copy=False, readonly=1)

    def get_estafeta_rate(self):
        if self.delivery_type == "estafeta_provider":
            self.carrier_id and self.carrier_id.get_estafeta_charges(self)
        else:
            raise ValidationError(_("Estafeta Shipping Id not found"))

    def get_estafeta_tracking_status(self):
        if self.delivery_type == "estafeta_provider":
            self.carrier_id and self.carrier_id.estafeta_provider_get_tracking_status(self)
        else:
            raise ValidationError(_("Estafeta status not found"))
