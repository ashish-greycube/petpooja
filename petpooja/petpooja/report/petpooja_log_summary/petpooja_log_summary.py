# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from itertools import groupby
from frappe.utils import flt, date_diff, getdate, cstr, cint
import datetime

def execute(filters=None):
	columns, data = [], []

	columns = get_columns(filters)
	data = get_data(filters, columns)
	if not data:
		# msgprint(_("No records found"))
		return columns, data
		
	return columns, data

def get_columns(filters):
	columns = [
		{
			"fieldname": "branch",
			"fieldtype": "Link",
			"label": _("Branch"),
			"options": "Cost Center",
			"width": 200
		},
		{
			"fieldname": "invoice_status",
			"fieldtype": "Data",
			"label": _("Invoice Status"),
			"width": 200
		},
	]

	return columns

def get_conditions(filters):
    conditions = []

    if filters.get("from_date") and filters.get("to_date"):
        if filters.get("to_date") >= filters.get("from_date"):
            conditions.append("DATE(ppl.business_date) BETWEEN %(from_date)s AND %(to_date)s")
        else:
            frappe.throw(_("To Date should be greater than From Date"))

    if filters.get("branch"):
        conditions.append("ppl.branch = %(branch)s")
    
    return " WHERE " + " AND ".join(conditions) if conditions else ""

def get_data(filters, columns):
    conditions = get_conditions(filters)
    
    data = frappe.db.sql(
        f"""
        SELECT
            ppl.branch AS branch, 
            ppl.business_date AS business_date, 
            ppl.invoice_status AS invoice_status, 
            1 AS count_log
        FROM `tabPet Pooja Log` AS ppl
        {conditions}
        """,
        filters,
        as_dict=1
    )

    return make_report(data, filters, columns)


def make_report(data, filters, columns):

	result = []

	from_date, to_date = filters.get("from_date"), filters.get("to_date")
	numdays = date_diff(to_date, from_date)

	dates = [
		(getdate(to_date) - datetime.timedelta(days=x)).strftime("%Y-%m-%d")
		for x in range(numdays)
	]

	dates.append(filters.get("from_date"))

	for dt in dates:
		columns.append(
				{
					"fieldname": dt,
					"label": dt,
					"fieldtype": "Data",
					"width": 150,
				}
			)
		
	columns.append({
		"fieldname": "total_invoice",
		"fieldtype": "Int",
		"label": _("Invoice Total"),
		"width": 110,
	}),

	grouping_key = lambda o: (o["branch"], o["invoice_status"])
	for (branch, invoice_status), rows in groupby(
		sorted(data, key=grouping_key), key=grouping_key
	):
		_rows = list(rows)

		row = {
			"branch": branch,
			"invoice_status": invoice_status,
		}

		total_invoice = 0
		for dt in dates:
			row[dt] = sum(
				flt(r["count_log"]) for r in _rows if cstr(r["business_date"]).startswith(dt)
			)
			total_invoice = total_invoice + row[dt]
			row["total_invoice"] = total_invoice

		result.append(row)
			
	return result