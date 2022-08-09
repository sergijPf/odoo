# -*- coding: utf-8 -*-

import json
import socket
import logging
import requests
from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def req(backend, path, method='GET', data=None, params=None):
    """
    Make API request based on API method
    """
    location_url = backend._append_rest_suffix_to_url(backend.magento_url)

    try:
        _logger.info(f'Data pass to Magento : {data}')

        api_url = f'{location_url}{path}'
        kwargs = {
            'method': method,
            'url': api_url,
            'headers': {
                'User-Agent': 'My User Agent 1.0',
                'Authorization': f'Bearer {backend.access_token}'
            },
            'params': params,
            'json': data
        }

        if backend.magento_verify_ssl:
            kwargs.update({'verify': True})

        resp = requests.request(**kwargs)

        content = resp.json()
        _logger.info(f'API URL : {api_url}')
        _logger.info(f'Response Status code : {resp.status_code}')

        if resp.status_code == 401:
            raise UserError(_('Given Credentials is incorrect, please provide correct Credentials.'))
        if resp.status_code == 500:
            return content
        if not resp.ok:
            if resp.headers.get('content-type') != 'application/json':
                raise UserError(_(f'Content-type is not JSON \n {resp.status_code} : {resp.reason} \n {path} \n {resp.content}'))

            response = resp.json()
            response.update({'status_code': resp.status_code})

            raise UserError(str(response))

    except (socket.gaierror, socket.error, socket.timeout) as err:
        raise UserError(_(f'A network error caused the failure of the job: {str(err)}'))
    except Exception as err:
        raise UserError(err)
    return content

def create_filter(field, value, condition_type='eq'):
    """
    Create dictionary for filter
    :param field: Field to be filtered
    :param value: Value to be filtered
    :param condition_type: condition type to be filtered
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
                    filters_list, filtersgroup_list, tempfilters = generate_filter_groups(
                        operator, values, k, filters_list, tempfilters, filtersgroup_list)
            else:
                filters_list.append(create_filter(k, val))
                tempfilters["filters"] = filters_list
                filtersgroup_list.append(tempfilters)
        searchcriteria["searchCriteria"]['filterGroups'] = filtersgroup_list
    return searchcriteria


def generate_filter_groups(operator, values, k, filters_list, tempfilters, filtersgroup_list):
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
    return filters_list, filtersgroup_list, tempfilters
