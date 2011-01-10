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

import xml.sax

from pyfogbugz import XmlHandler

class Case(object):
	def __init__(self, id=None, operations=None, connection=None):
		self.connection = connection
		self.id = id
		self.operations = operations

		self.parent_case = None
		self.child_cases = None
		self.tags = None
		self.is_open = None
		self.title = None
		self.summary = None
		self.latest_text_event = None
		self.project_id = None
		self.project_title = None
		self.area_id = None
		self.area_title = None
		self.group_id = None
		self.assigned_to_id = None
		self.assigned_to_name = None
		self.assigned_to_email = None
		self.opened_by_id = None
		self.resolved_by_id = None
		self.closed_by_id = None
		self.last_edited_by_id = None
		self.status_id = None
		self.status_name = None
		self.priority_id = None
		self.priority_name = None
		self.fixfor_id = None
		self.fixfor_name = None
		self.fixfor_date = None
		self.original_estimate = None
		self.current_estimate = None
		self.total_elapsed = None
		self.number_of_occurrences = None
		self.customer_email = None
		self.mailbox = None
		self.category_id = None
		self.category_name = None
		self.date_opened = None
		self.date_resolved = None
		self.date_closed = None
		self.latest_bugevent = None
		self.date_updated = None
		self.replied = None
		self.forwarded = None
		self.customer_ticket_id = None
		self.discussion_topic_id = None
		self.date_due = None
		self.release_notes = None
		self.date_last_viewed = None
		self.related_bugs = None
		self.scout_description = None
		self.scout_message = None
		self.scout_disable = None
		self.subscribed = None
		self.events = None

class Event(object):
	def __init__(self, case=None, id=None):
		self.case = case
		self.id = id

		self.type = None
		self.verb = None
		self.person_id = None
		self.person_name = None
		self.assigned_to_id = None
		self.date = None
		self.text = None
		self.fEmail = None
		self.fHtml = None
		self.fExternal = None
		self.bEmail = None
		self.bExternal = None
		self.changes = None
		self.description = None
		self.attachments = None

		# Additional fields if the event is an email
		self.email_from = None
		self.email_to = None
		self.email_cc = None
		self.email_bcc = None
		self.email_reply_to = None
		self.email_subject = None
		self.email_date = None
		self.email_body_text = None
		self.email_body_html = None


class Attachment(object):
	def __init__(self, event=None):
		self.event = event

		self.filename = None
		self.url = None

