"""Reject malformed mobile writes before they can create stock demand or stock entries."""
import unittest
from unittest.mock import patch

import frappe

from mobile_operations import api


class TestMobileWriteValidation(unittest.TestCase):
    def test_invalid_rows_and_json_are_business_errors(self):
        for data in ('{', [], {'items': {}}, {'items': ['bad']}, {'items': [None]},
                     {'items': [{'item_code': 123}]}, {'company': [], 'items': [{}]}):
            with self.subTest(data=data), self.assertRaises(frappe.ValidationError):
                api._mobile_create_data(data, 'Invalid request')

    def test_non_positive_and_non_finite_quantities_are_rejected(self):
        for field in ('qty', 'conversion_factor'):
            for value in (-1, 0, 'NaN', 'Infinity', '-Infinity', 'bad', True, [], {}):
                row = {'qty': 2, 'conversion_factor': 1, field: value}
                with self.subTest(field=field, value=value), self.assertRaises(frappe.ValidationError):
                    api._mobile_item_quantities(row, 1)
        with self.assertRaises(frappe.ValidationError):
            api._mobile_item_quantities({'qty': 1e308, 'conversion_factor': 1e308}, 1)

    def test_missing_factor_remains_compatible_and_decimal_factor_is_supported(self):
        self.assertEqual(api._mobile_item_quantities({'qty': '2.5'}, 1), [2.5, 1])
        self.assertEqual(api._mobile_item_quantities({'qty': 2, 'conversion_factor': '0.5'}, 1), [2, .5])

    def test_both_create_endpoints_apply_input_validation(self):
        for create in (api.create_mobile_material_request, api.create_mobile_stock_entry):
            with self.subTest(create=create.__name__), patch.object(frappe, 'has_permission', return_value=True):
                with self.assertRaises(frappe.ValidationError):
                    create({'items': ['bad']})

    def test_all_mobile_write_endpoints_require_post(self):
        for method in (api.create_mobile_material_request, api.submit_mobile_material_request,
                       api.issue_and_push_mobile_material_request, api.create_mobile_material_request_stock_entry,
                       api.create_mobile_stock_entry, api.submit_mobile_stock_entry, api.push_mobile_stock_entry_to_dlm):
            with self.subTest(method=method.__name__):
                self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ['POST'])
