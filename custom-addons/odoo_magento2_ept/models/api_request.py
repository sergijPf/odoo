# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Requrests API to magento.
"""
import json
import socket
import logging
import requests
from odoo import _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)


def req(backend, path, method='GET', data=None, params=None):
    """
    This method use for base on API request it call API method.
    """
    location_url = backend._check_location_url(backend.magento_url)
    api_url = '%s%s' % (location_url, path)
    headers = {
        'Accept': '*/*', 'Content-Type': 'application/json',
        'User-Agent': 'My User Agent 1.0', 'Authorization': 'Bearer %s' % backend.access_token}
    try:
        _logger.info('Data pass to Magento : %s', data)
        if method == 'GET':
            resp = requests.get(api_url, headers=headers, verify=False, params=params)
        elif method == 'POST':
            resp = requests.post(api_url, headers=headers, data=json.dumps(data), verify=False,
                                 params=params)
        elif method == 'DELETE':
            resp = requests.delete(api_url, headers=headers, verify=False, params=params)
        elif method == 'PUT':
            resp = requests.put(api_url, headers=headers, data=json.dumps(data), verify=False,
                                params=params)
        else:
            resp = requests.get(api_url, headers=headers, verify=False, params=params)
        content = resp.json()
        _logger.info('API URL : %s', api_url)
        _logger.info('Response Status code : %s', resp.status_code)
        if resp.status_code == 401:
            raise UserError(_('Given Credentials is incorrect, please provide correct Credentials.'))
        if resp.status_code == 500:
            return content
        if not resp.ok:
            if resp.headers.get('content-type').split(';')[0] == 'text/html':
                raise UserError(_('Content-type is not JSON \n %s : %s \n %s \n %s', (
                    resp.status_code, resp.reason, path, resp.content)))
            response = resp.json()
            response.update({'status_code':resp.status_code})
            raise UserError(str(response), response=response)
    except (socket.gaierror, socket.error, socket.timeout) as err:
        raise UserError(_('A network error caused the failure of the job: %s', err))
    except Exception as err:
        raise UserError(_("Request is not Satisfied. "
                          "Please check access token is correct or Apichange extention is installed in Magento store."))
    return content


def create_filter(field, value, condition_type='eq'):
    """
    Create dictionary for filter.
    :param field: Field to be filter
    :param value: Value to be filter
    :param condition_type: condition type to be filter
    :return: Dictionary for filter
    """
    filter_dict = {'field': field}
    if isinstance(value, str) and condition_type == "in":
        filter_dict['condition_type'] = 'like'
    elif isinstance(value, str) and condition_type == "nin":
        filter_dict['condition_type'] = 'nlike'
    else:
        filter_dict['condition_type'] = condition_type
    filter_dict['value'] = value

    return filter_dict


def create_search_criteria(filters):
    """
        Create Search Criteria
        if filters is {'updated_at': {'to': '2016-12-22 10:42:44', 'from': '2016-12-16 10:42:18'}}
        then searchCriteria = {'searchCriteria': {'filterGroups': [{'filters': [{'field':
        'updated_at', 'condition_type': 'to', 'value': '2016-12-22 10:42:44'}]},{'filters':
        [{'field': 'updated_at', 'condition_type': 'from', 'value': '2016-12-16 10:42:18'}]}]}}
    """
    searchcriteria = {}
    if filters is None:
        filters = {}

    if not filters:
        searchcriteria = {
            'searchCriteria': {
                'filterGroups': [{
                    'filters': [{
                        'field': 'id', 'value': -1, 'condition_type': 'gt'
                    }]
                }]
            }
        }
    else:
        searchcriteria.setdefault('searchCriteria', {})
        filtersgroup_list = []
        for k, val in filters.items():
            tempfilters = {}
            filters_list = []
            if isinstance(val, dict):
                for operator, values in val.items():
                    if isinstance(values, list):
                        if operator == "in":
                            for value in values:
                                filters_list.append(create_filter(k, value, operator))
                            tempfilters["filters"] = filters_list
                            filtersgroup_list.append(tempfilters)
                        elif operator == "nin":
                            for value in values:
                                filters_list.append(create_filter(k, value, operator))
                                tempfilters["filters"] = filters_list
                                filtersgroup_list.append(tempfilters)
                    else:
                        filters_list.append(create_filter(k, values, operator))
                        tempfilters["filters"] = filters_list
                        filtersgroup_list.append(tempfilters)
                        filters_list = []
                        tempfilters = {}
            else:
                filters_list.append(create_filter(k, val))
                tempfilters["filters"] = filters_list
                filtersgroup_list.append(tempfilters)
        searchcriteria["searchCriteria"]['filterGroups'] = filtersgroup_list
    return searchcriteria
