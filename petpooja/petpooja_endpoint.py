import hmac
import json
from http import HTTPStatus
from typing import Optional, Tuple

import frappe
from frappe import _
from werkzeug.wrappers import Response
from frappe.utils import getdate, cstr, add_to_date, get_time


def _token_is_valid(token):
	"""Constant-time check of the shared secret PetPooja sends in the payload.

	PetPooja does not compute an HMAC signature over the request body - it just
	echoes the shared secret back as a plain `token` field - so there is nothing
	to sign/verify beyond this. hmac.compare_digest still protects the comparison
	itself from timing attacks.
	"""
	if not token or not isinstance(token, str):
		return False
	petpooja_settings = frappe.get_cached_doc('Petpooja Settings', 'Petpooja Settings')
	secret = (petpooja_settings.secret or "").encode("utf8")
	return hmac.compare_digest(secret, token.encode("utf8"))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def order_created(*args, **kwargs):
	if not (frappe.request and frappe.request.data):
		return Response(response=_("Event not supported"), status=HTTPStatus.BAD_REQUEST)

	try:
		request_data = json.loads(frappe.request.data)
	except ValueError:
		return Response(response=_("Invalid JSON body"), status=HTTPStatus.BAD_REQUEST)

	if not isinstance(request_data, dict):
		return Response(response=_("Invalid JSON body"), status=HTTPStatus.BAD_REQUEST)

	if not _token_is_valid(request_data.pop('token', None)):
		return Response(response=_("Invalid or missing token"), status=HTTPStatus.UNAUTHORIZED)

	# ERPNext performs some standalone permission checks (e.g. Account read access
	# in get_party_account) that are not covered by ignore_permissions=True on the
	# Sales Invoice, so the enqueued job still needs to run as a real user. Only do
	# this after the token has been verified, and only for this endpoint - the old
	# approach ran this impersonation via a global auth_hook on every API request.
	petpooja_settings = frappe.get_cached_doc('Petpooja Settings', 'Petpooja Settings')
	frappe.set_user(petpooja_settings.creation_user)

	frappe.enqueue(create_petpooja_log, queue="long", job_name="petpooja_log", request_data=request_data)
	return Response(status=HTTPStatus.OK)


def create_petpooja_log(request_data):
	try:
		if request_data and not isinstance(request_data, str):
			request_data = json.dumps(request_data, sort_keys=True, indent=4)
		log = frappe.new_doc('Pet Pooja Log')
		log.data = request_data
		data=frappe.parse_json(request_data)
		log.rest_id=data.get('properties').get('Restaurant').get('restID')
		branch=frappe.db.get_value('Cost Center', {'custom_petpooja_restaurant_id': log.rest_id}, ['name'])
		if branch:
			log.branch=branch
		log.order_id=data.get('properties').get('Order').get('orderID')
		log.pos_created_on=data.get('properties').get('Order').get('created_on')
		log.business_date=  add_to_date(getdate(log.pos_created_on), days=-1) if get_time('04:30:01') > get_time(log.pos_created_on) else getdate(log.pos_created_on)
		log.log_status = "Success"
		log.insert(ignore_permissions=True)
		# frappe.db.commit()
	except Exception as e:
			frappe.log_error(_("PetPooja log creation error"),str(e)+"\n"+"Raw request data: "+"\n"+request_data)
