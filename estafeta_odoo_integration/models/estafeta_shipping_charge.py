from odoo import models, fields


class EstafetaShippingCharge(models.Model):
    _name = "estafeta.shipping.charge"
    _rec_name = "estafeta_service_name"

    estafeta_service_code = fields.Char(string="Service Code")
    estafeta_service_name = fields.Char(string="Service Name")
    estafeta_modality = fields.Char(string="Modality")
    estafeta_total_amount = fields.Char(string="Total Amount")
    sale_order_id = fields.Many2one("sale.order", string="Sales Order")
    picking_id = fields.Many2one("stock.picking", string="Delivery Order")

    def set_service(self):
        self.ensure_one()
        if self.sale_order_id:
            carrier = self.sale_order_id.carrier_id
            self.sale_order_id.estafeta_shipping_charge_id = self.id
            self.sale_order_id.carrier_id = carrier.id
            self.sale_order_id.set_delivery_line(carrier,
                                                 self.estafeta_total_amount)  # This Line Used For set updated rate in sale order line
        if self.picking_id:
            self.picking_id.estafeta_shipping_charge_id = self.id


