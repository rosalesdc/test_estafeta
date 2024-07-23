from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    estafeta_shipping_charge_ids = fields.One2many("estafeta.shipping.charge", "sale_order_id", string="estafeta Rate ")
    estafeta_shipping_charge_id = fields.Many2one("estafeta.shipping.charge", string="estafeta Service")
