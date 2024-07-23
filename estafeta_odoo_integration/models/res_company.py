import requests
import logging
from odoo import models, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    use_estafeta_shipping_provider = fields.Boolean(copy=False, string="Are You Use Estafeta Shipping Provider.?",
                                                    help="If use Estafeta shipping provider than value set TRUE.",
                                                    default=False)
    estafeta_token_api_url = fields.Char(string="Token API URL", help="Put the URl for getting the Token hear.",
                                         copy=False)
    estafeta_rate_api_url = fields.Char(string="Rate API URL", help="Put the URl for getting the Rate hear.",
                                        copy=False)
    estafeta_label_api_url = fields.Char(string="Label API URL", help="Put the URl for getting the Label hear.",
                                         copy=False)
    estafeta_tracking_api_url = fields.Char(string="Tracking API URL",
                                            help="Put the URl for getting the Tracking hear.",copy=False)
    estafeta_suscriber_id = fields.Char(string="Suscriber Id", help="Unique Customer Groud Id Provided by Estafeta",
                                        copy=False)
    estafeta_customer_number = fields.Char(string="Customer Number",
                                           help="Client number used by Estafeta to identify clients", copy=False)
    estafeta_sales_organization = fields.Char(string="Sales Organization",
                                              help="In the quality environment it is 112, in the productive environment it is: 570",
                                              copy=False, default="112")

    estafeta_api_key = fields.Char(string="API Key", copy=False)
    estafeta_shared_secret = fields.Char(string="Shared Secret", copy=False)
    estafeta_api_token = fields.Char(string="API Token", copy=False, readonly=True)
    estafeta_id = fields.Char(string="System ID",
                              help="It is an identifier of your system, it is the Id that you want to put.", copy=False)
    estafeta_name = fields.Char(string="System Name",
                                help=" It is a name of your system, it is the name that you want to give.", copy=False)

    def estafeta_generate_token(self):
        api_url = (
            "{0}?grant_type=client_credentials&client_id={"
            "1}&client_secret={2}&scope=execute").format(self.estafeta_token_api_url,
                                                         self.estafeta_api_key, self.estafeta_shared_secret)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {}
        try:
            response = requests.request("POST", api_url, headers=headers, data=payload)
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data['access_token']:
                    self.estafeta_api_token = response_data['access_token']
                    return {
                        'effect': {
                            'fadeout': 'slow',
                            'message': "Yeah! Estafeta Token Retrieved successfully!!",
                            'img_url': '/web/static/img/smile.svg',
                            'type': 'rainbow_man',
                        }
                    }
                else:
                    raise ValidationError(response_data)
            else:
                raise ValidationError(response.text)
        except Exception as e:
            raise ValidationError(e)

    def estafeta_generate_authentication_token_using_crone(self, ):
        for credential_id in self.search([]):
            try:
                if credential_id.use_estafeta_shipping_provider:
                    credential_id.estafeta_generate_token()
            except Exception as e:
                _logger.info("Getting an error in Generate Token request Odoo to Estafeta: {0}".format(e))
