from odoo import models, fields


class PackageDetails(models.Model):
    _inherit = 'stock.package.type'

    package_carrier_type = fields.Selection(selection_add=[("estafeta_provider", "Estafeta")],
                                            ondelete={'estafeta_provider': 'set default'})
