# Copyright (c) 2009 Patrick Altman http://paltman.com
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

"""
Provides connectivity to FogBugz
"""
import urllib
import xml.sax
import logging
import time
import BaseHTTPServer
msg_dict = BaseHTTPServer.BaseHTTPRequestHandler.responses

from google.appengine.api import urlfetch
from pyfogbugz import UserAgent, XmlHandler
from pyfogbugz.exceptions import FogBugzClientError, FogBugzServerError
from pyfogbugz.filter import FilterList
from pyfogbugz.case import CaseList
from pyfogbugz.status import StatusList

AVAILABLE_CASE_COLUMNS = ('ixBug', 'ixBugParent', 'ixBugChildren', 'tags', 'fOpen', 'sTitle', 'sLatestTextSummary', 'ixBugEventLatestText', 'ixProject', 'sProject', 'ixArea', 'sArea', 'ixGroup', 'ixPersonAssignedTo', 'sPersonAssignedTo', 'sEmailAssignedTo', 'ixPersonOpenedBy', 'ixPersonResolvedBy', 'ixPersonClosedBy', 'ixPersonLastEditedBy', 'ixStatus', 'sStatus', 'ixPriority', 'sPriority', 'ixFixFor', 'sFixFor', 'dtFixFor', 'sVersion', 'sComputer', 'hrsOrigEst', 'hrsCurrEst', 'hrsElapsed', 'c', 'sCustomerEmail', 'ixMailbox', 'ixCategory', 'sCategory', 'dtOpened', 'dtResolved', 'dtClosed', 'ixBugEventLatest', 'dtLastUpdated', 'fReplied', 'fForwarded', 'sTicket', 'ixDiscussTopic', 'dtDue', 'sReleaseNotes', 'ixBugEventLastView', 'dtLastView', 'ixRelatedBugs', 'sScoutDescription', 'sScoutMessage', 'fScoutStopReporting', 'fSubscribed', 'events')

class Connection(object):
	def __init__(self, url, offline):
		self.url = url
		self.offline = offline

	def make_request(self, path, data=None):
		response = None
		headers = {'User-Agent':UserAgent}

		if data:
			data = urllib.urlencode(data)
			headers['Content-Length'] = len(data)
			method = 'POST'
		else:
			method = 'GET'

		try:
			url = "%s/%s" % (self.url, path)
			retries = 0
			while retries <= 2:
				logging.info(url)
				if self.offline:
					response = urlfetch.fetch(url=url, payload=data, method=method, headers=headers, deadline=60)
				else:
					response = urlfetch.fetch(url=url, payload=data, method=method, headers=headers, deadline=10)

				if response.status_code < 300:
					return response
				else:
					logging.exception('URLFetch returned with HTTP %s when requesting URL:\n%s' % (response.status_code, url))
					# If this is a server error, we retry the request up to 2 times
					if response.status_code >= 500:
						retries += 1
						# Wait a couple seconds before another attempt
						if self.offline:
							time.sleep(retries*2)
						else:
							time.sleep(1)
						continue
				break

		except Exception, e:
			pass

		if response:
			raise FogBugzServerError(response.status_code, ': '.join(msg_dict[response.status_code]), response.content)
		elif e:
			raise e
		else:
			raise FogBugzClientError("Please report this exception as an issue with pyfogbugz.")



class ApiCheckHandler(XmlHandler):
	def __init__(self):
		super(ApiCheckHandler, self).__init__()
		self.version = ''
		self.minversion = ''
		self.url = ''

	def endElement(self, name):
		if name == 'version':
			self.version = self.current_value
		elif name == 'minversion':
			self.minversion = self.current_value
		elif name == 'url':
			self.url = self.current_value
		super(ApiCheckHandler, self).endElement(name)


class LogonHandler(XmlHandler):
	def __init__(self):
		super(LogonHandler, self).__init__()
		self.token = None
		self.people = None

	def startElement(self, name, attrs):
		super(LogonHandler, self).startElement(name, attrs)
		if name == 'people':
			self.people = []

	def endElement(self, name):
		if name == 'token':
			self.token = self.current_value
		elif name == 'person':
			self.people.append(self.current_value)
		super(LogonHandler, self).endElement(name)



