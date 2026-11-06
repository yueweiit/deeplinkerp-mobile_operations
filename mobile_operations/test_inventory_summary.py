"""The mobile reminders count visible documents without loading every document."""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from mobile_operations import api


def _counts(rows):
    return {row["key"]: row["count"] for row in rows}


class TestMobileInventorySummary(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(frappe.db.rollback)
        self.token = frappe.generate_hash(length=10).upper()
        self.sequence = 0

    def insert(self, doctype, **values):
        self.sequence += 1
        name = values.pop("name", f"MOBILE-SUMMARY-{self.token}-{self.sequence}")
        frappe.get_doc({"doctype": doctype, "name": name, **values}).db_insert()
        return name

    def test_material_request_bucket_counts(self):
        before = _counts(api._get_mobile_material_request_summary())
        self.insert("Material Request", material_request_type="Material Issue", docstatus=0, status="Draft")
        self.insert("Material Request", material_request_type="Material Issue", docstatus=1, status="Pending")
        self.insert(
            "Material Request", material_request_type="Material Issue", docstatus=1,
            status="Partially Ordered", per_ordered=25,
        )
        self.insert(
            "Material Request", material_request_type="Material Issue", docstatus=2,
            status="Stopped", transfer_status="In Transit",
        )
        self.insert(
            "Material Request", material_request_type="Material Issue", docstatus=1,
            status="Ordered", per_ordered=100,
        )
        self.insert(
            "Material Request", material_request_type="Material Issue", docstatus=1,
            status="stopped",
        )
        self.insert(
            "Material Request", material_request_type="Material Issue", docstatus=1,
            transfer_status="in transit",
        )
        self.insert(
            "Material Request", material_request_type="material issue", docstatus=1,
            status="Pending",
        )
        after = _counts(api._get_mobile_material_request_summary())
        self.assertEqual(
            {key: after[key] - before[key] for key in before},
            {"in_progress": 6, "to_issue": 3, "partial": 1, "transit": 1, "exception": 1},
        )

    def test_mes_pending_count_filter_and_detail_use_the_same_business_conditions(self):
        if not all(
            frappe.db.has_column(doctype, field)
            for doctype, field in (
                ("Stock Entry", "custom_mes_status"),
                ("Material Request", "custom_request_source"),
                ("Company", "custom_enable_mes_integration"),
            )
        ):
            self.skipTest("MES custom fields are not migrated on this site")

        before = _counts(api._get_mobile_stock_entry_summary())
        enabled_company = self.insert(
            "Company", company_name=f"Mobile Summary {self.token}",
            abbr=self.token[:5], default_currency="USD", custom_enable_mes_integration=1,
        )
        disabled_company = self.insert(
            "Company", company_name=f"Mobile Disabled {self.token}",
            abbr=self.token[5:], default_currency="USD", custom_enable_mes_integration=0,
        )
        mes_request = self.insert(
            "Material Request", name=f"MAT-MR-MES-{self.token}",
            material_request_type="Material Issue", docstatus=1,
        )
        explicit_source = self.insert(
            "Material Request", material_request_type="Material Issue",
            custom_request_source=" MES ", docstatus=1,
        )
        manual_request = self.insert(
            "Material Request", material_request_type="Material Issue",
            custom_request_source="手动创建", docstatus=1,
        )
        lowercase_source = self.insert(
            "Material Request", material_request_type="Material Issue",
            custom_request_source="mes", docstatus=1,
        )
        manual_prefix = self.insert(
            "Material Request", name=f"MAT-MR-MES-MANUAL-{self.token}",
            material_request_type="Material Issue", custom_request_source="手动创建", docstatus=1,
        )
        lowercase_prefix = self.insert(
            "Material Request", name=f"mat-mr-mes-lower-{self.token}",
            material_request_type="Material Issue", docstatus=1,
        )

        def stock(docstatus=1, stock_entry_type="Material Issue", company=None, mes_status=""):
            return self.insert(
                "Stock Entry", docstatus=docstatus, stock_entry_type=stock_entry_type,
                company=company or enabled_company, custom_mes_status=mes_status,
            )

        def link(parent, request, index=1, qty=1):
            self.insert(
                "Stock Entry Detail", parent=parent, parenttype="Stock Entry",
                parentfield="items", idx=index, material_request=request, qty=qty,
            )

        draft = stock(docstatus=0)
        pending = stock()
        explicit_pending = stock()
        lowercase_status = stock(mes_status="pushed")
        pushed = stock(mes_status="Pushed")
        manual = stock()
        wrong_type = stock(stock_entry_type="Material Receipt")
        wrong_case_type = stock(stock_entry_type="material issue")
        disabled = stock(company=disabled_company)
        multiple_requests = stock()
        zero_quantity = stock()
        wrong_prefix = stock()
        explicit_manual = stock()
        lowercase_source_entry = stock()
        for parent, request in (
            (draft, mes_request), (pending, mes_request), (explicit_pending, explicit_source),
            (lowercase_status, mes_request), (pushed, mes_request), (manual, manual_request),
            (wrong_type, mes_request), (wrong_case_type, mes_request), (disabled, mes_request),
            (multiple_requests, mes_request), (wrong_prefix, lowercase_prefix),
            (explicit_manual, manual_prefix), (lowercase_source_entry, lowercase_source),
        ):
            link(parent, request)
        link(pending, mes_request, index=2)
        link(multiple_requests, manual_request, index=2)
        link(zero_quantity, mes_request, qty=0)

        after = _counts(api._get_mobile_stock_entry_summary())
        self.assertEqual(
            {key: after[key] - before[key] for key in before},
            {"all": 14, "draft": 1, "submitted": 13, "mes_pending": 3},
        )
        api._clear_mobile_inventory_summary_cache()
        self.addCleanup(api._clear_mobile_inventory_summary_cache)
        page = api.get_mobile_stock_entry_dashboard(search=self.token, status="mes_pending")
        self.assertEqual(page["total"], 3)
        self.assertEqual(
            {row["name"] for row in page["entries"]},
            {pending, explicit_pending, lowercase_status},
        )
        self.assertTrue(api.get_mobile_stock_entry_detail(pending)["can_push_to_dlm"])
        self.assertFalse(api.get_mobile_stock_entry_detail(multiple_requests)["can_push_to_dlm"])
        manual_detail = api.get_mobile_stock_entry_detail(explicit_manual)
        self.assertEqual(manual_detail["request_source"], "Manual")
        self.assertFalse(manual_detail["can_push_to_dlm"])
        self.assertEqual(
            api._get_request_source({"name": manual_prefix, "custom_request_source": "手动创建"}),
            "Manual",
        )

    def test_guest_has_no_summary(self):
        with set_user("Guest"):
            self.assertEqual(
                api._get_mobile_inventory_summary_data(),
                {"material_request": [], "stock_entry": []},
            )
            api._clear_mobile_inventory_summary_cache()
