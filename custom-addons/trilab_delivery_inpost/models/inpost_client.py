import base64
import enum
import logging
import re
from json import JSONDecodeError

import requests
from werkzeug.urls import url_join


_logger = logging.getLogger(__name__)


class InpostError(Exception):

    def __init__(self, error, data=None, *args: object) -> None:
        if isinstance(data, (list, tuple)) or data is None:
            self.data = data
        else:
            self.data = (data,)

        super().__init__(error, *args)

    def __str__(self) -> str:
        return super(InpostError, self).__str__() + '\n' + '\n'.join(self.data or [])


class SendingMethod(enum.Enum):
    PARCEL_LOCKER = 'parcel_locker'
    POK = 'pok'
    POP = 'pop'
    COURIER_POK = 'courier_pok'
    BRANCH = 'branch'
    DISPATCH_ORDER = 'dispatch_order'


class Client:
    """Implementation of InPost API"""

    PROD_URL = 'https://api-shipx-pl.easypack24.net'
    TEST_URL = 'https://sandbox-api-shipx-pl.easypack24.net'

    def __init__(self, carrier_id=None, prod=True):
        if carrier_id:
            self.api_key = carrier_id.inpost_token
            self.debug_logger = carrier_id.log_xml
            self.organization = carrier_id.inpost_organization
            self.prod = carrier_id.prod_environment
        else:
            self.api_key = None
            self.debug_logger = lambda xml_string, func: None
            self.organization = None
            self.prod = prod

    def _make_api_request(
        self, endpoint, method='get', data=None, request_id=None, headers=None, raw_response=False, auth=True
    ):
        """make an api call, return response"""

        url = url_join(Client.PROD_URL if self.prod else Client.TEST_URL, endpoint)

        _headers = {
            'Content-Type': 'application/json',
            'X-User-Agent': 'Odoo - Trilab InPost',
            'X-User-Agent-Version': '2.0',
        }

        if auth:
            if not self.api_key:
                message = 'A Token is required in order to configure InPost.'
                _logger.error(message)
                raise InpostError(message)

            _headers['Authorization'] = f'Bearer {self.api_key}'

            if url.find(':organization_id') >= 0:
                if not self.organization:
                    message = 'Organization is required in order to configure InPost.'
                    _logger.error(message)
                    raise InpostError(message)

                url = url.replace(':organization_id', self.organization)

        if request_id:
            _headers['X-Request-ID'] = request_id

        if headers:
            _headers.update(headers)

        if data is None:
            data = {}

        try:
            message = f'url: {url}\nmethod: {method}\ndata: {data}'
            _logger.debug(message)
            self.debug_logger(message, f'inpost_request_{endpoint}')

            if method == 'get':
                response = requests.get(url, json=data, headers=_headers)
            elif method == 'post':
                response = requests.post(url, json=data, headers=_headers)
            elif method == 'delete':
                response = requests.delete(url, json=data, headers=_headers)
            else:
                raise InpostError(f'Invalid InPost API method "{method}".')

            if raw_response:
                if response.ok:
                    return response
                else:
                    raise InpostError(f'Got error: [{response.status_code}] {response.text}')
            else:
                self.debug_logger(response.text, 'inpost_response_{endpoint}')

                try:
                    data = response.json()
                except JSONDecodeError:
                    data = {}

                # check for any error in response
                if 'message' in data:
                    message = data['message']
                else:
                    message = 'InPost returned an error'

                if 'error' in data:
                    error_data = []

                    def _flatten_data(d, level=None):
                        if isinstance(d, (list, tuple)):
                            resp = []
                            for v in d:
                                resp.extend(_flatten_data(v, level))
                            return resp
                        elif isinstance(d, dict):
                            resp = []
                            for k, v in d.items():
                                resp.extend(_flatten_data(v, f'{level or ""}{" -> " if level else ""}{k}'))
                            return resp
                        else:
                            if level:
                                level = f'{level}: '
                            else:
                                level = ''
                            return [f'{level}{d}']

                    if 'details' in data:
                        error_data = _flatten_data(data.get('details', {}))

                    raise InpostError(message, data=error_data)

                elif not response.ok:
                    message += response.text
                    raise InpostError(message)

                return data

        except InpostError:
            raise

        except Exception as e:
            _logger.exception('Got exception during InPost API call')
            raise InpostError(e)

    def send_shipping(self, order_payload):
        _logger.debug(f'send_shipping: {order_payload}')
        return self._make_api_request('/v1/organizations/:organization_id/shipments', 'post', data=order_payload)

    # noinspection PyMethodMayBeStatic
    def get_tracking_link(self, carrier_tracking_ref):
        return f'https://inpost.pl/sledzenie-przesylek?number={carrier_tracking_ref}'

    def get_shipping_info(self, inpost_shipment_id):
        return self._make_api_request(f'/v1/shipments/{inpost_shipment_id}')

    def cancel_shipment(self, inpost_shipment_id):
        return self._make_api_request(f'/v1/shipments/{inpost_shipment_id}', method='delete')

    def get_labels(self, shipments, label_format='pdf', label_type='normal'):
        response = self._make_api_request(
            '/v1/organizations/:organization_id/shipments/labels',
            method='post',
            data={'format': label_format, 'type': label_type, 'shipment_ids': shipments},
            raw_response=True,
        )

        filename = re.findall(r'filename=(.+)', response.headers.get('content-disposition', ''))

        if isinstance(filename, (list, tuple)):
            filename = filename[0].strip('"').strip("'")

        if not filename:
            ct = response.headers.get('content-type')
            if ct == 'application/pdf':
                filename = 'label.pdf'
            elif ct == 'application/zip':
                filename = 'label.zip'
            else:
                filename = f'label.{label_format}'

        return {'file_name': filename, 'data': base64.b64encode(response.content)}

    def get_return_labels(self, shipments, label_format='pdf'):
        response = self._make_api_request(
            '/v1/organizations/:organization_id/shipments/return_labels',
            data={'format': label_format, 'shipment_ids': shipments},
            raw_response=True,
        )

        filename = re.findall(r'filename=(.+)', response.headers.get('content-disposition', ''))

        if isinstance(filename, (list, tuple)):
            filename = filename[0].strip('"').strip("'")

        if not filename:
            ct = response.headers.get('content-type')
            if ct == 'application/pdf':
                filename = 'label.pdf'
            elif ct == 'application/zip':
                filename = 'label.zip'
            else:
                filename = f'label.{label_format}'

        return {'file_name': filename, 'data': base64.b64encode(response.content)}

    def dispatch_orders(self, data):
        return self._make_api_request('/v1/organizations/:organization_id/dispatch_orders', method='post', data=data)

    def cancel_order(self, order_id):
        return self._make_api_request(f'/v1/dispatch_orders/{order_id}', method='delete')

    def printout_order(self, order_id: str):
        return self._make_api_request(
            '/v1/organizations/:organization_id/dispatch_orders/printouts',
            data={'format': 'Pdf', 'dispatch_order_id': order_id},
            raw_response=True,
        ).content

    def printout_orders(self, shipments: list):
        return self._make_api_request(
            '/v1/organizations/:organization_id/dispatch_orders/printouts',
            data={'format': 'Pdf', 'shipment_ids': shipments},
            raw_response=True,
        ).content

    def get_organizations(self):
        organizations = []

        _continue = True
        _page = 1

        while _continue:
            response = self._make_api_request(f'/v1/organizations/?page={_page}')

            for org in response['items']:
                organizations.append((org.get('id'), org.get('name')))

            if _page * response['per_page'] >= response['count']:
                _continue = False
            else:
                _page += 1

        return organizations

    def get_points(self, page=1, page_size=50):
        return self._make_api_request(f'/v1/points/?page={page}&per_page={page_size}', auth=False)

    def get_point(self, name):
        return self._make_api_request(f'/v1/points/{name}', auth=False)
