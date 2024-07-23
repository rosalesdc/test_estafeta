import binascii
import logging
import requests
import json
from odoo import models, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[("estafeta_provider", "Estafeta")],
                                     ondelete={'estafeta_provider': 'set default'})
    estafeta_provider_package_id = fields.Many2one('stock.package.type', string="Package Info", help="Default Package")

    estafeta_parcel_id = fields.Selection([('1', 'Envelope'),
                                           ('4', 'Package'),
                                           ('5', 'Pallet'),
                                           ], string="parcel Id", default='1')
    estafeta_output_type = fields.Selection([('FILE_PDF', 'FILE_PDF'),
                                             ('FILE_PDF_SC', 'FILE_PDF_SC'),
                                             ('FILE_THERMAL_SEQUENCE', 'FILE_THERMAL_SEQUENCE'),
                                             ('SECTION_DOCUMENT', 'SECTION_DOCUMENT')
                                             ], string="Output Type", default='FILE_PDF')
    estafeta_output_group = fields.Selection([('INDIVIDUAL', 'INDIVIDUAL'),
                                              ('SYNC_REFERENCE', 'SYNC_REFERENCE'),
                                              ('REQUEST', 'REQUEST')
                                              ], string="Output Group", default='REQUEST')
    estafeta_response_mode = fields.Selection([('SYNC_INLINE', 'SYNC_INLINE'),
                                               ('SYNC_REFERENCE', 'SYNC_REFERENCE')
                                               ], string="Response Mode", default='SYNC_INLINE')
    estafeta_printing_template = fields.Char(string="Printing Template",
                                             help="The value to be used must be provided by Estafeta Team.")

    estafeta_service_type_id = fields.Char(string="Service Type Id", default='70')
    estafeta_default_service_type_id = fields.Boolean(string="Default Service Type Id", default=False)

    def check_address_details(self, address_id, required_fields):
        """
            check the address of Shipper and Recipient
            param : address_id: res.partner, required_fields: ['zip', 'city', 'country_id', 'street']
            return: missing address message
        """

        res = [field for field in required_fields if not address_id[field]]
        if res:
            return "Missing Values For Address :\n %s" % ", ".join(res).replace("_id", "")

    def estafeta_provider_rate_shipment(self, order):
        """
           This method is used for get rate of shipment
           param : order : sale.order
           return: 'success': False : 'error message' : True
           return: 'success': True : 'error_message': False
        """
        # Shipper and Recipient Address
        shipper_address_id = order.warehouse_id.partner_id
        recipient_address_id = order.partner_shipping_id

        shipper_address_error = self.check_address_details(shipper_address_id, ['zip', 'city', 'country_id', 'street'])
        recipient_address_error = self.check_address_details(recipient_address_id,
                                                             ['zip', 'city', 'country_id', 'street'])
        total_weight = sum([(line.product_id.weight * line.product_uom_qty) for line in order.order_line]) or 0.0

        product_weight = (order.order_line.filtered(
            lambda x: not x.is_delivery and x.product_id.type == 'product' and x.product_id.weight <= 0))
        product_name = ", ".join(product_weight.mapped('product_id').mapped('name'))

        if shipper_address_error or recipient_address_error or product_name:
            return {'success': False, 'price': 0.0,
                    'error_message': "%s %s  %s " % (
                        "Shipper Address : %s \n" % (shipper_address_error) if shipper_address_error else "",
                        "Recipient Address : %s \n" % (recipient_address_error) if recipient_address_error else "",
                        "product weight is not available : %s" % (product_name) if product_name else ""
                    ),
                    'warning_message': False}
        estafeta_shipping_charge_obj = self.env['estafeta.shipping.charge']
        company_id = self.company_id
        sender_zip = shipper_address_id.zip or ""
        receiver_zip = recipient_address_id.zip or ""
        package_id = self.estafeta_provider_package_id

        try:
            header = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'apikey': company_id.estafeta_api_key,
                'Authorization': "Bearer {}".format(company_id.estafeta_api_token)
            }
            api_url = company_id.estafeta_rate_api_url
            request_data = json.dumps({
                "Origin": sender_zip,
                "Destination": [
                    receiver_zip
                ],
                "PackagingType": package_id.name,
                "Dimensions": {
                    "Length": package_id.packaging_length or 0,
                    "Width": package_id.width or 0,
                    "Height": package_id.height or 0,
                    "Weight": total_weight
                }
            })
            request_type = "POST"
            response_status, response_data = self.estafeta_provider_create_shipment(request_type, api_url, request_data,
                                                                                    header)
            if response_status and response_data:
                destination_quotes = response_data.get('Quotation')
                existing_records = estafeta_shipping_charge_obj.search([('sale_order_id', '=', order and order.id)])
                existing_records.sudo().unlink()
                if not response_data.get("Quotation"):
                    ValidationError(response_data.content)
                if isinstance(destination_quotes, dict):
                    destination_quotes = [destination_quotes]
                for destination_quote in destination_quotes:
                    if not destination_quote.get('Service'):
                        raise ValidationError(response_data)
                    for quote in destination_quote.get('Service'):
                        estafeta_service_code = quote.get("ServiceCode")
                        estafeta_service_name = quote.get("ServiceName")
                        estafeta_modality = quote.get("Modality")
                        estafeta_total_amount = quote.get("TotalAmount")
                        estafeta_shipping_charge_obj.sudo().create(
                            {
                                'estafeta_service_code': estafeta_service_code,
                                'estafeta_service_name': estafeta_service_name,
                                'estafeta_modality': estafeta_modality,
                                'estafeta_total_amount': estafeta_total_amount,
                                'sale_order_id': order and order.id
                            }
                        )

                estafeta_charge_id = estafeta_shipping_charge_obj.search(
                    [('sale_order_id', '=', order and order.id)], order='estafeta_total_amount', limit=1)
                order.estafeta_shipping_charge_id = estafeta_charge_id and estafeta_charge_id.id

                return {'success': True,
                        'price': estafeta_charge_id and estafeta_charge_id.estafeta_total_amount or 0.0,
                        'error_message': False, 'warning_message': False}

            else:
                return {'success': False, 'price': 0.0,
                        'error_message': response_data, 'warning_message': False}
        except Exception as e:
            return {'success': False, 'price': 0.0,
                    'error_message': e, 'warning_message': False}

    def estafeta_provider_retrive_single_package_info(self, height=False, width=False, length=False, weight=False,
                                                      package_name=False):
        return {

        }

    def estafeta_provider_packages(self, picking):
        package_list = []
        weight_bulk = picking.weight_bulk
        package_ids = picking.package_ids
        for package_id in package_ids:
            height = package_id.package_type_id and package_id.package_type_id.height or 0
            width = package_id.package_type_id and package_id.package_type_id.width or 0
            length = package_id.package_type_id and package_id.package_type_id.packaging_length or 0
            weight = package_id.shipping_weight
            package_name = package_id.name
            package_list.append(
                self.estafeta_provider_retrive_single_package_info(height, width, length, weight, package_name))
        if weight_bulk:
            height = self.estafeta_provider_package_id and self.estafeta_provider_package_id.height or 0
            width = self.estafeta_provider_package_id and self.estafeta_provider_package_id.width or 0
            length = self.estafeta_provider_package_id and self.estafeta_provider_package_id.packaging_length or 0
            weight = weight_bulk
            package_name = picking.name
            package_list.append(
                self.estafeta_provider_retrive_single_package_info(height, width, length, weight, package_name))
        return package_list

    def estafeta_provider_create_shipment(self, request_type, api_url, request_data, header):
        _logger.info("Shipment Request API URL:::: %s" % api_url)
        _logger.info("Shipment Request Data:::: %s" % request_data)
        response_data = requests.request(method=request_type, url=api_url, headers=header, data=request_data)
        if response_data.status_code in [200, 201]:
            response_data = response_data.json()
            _logger.info(">>> Response Data {}".format(response_data))
            return True, response_data
        else:
            return False, response_data.text

    def estafeta_provider_send_shipping(self, picking):
        shipper_address_id = picking.picking_type_id and picking.picking_type_id.warehouse_id and picking.picking_type_id.warehouse_id.partner_id
        recipient_address_id = picking.partner_id
        company_id = self.company_id
        shipper_address_error = self.check_address_details(shipper_address_id, ['zip', 'city', 'country_id', 'street'])
        recipient_address_error = self.check_address_details(recipient_address_id,
                                                             ['zip', 'city', 'country_id', 'street'])
        if shipper_address_error or recipient_address_error or not picking.shipping_weight:
            raise ValidationError("%s %s  %s " % (
                "Shipper Address : %s \n" % (shipper_address_error) if shipper_address_error else "",
                "Recipient Address : %s \n" % (recipient_address_error) if recipient_address_error else "",
                "Shipping weight is missing!" if not picking.shipping_weight else ""
            ))

        sender_zip = shipper_address_id.zip or ""
        sender_city = shipper_address_id.city or ""
        sender_country_code = shipper_address_id.country_id and shipper_address_id.country_id.code or ""
        sender_country_code_numeric = shipper_address_id.country_id and shipper_address_id.country_id.code_numeric or ""
        sender_state_code = shipper_address_id.state_id and shipper_address_id.state_id.code or ""
        sender_street = shipper_address_id.street or ""
        sender_street2 = shipper_address_id.street2 or ""
        sender_phone = shipper_address_id.phone or ""
        sender_email = shipper_address_id.email or ""

        receiver_zip = recipient_address_id.zip or ""
        receiver_city = recipient_address_id.city or ""
        receiver_country_code = recipient_address_id.country_id and recipient_address_id.country_id.code or ""
        receiver_country_code_numeric = recipient_address_id.country_id and recipient_address_id.country_id.code_numeric or ""
        receiver_state_code = recipient_address_id.state_id and recipient_address_id.state_id.code or ""
        receiver_street = recipient_address_id.street or ""
        receiver_street2 = recipient_address_id.street2 or ""
        receiver_phone = recipient_address_id.phone or ""
        receiver_email = recipient_address_id.email or ""

        packages = self.estafeta_provider_packages(picking)
        try:
            header = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'apikey': company_id.estafeta_api_key,
                'Authorization': "Bearer {}".format(company_id.estafeta_api_token)
            }
            api_url = "{0}?outputType={1}&outputGroup={2}&responseMode={3}&printingTemplate={4}".format(
                company_id.estafeta_label_api_url, self.estafeta_output_type, self.estafeta_output_group,
                self.estafeta_response_mode, self.estafeta_printing_template)
            request_data = json.dumps({
                "identification": {
                    "suscriberId": company_id.estafeta_suscriber_id,
                    "customerNumber": company_id.estafeta_customer_number
                },
                "systemInformation": {
                    "id": company_id.estafeta_id,
                    "name": company_id.estafeta_name,
                    "version": "1.10.20"
                },
                "labelDefinition": {
                    "wayBillDocument": {
                        "content": picking.product_id.name,
                        "referenceNumber": picking.name
                    },
                    "itemDescription": {
                        "parcelId": int(self.estafeta_parcel_id),
                        "weight": picking.weight_bulk,
                        "height": self.estafeta_provider_package_id and self.estafeta_provider_package_id.height or 0,
                        "length": self.estafeta_provider_package_id and self.estafeta_provider_package_id.packaging_length or 0,
                        "width": self.estafeta_provider_package_id and self.estafeta_provider_package_id.width or 0
                    },
                    "serviceConfiguration": {
                        "quantityOfLabels": picking.estafeta_no_of_packages,
                        "serviceTypeId": self.estafeta_service_type_id if self.estafeta_default_service_type_id else picking.estafeta_shipping_charge_id.estafeta_service_code,
                        "salesOrganization": company_id.estafeta_sales_organization,
                        "effectiveDate": picking.scheduled_date.strftime("%Y%m%d"),  # "20240216",
                        "originZipCodeForRouting": sender_zip,  # Shipment’s origin zip code,
                        "isInsurance": False,
                        "isReturnDocument": False,
                    },
                    "location": {
                        "origin": {
                            "contact": {
                                "corporateName": shipper_address_id.company_id.name if shipper_address_id.company_id.name else shipper_address_id.name,
                                "contactName": shipper_address_id.name,
                                "cellPhone": sender_phone,
                                "email": sender_email
                            },
                            "address": {
                                "bUsedCode": False,
                                "roadTypeAbbName": "C",  # You can use C. or Calle
                                "roadName": sender_street2,
                                "settlementTypeAbbName": "Col",
                                "settlementName": shipper_address_id.name,
                                "stateAbbName": shipper_address_id.state_id.name,
                                "zipCode": sender_zip,
                                "settlementTypeCode": "001",
                                "countryCode": sender_country_code_numeric,
                                "countryName": shipper_address_id.country_id and shipper_address_id.country_id.l10n_mx_edi_code or "",
                                "externalNum": sender_street
                            }
                        },
                        "destination": {
                            "isDeliveryToPUDO": False,
                            "homeAddress": {
                                "contact": {
                                    "corporateName": recipient_address_id.company_id.name if recipient_address_id.company_id.name else recipient_address_id.name,
                                    "contactName": recipient_address_id.name,
                                    "cellPhone": receiver_phone,
                                    "email": receiver_email
                                },
                                "address": {
                                    "bUsedCode": False,
                                    "roadTypeAbbName": "C",  # You can use C. or Calle
                                    "roadName": receiver_street2,
                                    "settlementTypeAbbName": "Col",
                                    "settlementName": recipient_address_id.name,
                                    "stateAbbName": recipient_address_id.state_id.name,
                                    "zipCode": receiver_zip,
                                    "settlementTypeCode": "001",
                                    "countryCode": receiver_country_code_numeric,
                                    "countryName": recipient_address_id.country_id and recipient_address_id.country_id.l10n_mx_edi_code or "",
                                    "externalNum": receiver_street
                                }
                            }
                        }
                    }
                }
            })
            request_type = "POST"
            response_status, response_data = self.estafeta_provider_create_shipment(request_type, api_url, request_data,
                                                                                    header)
            if response_status and response_data:
                label_data = response_data.get("data")
                label_binary_data = binascii.a2b_base64(str(label_data))
                if not label_data:
                    raise ValidationError(response_data)
                way_bills = []
                tracking_code = []
                trackings = response_data.get("labelPetitionResult") and response_data.get(
                    "labelPetitionResult").get(
                    "elements")
                for tracking in trackings:
                    way_bills.append(tracking.get("wayBill"))
                    tracking_code.append(tracking.get("trackingCode"))
                logmessage = "<b>Tracking Number:</b> %s" % (",".join(tracking_code))
                picking.message_post(body=logmessage,
                                     attachments=[("%s.pdf" % (picking.name), label_binary_data)])
                shipping_data = {'exact_price': 0.0, 'tracking_number': ",".join(way_bills)}
                shipping_data = [shipping_data]
                return shipping_data
            else:
                raise ValidationError(response_data)
        except Exception as e:
            raise ValidationError(e)

    def get_estafeta_charges(self, picking=False):
        shipper_address_id = picking.picking_type_id and picking.picking_type_id.warehouse_id and picking.picking_type_id.warehouse_id.partner_id
        recipient_address_id = picking.partner_id
        shipper_address_error = self.check_address_details(shipper_address_id,
                                                           ['zip', 'city', 'country_id', 'street'])
        recipient_address_error = self.check_address_details(recipient_address_id,
                                                             ['zip', 'city', 'country_id', 'street'])
        if shipper_address_error or recipient_address_error or not picking.shipping_weight:
            raise ValidationError("%s %s  %s " % (
                "Shipper Address : %s \n" % (shipper_address_error) if shipper_address_error else "",
                "Recipient Address : %s \n" % (recipient_address_error) if recipient_address_error else "",
                "Shipping weight is missing!" if not picking.shipping_weight else ""
            ))
        estafeta_shipping_charge_obj = self.env['estafeta.shipping.charge']
        company_id = self.company_id
        sender_zip = shipper_address_id.zip or ""
        receiver_zip = recipient_address_id.zip or ""

        try:
            header = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'apikey': company_id.estafeta_api_key,
                'Authorization': "Bearer {}".format(company_id.estafeta_api_token)
            }
            api_url = company_id.estafeta_rate_api_url
            request_data = json.dumps({
                "Origin": sender_zip,
                "Destination": [
                    receiver_zip
                ],
                "PackagingType": self.estafeta_provider_package_id.name,
                "Dimensions": {
                    "Length": self.estafeta_provider_package_id.packaging_length,
                    "Width": self.estafeta_provider_package_id.width,
                    "Height": self.estafeta_provider_package_id.height,
                    "Weight": picking.weight_bulk

                }
            })
            request_type = "POST"
            response_status, response_data = self.estafeta_provider_create_shipment(request_type, api_url,
                                                                                    request_data,
                                                                                    header)
            if response_status and response_data:
                destination_quotes = response_data.get('Quotation')
                existing_records = estafeta_shipping_charge_obj.search([('picking_id', '=', picking.id)])
                existing_records.sudo().unlink()
                if not response_data.get("Quotation"):
                    ValidationError(response_data.content)
                if isinstance(destination_quotes, dict):
                    destination_quotes = [destination_quotes]
                for destination_quote in destination_quotes:
                    if not destination_quote.get('Service'):
                        raise ValidationError(response_data)
                    for quote in destination_quote.get('Service'):
                        estafeta_service_code = quote.get("ServiceCode")
                        estafeta_service_name = quote.get("ServiceName")
                        estafeta_modality = quote.get("Modality")
                        estafeta_total_amount = quote.get("TotalAmount")
                        estafeta_shipping_charge_obj.sudo().create(
                            {
                                'estafeta_service_code': estafeta_service_code,
                                'estafeta_service_name': estafeta_service_name,
                                'estafeta_modality': estafeta_modality,
                                'estafeta_total_amount': estafeta_total_amount * picking.estafeta_no_of_packages,
                                'picking_id': picking.id
                            }
                        )
                estafeta_charge_id = estafeta_shipping_charge_obj.search(
                    [('picking_id', '=', picking.id)], order='estafeta_total_amount', limit=1)
                picking.estafeta_shipping_charge_id = estafeta_charge_id and estafeta_charge_id.id

                return {'success': True,
                        'price': estafeta_charge_id and estafeta_charge_id.estafeta_total_amount or 0.0,
                        'error_message': False, 'warning_message': False}
            else:
                return {'success': False, 'price': 0.0,
                        'error_message': response_data, 'warning_message': False}

        except Exception as e:
            return {'success': False, 'price': 0.0,
                    'error_message': e, 'warning_message': False}

    def estafeta_provider_cancel_shipment(self, picking):
        raise ValidationError("")

    def estafeta_provider_get_tracking_status(self, picking):
        company_id = self.company_id
        header = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            'apikey': company_id.estafeta_api_key,
            'Authorization': "Bearer {}".format(company_id.estafeta_api_token)
        }
        api_url = company_id.estafeta_tracking_api_url
        request_data = json.dumps({
            "inputType": 0,
            "itemReference": {
                "clientNumber": "string",
                "referenceCode": [
                    "string"
                ]
            },
            "itemsSearch": [
                picking.carrier_tracking_ref
            ],
            "searchType": 0
        })
        request_type = "POST"
        response_status, response_data = self.estafeta_provider_create_shipment(request_type, api_url, request_data,
                                                                                header)
        if response_status and response_data:
            items = response_data.get('items')
            for item in items:
                if not item.get('statusCurrent'):
                    raise ValidationError(item.get('error').get('description'))
            for item in items:
                picking.estafeta_code = item.get('statusCurrent') and item.get('statusCurrent').get('code')
                picking.estafeta_english_name = item.get('statusCurrent') and item.get('statusCurrent').get(
                    'englishName')
                picking.estafeta_local_date_time = item.get('statusCurrent') and item.get('statusCurrent').get(
                    'localDateTime')
                picking.estafeta_spanish_name = item.get('statusCurrent') and item.get('statusCurrent').get(
                    'spanishName')
                picking.estafeta_warehouse_code = item.get('statusCurrent') and item.get('statusCurrent').get(
                    'warehouseCode')
                picking.estafeta_warehouse_name = item.get('statusCurrent') and item.get('statusCurrent').get(
                    'warehouseName')
        else:
            raise ValidationError(response_data.text)

    def estafeta_provider_get_tracking_link(self, picking):
        return "tracking_url"
