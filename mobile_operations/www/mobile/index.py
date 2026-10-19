from pathlib import Path
from urllib.parse import urlencode

import frappe
from frappe.translate import get_all_translations, get_translations_from_apps

no_cache = 1


def get_context(context):
	"""Render the mobile shell for logged-in system users only."""
	if frappe.session.user == "Guest":
		redirect_to = frappe.local.request.path or "/mobile"
		if not redirect_to.startswith("/mobile"):
			redirect_to = "/mobile"
		frappe.redirect(f"/mobile/login?{urlencode({'redirect-to': redirect_to})}")

	context.mobile_bom_asset_version = max(
		Path(frappe.get_app_path("mobile_operations", "public", folder, filename)).stat().st_mtime_ns
		for folder, filename in (("js", "mobile_bom.js"), ("css", "mobile_bom.css"))
	)
	context.mobile_item_asset_version = max(
		Path(frappe.get_app_path("mobile_operations", "public", folder, filename)).stat().st_mtime_ns
		for folder, filename in (("js", "mobile_items.js"), ("css", "mobile_items.css"))
	)
	# Website boot omits Desk's dictionary; load this App's keys before its views.
	translations = get_translations_from_apps(frappe.local.lang, apps=["mobile_operations"])
	merged = get_all_translations(frappe.local.lang)
	context.mobile_translations = {key: merged.get(key, value) for key, value in translations.items()}
	return context