class FogBugzConnection(Connection):
	# This class will try to use the token first (if provided), but if a request fails because the token is not valid
	# any more, it will automatically log in with the username and password and update the token.
	def __init__(self, url, username, password, token=None, offline=False):
		self.username = username
		self.password = password
		self.token = token
		self.base_path = None
		super(FogBugzConnection, self).__init__(url, offline)
		self._check_api()
		if token is None:
			self._logon()

	def make_request(self, path, data=None):
		if self.base_path:
			computed_path = "%s%s" % (self.base_path, path)
			if self.token:
				computed_path += "&token=%s" % self.token
		else:
			computed_path = path
		return super(FogBugzConnection, self).make_request(computed_path, data)

	def _check_api(self):
		response = self.make_request('api.xml')
		if response:
			data = response.content
			handler = ApiCheckHandler()
			xml.sax.parseString(data, handler)
			self.base_path = handler.url
		else:
			raise FogBugzClientError("Could not validate API.")

	def _logon(self):
		response = self.make_request('cmd=logon&email=%s&password=%s' % (urllib.quote_plus(self.username), urllib.quote_plus(self.password)))
		if response:
			data = response.content
			handler = LogonHandler()
			xml.sax.parseString(data, handler)
			if handler.has_error:
				raise FogBugzClientError("Invalid login: %s" % handler.error_message, handler.error_code)
			else:
				self.token = handler.token

	def list_filters(self):
		response = self.make_request('cmd=listFilters')
		if response:
			data = response.content
			filter_list = FilterList(connection=self)
			xml.sax.parseString(data, filter_list)
			if filter_list.has_error:
				if filter_list.error_code == 3:
					# The old token is invalid, log in with username and password to get a new token
					self.token = None
					self._logon()
					# Execute this command again
					return self.list_filters()
				else:
					raise FogBugzClientError("Invalid filter request: %s" % filter_list.error_message, filter_list.error_code)
			else:
				return filter_list.filters

	def list_cases(self, search=None, cols=None, max_records=None):
		query = 'cmd=search'
		if search:
			query += '&q=%s' % urllib.quote_plus(search)
		if cols:
			query += '&cols=%s' % urllib.quote_plus(cols)
		else:
			query += '&cols=%s' % urllib.quote_plus(','.join(AVAILABLE_CASE_COLUMNS))
		if max_records:
			query += '&max=%s' % max_records
		response = self.make_request(query)
		if response:
			data = response.content
			case_list = CaseList(connection=self)
			xml.sax.parseString(data, case_list)
			if case_list.has_error:
				if case_list.error_code == 3:
					# The old token is invalid, log in with username and password to get a new token
					self.token = None
					self._logon()
					# Execute this command again
					return self.list_cases(search, cols, max_records)
				else:
					raise FogBugzClientError("Invalid search: %s" % case_list.error_message, case_list.error_code)
			else:
				return case_list.cases

	# Supported cmd: new, edit, reactivate, reopen, resolve, close.
	# If cmd is resolve, ixStatus must be in fields.
	# If cmd is new, id is ignored
	def edit_case(self, id, fields, values, cols=None, cmd='edit'):
		if cmd == 'new':
			query = 'cmd=new'
		else:
			query = 'cmd=%s&ixBug=%s' % (cmd, id)

		for i in range(len(fields)):
			query += '&%s=%s' % (fields[i], urllib.quote_plus(values[i]))
		if cols:
			query += '&cols=' + urllib.quote_plus(cols)

		response = self.make_request(query)
		if response:
			data = response.content
			case_list = CaseList(connection=self)
			xml.sax.parseString(data, case_list)
			if case_list.has_error:
				if case_list.error_code == 3:
					# The old token is invalid, log in with username and password to get a new token
					self.token = None
					self._logon()
					# Execute this command again
					return self.edit_case(id, fields, values, cols, cmd)
				else:
					raise FogBugzClientError("Invalid search: %s" % case_list.error_message, case_list.error_code)
			else:
				return case_list.cases

	def list_statuses(self, category_id=None, resolved_only=None):
		query = 'cmd=listStatuses'
		if category_id:
			query += '&ixCategory=%s' % category_id
		if resolved_only:
			query += '&fResolved=1'
		response = self.make_request(query)
		if response:
			data = response.content
			status_list = StatusList()
			xml.sax.parseString(data, status_list)
			if status_list.has_error:
				if status_list.error_code == 3:
					# The old token is invalid, log in with username and password to get a new token
					self.token = None
					self._logon()
					# Execute this command again
					return self.list_statuses(category_id, resolved_only)
				else:
					raise FogBugzClientError("Invalid listing: %s" % status_list.error_message, status_list.error_code)
			else:
				return status_list.statuses