# Although called a "case list", it supports both a list of cases returned by a "search", and a single case returned by
# an "edit" that specifies a set of columns to return
class CaseList(XmlHandler):
	def __init__(self, connection):
		super(CaseList, self).__init__()
		self.cases = []
		self.current_case = None
		self.current_event = None
		self.current_attachment = None
		self.connection = connection

	def startElement(self, name, attrs):
		super(CaseList, self).startElement(name, attrs)
		if name == 'case':
			self.current_case = Case(id=attrs['ixBug'], operations=attrs['operations'].split(','), connection=self.connection)
		elif name == 'tags' and self.current_case is not None:
			self.current_case.tags = []
		elif name == 'events' and self.current_case is not None:
			self.current_case.events = []
		elif name == 'event' and self.current_case is not None and self.current_case.events is not None:
			self.current_event = Event(case = self.current_case.id, id = attrs['ixBugEvent'])
		elif name == 'rgAttachments' and self.current_event is not None:
			self.current_event.attachments = []
		elif name == 'attachment' and self.current_event is not None and self.current_event.attachments is not None:
			self.current_attachment = Attachment(event = self.current_event.id)

	def endElement(self, name):
		# Container elements
		if name == 'attachment' and self.current_attachment is not None:
			self.current_event.attachments.append(self.current_attachment)
			self.current_attachment = None
		elif name == 'rgAttachments':
			self.current_attachment = None
		elif name == 'event' and self.current_event is not None:
			self.current_case.events.append(self.current_event)
			self.current_attachment = None
			self.current_event = None
		elif name == 'events':
			self.current_attachment = None
			self.current_event = None
		elif name == 'case' and self.current_case is not None:
			self.cases.append(self.current_case)
			self.current_attachment = None
			self.current_event = None
			self.current_case = None

		# Elements of an attachment
		if self.current_attachment is not None:
			if name == 'sFileName':
				self.current_attachment.filename = self.current_value
			elif name == 'sURL':
				self.current_attachment.url = self.current_value

		# Elements of an event
		if self.current_event is not None:
			if name == 'evt':
				self.current_event.type = self.current_value
			elif name == 'sVerb':
				self.current_event.verb = self.current_value
			elif name == 'ixPerson':
				self.current_event.person_id = self.current_value
			elif name == 'sPerson':
				self.current_event.person_name = self.current_value
			elif name == 'ixPersonAssignedTo':
				self.current_event.assigned_to_id = self.current_value
			elif name == 'dt':
				self.current_event.date = self.current_value
			elif name == 's':
				self.current_event.text = self.current_value
			elif name == 'fEmail':
				self.current_event.fEmail = (self.current_value == 'true')
			elif name == 'fHTML':
				self.current_event.fHtml = (self.current_value == 'true')
			elif name == 'fExternal':
				self.current_event.fExternal = (self.current_value == 'true')
			elif name == 'bEmail':
				self.current_event.bEmail = (self.current_value == 'true')
			elif name == 'bExternal':
				self.current_event.bExternal = (self.current_value == 'true')
			elif name == 'sChanges':
				self.current_event.changes = self.current_value
			elif name == 'evtDescription':
				self.current_event.description = self.current_value

			elif name == 'sFrom':
				self.current_event.email_from = self.current_value
			elif name == 'sTo':
				self.current_event.email_to = self.current_value
			elif name == 'sCC':
				self.current_event.email_cc = self.current_value
			elif name == 'sBCC':
				self.current_event.email_bcc = self.current_value
			elif name == 'sReplyTo':
				self.current_event.email_reply_to = self.current_value
			elif name == 'sSubject':
				self.current_event.email_subject = self.current_value
			elif name == 'sDate':
				self.current_event.email_date = self.current_value
			elif name == 'sBodyText':
				self.current_event.email_body_text = self.current_value
			elif name == 'sBodyHTML':
				self.current_event.email_body_html = self.current_value

		# Elements of a case
		if self.current_case is not None:
			if name == 'ixBugParent':
				self.current_case.parent_case = self.current_value
			elif name == 'ixBugChildren':
				self.current_case.child_cases = self.current_value
			elif name == 'tag':
				if self.current_case.tags is not None:
					self.current_case.tags.append(self.current_value)
			elif name == 'fOpen':
				if self.current_value == 'false':
					self.current_case.is_open = False
				else:
					self.current_case.is_open = True
			elif name == 'sTitle':
				self.current_case.title = self.current_value
			elif name == 'sLatestTextSummary':
				self.current_case.summary = self.current_value
			elif name == 'ixBugEventLatestText':
				self.current_case.latest_text_event = self.current_value
			elif name == 'ixProject':
				self.current_case.project_id = self.current_value
			elif name == 'sProject':
				self.current_case.project_title = self.current_value
			elif name == 'ixArea':
				self.current_case.area_id = self.current_value
			elif name == 'sArea':
				self.current_case.area_title = self.current_value
			elif name == 'ixGroup':
				self.current_case.group_id = self.current_value
			elif name == 'ixPersonAssignedTo':
				self.current_case.assigned_to_id = self.current_value
			elif name == 'sPersonAssignedTo':
				self.current_case.assigned_to_name = self.current_value
			elif name == 'sEmailAssignedTo':
				self.current_case.assigned_to_email = self.current_value
			elif name == 'ixPersonOpenedBy':
				self.current_case.opened_by_id = self.current_value
			elif name == 'ixPersonResolvedBy':
				self.current_case.resolved_by_id = self.current_value
			elif name == 'ixPersonClosedBy':
				self.current_case.closed_by_id = self.current_value
			elif name == 'ixPersonLastEditedBy':
				self.current_case.last_edited_by_id = self.current_value
			elif name == 'ixStatus':
				self.current_case.status_id = self.current_value
			elif name == 'sStatus':
				self.current_case.status_name = self.current_value
			elif name == 'ixPriority':
				self.current_case.priority_id = self.current_value
			elif name == 'sPriority':
				self.current_case.priority_name = self.current_value
			elif name == 'ixFixFor':
				self.current_case.fixfor_id = self.current_value
			elif name == 'sFixFor':
				self.current_case.fixfor_name = self.current_value
			elif name == 'dtFixFor':
				self.current_case.fixfor_date = self.current_value
			elif name == 'hrsOrigEst':
				self.current_case.original_estimate = self.current_value
			elif name == 'hrsCurrEst':
				self.current_case.current_estimate = self.current_value
			elif name == 'hrsElapsed':
				self.current_case.total_elapsed = self.current_value
			elif name == 'c':
				self.current_case.number_of_occurrences = self.current_value
			elif name == 'sCustomerEmail':
				self.current_case.customer_email = self.current_value
			elif name == 'ixMailbox':
				self.current_case.mailbox = self.current_value
			elif name == 'ixCategory':
				self.current_case.category_id = self.current_value
			elif name == 'sCategory':
				self.current_case.category_name = self.current_value
			elif name == 'dtOpened':
				self.current_case.date_opened = self.current_value
			elif name == 'dtResolved':
				self.current_case.date_resolved = self.current_value
			elif name == 'dtClosed':
				self.current_case.date_closed = self.current_value
			elif name == 'ixBugEventLatest':
				self.current_case.latest_bugevent = self.current_value
			elif name == 'dtLastUpdated':
				self.current_case.date_updated = self.current_value
			elif name == 'fReplied':
				self.current_case.replied = False
				if self.current_value == "true":
					self.current_case.replied = True
			elif name == 'fForwarded':
				self.current_case.forwarded = False
				if self.current_value == "true":
					self.current_case.forwarded = True
			elif name == 'sTicket':
				self.current_case.customer_ticket_id = self.current_value
			elif name == 'ixDiscussTopic':
				self.current_case.discussion_topic_id = self.current_value
			elif name == 'dtDue':
				self.current_case.date_due = self.current_value
			elif name == 'sReleaseNotes':
				self.current_case.release_notes = self.current_value
			elif name == 'dtLastView':
				self.current_case.date_last_viewed = self.current_value
			elif name == 'ixRelatedBugs':
				self.current_case.related_bugs = self.current_value.split(',')
			elif name == 'sScoutDescription':
				self.current_case.scout_description = self.current_value
			elif name == 'sScoutMessage':
				self.current_case.scout_message = self.current_value
			elif name == 'fScoutStopReporting':
				self.current_case.scout_disable = (self.current_value == 'true')
			elif name == 'fSubscribed':
				self.current_case.subscribed = False
				if self.current_value == "true":
					self.current_case.subscribed = True

		super(CaseList, self).endElement(name)
