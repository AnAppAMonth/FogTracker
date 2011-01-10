#!/usr/bin/env python
#
# Copyright (c) 2011 Feng Qiu http://www.ban90.com
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

import re, random, time
from datetime import datetime
from xml.sax.saxutils import escape
from xml.dom import minidom

from google.appengine.ext import webapp
from google.appengine.ext.webapp import util, template
from google.appengine.api import urlfetch, users
from google.appengine.ext import db

from pyfogbugz import connection
from model import Integration

# This class handles requests to the public pages of the website
class MainPage(webapp.RequestHandler):
	def get(self, page):
		user = users.get_current_user()

		if user:
			url = users.create_logout_url(self.request.uri)
			url_linktext = 'Sign Out'
			status_text = 'currently signed in as ' + user.nickname()
		else:
			url = users.create_login_url(self.request.uri)
			url_linktext = 'Sign In'
			status_text = 'sign in to manage your integrations'

		template_values = {
			'signed_in': user is not None,
			'url': url,
			'url_linktext': url_linktext,
			'status_text': status_text,
			}

		if page == 'edit':
			if user:
				token = self.request.get('token', '')
				if token:
					entry = Integration.all().filter('token = ', token).get()
					if entry:
						# Make sure this integration was created by this user
						if entry.account == user.user_id():
							template_values['fburl'] = entry.fburl
							template_values['fbuser'] = entry.fbuser
							template_values['pttoken'] = entry.pttoken
							template_values['mapping'] = entry.mapping
							template_values['resolve'] = entry.resolve

							template_values['token'] = token
							return self.response.out.write(template.render('templates/new.html', template_values))

			self.redirect('/')
		elif page == 'delete':
			self.redirect('/')
		elif page:
			self.response.out.write(template.render('templates/%s.html' % page, template_values))
		else:
			if user:
				# The user is signed in, we need to display a list of her existing integrations
				template_values['integrations'] = Integration.all().filter('account = ', user.user_id()).order('created').fetch(1000)

			self.response.out.write(template.render('templates/index.html', template_values))

	# This method handles the POST requests to create a new integration and editing or deleting an existing integration
	def post(self, page):
		user = users.get_current_user()
		if user:
			# The "new" and "edit" commands are processed with the same code. It all depends on whether the parameter
			# "token" is present.
			if page == 'new' or page == 'edit':
				token = self.request.get('token', '')

				# Retrieve POST parameters
				fburl = self.request.get('fburl', '')
				fbuser = self.request.get('fbuser', '')
				fbpass = self.request.get('fbpass', '')
				pttoken = self.request.get('pttoken', '')
				mapping = self.request.get('mapping', '')
				resolve = self.request.get('resolve', '')

				# Validate POST parameters
				template_values = {}
				if fburl == '':
					template_values['fburl_empty'] = True
				else:
					# Remove trailing '/' from the base url
					try:
						while fburl[-1] == '/':
							fburl = fburl[:-1]
					except IndexError:
						template_values['fburl_empty'] = True
				if fbuser == '':
					template_values['fbuser_empty'] = True
				if fbpass == '':
					template_values['fbpass_empty'] = True
				if pttoken == '':
					template_values['pttoken_empty'] = True

				if template_values <> {}:
					# A required field is empty, validation failed
					if token:
						template_values['token'] = token

					template_values['fburl'] = fburl
					template_values['fbuser'] = fbuser
					template_values['pttoken'] = pttoken
					template_values['mapping'] = mapping
					template_values['resolve'] = resolve

					template_values['signed_in'] = True
					template_values['url'] = users.create_logout_url(self.request.uri)
					template_values['url_linktext'] = 'Sign Out'
					template_values['status_text'] = 'currently signed in as ' + user.nickname()

					# the same template is used for both "new" and "edit" actions
					return self.response.out.write(template.render('templates/new.html', template_values))
				else:
					# Validation passed
					if token:
						# We are editing an existing integration
						entry = Integration.all().filter('token = ', token).get()
						if entry:
							# Make sure this integration was created by this user
							if entry.account == user.user_id():
								entry.fburl = fburl
								entry.fbuser = fbuser
								entry.fbpass = fbpass
								entry.pttoken = pttoken
								entry.mapping = mapping
								entry.resolve = resolve
								entry.put()
					else:
						# Create a 32-characters random string as the token
						# Use both the system time and the user's IP address to initialize the random number generator
						random.seed(str(time.time()) + self.request.remote_addr)
						while True:
							token = ''
							for i in range(32):
								num = random.randint(0, 35)
								if num <= 9:
									token += str(num)
								else:
									token += chr(num+87)

							# Make sure this token hasn't already been used
							if Integration.all().filter('token = ', token).get() is None:
								break

						# Get the time of creation, then set microsecond to 0
						created = datetime.now().replace(microsecond = 0)

						# Now create a new integration object with the data
						entry = Integration(account=user.user_id(), token=token, created=created, fburl=fburl,
											fbuser=fbuser, fbpass=fbpass, pttoken=pttoken, mapping=mapping,
											resolve=resolve, status='<span class="new">New</span>')
						entry.put()

			elif page == 'delete':
				token = self.request.get('token', '')
				if token:
					entry = Integration.all().filter('token = ', token).get()
					if entry:
						# Make sure this integration was created by this user
						if entry.account == user.user_id():
							db.delete(entry)

		self.redirect('/')

# This class implements the XML feed of cases in FogBugz used to populate the import panel in Tracker
class CaseFeedHandler(webapp.RequestHandler):
	def get(self, token):
		# First get the integration object
		obj = Integration.all().filter('token = ', token).get()
		if obj is None:
			self.response.set_status(404)
			return

		conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken)

		# This is the query used to specify the cases to include in the feed
		query = self.request.get('q', '')

		cases = conn.list_cases(query + '%20status:active%20-tag:"ts*"', 'ixBug,ixBugParent,ixBugChildren,sTitle,sPersonAssignedTo,ixCategory,dtOpened,events', 1000)

		output = '<?xml version="1.0" encoding="UTF-8"?>\n'
		output += '<external_stories type="array">\n'
		for case in cases:
			if case.category_id <> '3':
				output += '  <external_story>\n'
				output += '	<external_id>%s</external_id>\n' % case.id
				output += '	<name>%s</name>\n' % escape(case.title)

				summary = case.events[0].text
				if case.parent_case > '0':
					summary = 'Parent Case: %s/default.asp?%s\n\n' % (conn.url, case.parent_case) + summary
				if case.child_cases:
					summary += '\n\nChild Cases:'
					for cc in case.child_cases.split(','):
						summary += '\n%s/default.asp?' % conn.url + cc
				output += '	<description>%s</description>\n' % escape(summary)

				output += '	<requested_by>%s</requested_by>\n' % escape(case.assigned_to_name)
				output += '	<created_at type="datetime">%s</created_at>\n' % case.date_opened.replace('T', ' ').replace('Z', ' UTC')

				if case.category_id == '1':
					tp = 'bug'
				elif case.category_id == '2':
					tp = 'feature'
				elif case.category_id == '4':
					tp = 'release'
				else:
					tp = 'chore'
				output += '	<story_type>%s</story_type>\n' % tp

				output += '  </external_story>\n'
		output += '</external_stories>\n'

		# If the token has been updated, also update it in the integration object
		if obj.fbtoken <> conn.token:
			obj.fbtoken = conn.token
			obj.put()

		self.response.headers.add_header("Content-Type", 'text/xml')
		self.response.out.write(output)

class Story(object):
	def __init__(self, fbid):
		self.fbid = fbid
		self.ptid = None
		self.title = None
		self.state = None
		self.notes = []

# This class receives activity notifications from Tracker, and updates FogBugz accordingly via API
class WebHookHandler(webapp.RequestHandler):
	def post(self, token):
		# We must parse the XML no matter what, because any type of event can contain a note/comment in it
		dom = minidom.parseString(self.request.body)
		type = dom.getElementsByTagName('event_type')[0].firstChild.nodeValue
		stories = dom.getElementsByTagName('stories')[0]
		entries = []
		for story in stories.childNodes:
			try:
				if story.nodeName == 'story':
					fbid = story.getElementsByTagName('other_id')[0].firstChild.nodeValue
					entry = Story(fbid)
					if type == 'story_create':
						entry.ptid = story.getElementsByTagName('id')[0].firstChild.nodeValue
						entries.append(entry)
					else:
						# Only record title changes, status changes, and new notes
						changed = False
						try:
							entry.title = story.getElementsByTagName('name')[0].firstChild.nodeValue
						except:
							pass
						else:
							changed = True

						try:
							entry.state = story.getElementsByTagName('current_state')[0].firstChild.nodeValue
						except:
							pass
						else:
							changed = True

						try:
							notes = story.getElementsByTagName('notes')[0]
							for note in notes.childNodes:
								if note.nodeName == 'note':
									self.notes.append(note.getElementsByTagName('text')[0].firstChild.nodeValue)
						except:
							pass
						else:
							changed = True

						if changed:
							entries.append(entry)
			except:
				pass

		if entries <> []:
			# At least one of the listed stories is an import from FogBugz, and more operations are needed
			# First get the integration object
			obj = Integration.all().filter('token = ', token).get()
			if obj is None:
				self.response.set_status(404)
				return

			conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken)

			# We put the author of the activity into the event text to indicate who did this.
			try:
				author = dom.getElementsByTagName('author')[0].firstChild.nodeValue
			except:
				author = 'Unknown'

			for entry in entries:
				if type == 'story_create':
					# A new story has just been created (by importing an existing case from FogBugz)
					# First, set the sComputer field of the corresponding FogBugz case to the URL of the story in Tracker,
					# and also return a list of all existing events of the FogBugz case
					fields = ['sComputer', 'sEvent']
					values = ['https://www.pivotaltracker.com/story/show/%s' % entry.ptid, 'Case imported into Pivotal Tracker by ' + author + '.']
					case = conn.edit_case(entry.fbid, fields, values, 'ixBug,sProject,events')[0]

					# Second, add all existing events in this FogBugz case into Tracker as comments on this story
					for event in case.events:
						headers = {}
						headers['X-TrackerToken'] = obj.pttoken
						headers['Content-Type'] = 'application/xml'

						data = event.description
						if event.changes:
							data += '\n' + event.changes
						if event.text:
							data += '\n' + event.text
						data = '<note><text>%s</text></note>' % escape(data)

						urlfetch.fetch('http://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (case.project_title, entry.ptid), payload=data, method='POST', headers=headers, deadline=10)
				else:
					# A story has just been edited, currently we only propogate title changes, status changes and new notes/comments to FogBugz

					# If multiple actions are performed at once, we first create a Fogbugz case event for each note/comment included, and finally
					# create another case event for all other changes (if any), including title and status changes. We feel it makes more sense
					# this way (e.g. comments on why an action is performed appear before the action itself), and it also saves some work.

					# An instance of Case that contains information we need for certain operations
					case = None

					# Each new note is sent in its own edit request
					if entry.notes <> []:
						# A new comment has just been created, add it to FogBugz as a case event
						for i in range(len(entry.notes)):
							if case is None:
								case = conn.edit_case(entry.fbid, ['sEvent'], ['Comment posted by ' + author + ' in Pivotal Tracker:\n\n' + entry.notes[i]], 'ixBug,ixCategory,sCategory')[0]
							else:
								conn.edit_case(entry.fbid, ['sEvent'], ['Comment posted by ' + author + ' in Pivotal Tracker:\n\n' + entry.notes[i]])

					# Title and status changes are incorporated in a single edit request
					fields = []
					values = []

					if entry.title is not None:
						fields.append('sTitle')
						values.append(entry.title)

					# Status changes are tricky, as there are restrictions on which status can be changed to which status,
					# while no such restrictions exist in Tracker.
					extra = False
					if entry.state in ('started', 'finished', 'accepted'):
						# We need to know the current status of the FogBugz case to decide which command to use
						if case is None:
							case = conn.list_cases(entry.fbid, 'ixBug,ixCategory,sCategory')[0]

						if entry.state == 'accepted':
							# Close the case in FogBugz, if not already closed
							if 'close' in case.operations:
								# Case is currently resolved, close it
								cmd = 'close'
							elif 'resolve' in case.operations:
								# Case is currently active, two separate commands are needed to close it
								# First resolve it
								entry.state = 'finished'
								extra = True

						if entry.state == 'started':
							# Reactivate/reopen the case in FogBugz, if not already active
							if 'reactivate' in case.operations:
								# Case is currently resolved, reactivate it
								cmd = 'reactivate'
							elif 'reopen' in case.operations:
								# Case is currently closed, reopen it
								cmd = 'reopen'
						elif entry.state == 'finished':
							# Resolve the case in FogBugz only when it's currently active
							if 'resolve' in case.operations and 'reactivate' not in case.operations:
								# This one is tricky as we must find out the proper status to resolve to
								cmd = 'resolve'

								# First try to find the status to resolve to in configuration
								status = None
								for line in obj.resolve.splitlines():
									t = line.partition(':')
									if t[0].strip().lower() == case.category_name.lower():
										status = t[2].strip()
										break
								if status is None:
									# Status not specified in configuration, fetch all resolved statuses of this category from FogBugz
									statuses = conn.list_statuses(case.category_id, True)

									# Now choose the "best" status in the list to use.
									# The criteria is to prefer statuses that are not "deleted", not a "duplicate", "work done",
									# and order highly, in this order.
									t = None
									for i in range(len(statuses)):
										s = (statuses[i].is_deleted, statuses[i].is_duplicate, not statuses[i].is_work_done, statuses[i].order, statuses[i].id)
										if t is None or s < t:
											t = s
									status = t[4]

								# Finally, insert the status into fields
								fields.append('ixStatus')
								values.append(status)

					else:
						cmd = 'edit'

					if fields <> [] or cmd <> 'edit':
						fields.append('sEvent')
						values.append('By ' + author + ' in Pivotal Tracker.')
						conn.edit_case(entry.fbid, fields, values, cmd=cmd)

						if extra:
							# Extra step needed to close the case (after resolving it)
							conn.edit_case(entry.fbid, ['sEvent'], [], cmd='close')

			# If the token has been updated, also update it in the integration object
			if obj.fbtoken <> conn.token:
				obj.fbtoken = conn.token
				obj.put()

		self.response.out.write('OK')

# Original URL used:
# http://fogtracker.appspot.com/9D35cnPx7ij4ol8h56b-X0dz/?AreaID={AreaID}&AreaName={AreaName}&CaseNumber={CaseNumber}&CaseEventID={CaseEventID}&Category={Category}&TrackerURL={Computer}&EmailBodyText={EmailBodyText}&EmailDate={EmailDate}&EmailSubject={EmailSubject}&EventText={EventText}&EventTime={EventTime}&EventType={EventType}&ProjectName={ProjectName}&StatusName={StatusName}&Title={Title}
# This class receives activity notifications from FogBugz, and updates Tracker accordingly via API
class URLTriggerHandler(webapp.RequestHandler):
	def get(self, token):
		cid = self.request.get('CaseNumber')
		eid = self.request.get('CaseEventID')
		if cid and eid:
			# A new case event has occured, let's see whether the case is already imported into Tracker
			turl = self.request.get('TrackerURL')
			tid = turl.rpartition('/')[2]
			try:
				t = int(tid)
			except:
				pass
			else:
				# Now fetch all events from that case to get detailed info
				# First get the integration object
				obj = Integration.all().filter('token = ', token).get()
				if obj is None:
					self.response.set_status(404)
					return

				conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken)

				case = conn.list_cases(cid, 'ixBug,ixBugParent,ixBugChildren,sTitle,events')[0]
				for i in range(len(case.events)-1, -1, -1):
					if case.events[i].id == eid:
						# This is the event we just received
						event = case.events[i]

						# This is the type of the event
						type = self.request.get('EventType')

						# See what changes have been made
						tc = False
						pe = False
						for c in event.changes.split('\n'):
							if c.find('Title changed')==0:
								tc = True
							else:
								mo = re.match(r'Revised.*?from\s([\d/]+)\sat\s([\d\:]+)\sUTC', c)
								if mo:
									# A comment is changed in this event
									d = 'T'.join(mo.groups()).replace('/', '-')
									if case.events[0].date.find(d) == 0:
										# The first comment is changed
										pe = True

						headers = {}
						headers['X-TrackerToken'] = obj.pttoken
						headers['Content-Type'] = 'application/xml'

						if tc or pe or type <> 'CaseEdited':
							# We must modify the story (title/description/state)
							data = '<story>'
							if tc:
								data += '<name>%s</name>' % escape(case.title)

							if pe:
								summary = case.events[0].text
								if case.parent_case > '0':
									summary = 'Parent Case: %s/default.asp?%s\n\n' % (conn.url, case.parent_case) + summary
								if case.child_cases:
									summary += '\n\nChild Cases:'
									for cc in case.child_cases.split(','):
										summary += '\n%s/default.asp?' % conn.url + cc
								data += '<description>%s</description>' % escape(summary)

							if type == 'CaseResolved':
								# Finish the story in Tracker
								data += '<current_state>finished</current_state>'
							elif type == 'CaseClosed':
								# Accept the story in Tracker
								data += '<current_state>accepted</current_state>'
							elif type == 'CaseReactivated' or type == 'CaseReopened':
								# Unstart the story in Tracker
								data += '<current_state>unstarted</current_state>'

							data += '</story>'

							urlfetch.fetch('http://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (self.request.get('ProjectName'), tid), payload=data, method='PUT', headers=headers, deadline=10)

						# Finally add a comment in Tracker to reflect this case event (but only when this event wasn't created as a result of a comment in Tracker)
						if re.match(r'Comment posted by [^\n]* in Pivotal Tracker:\n', event.text) is None:
							data = event.description
							if event.changes:
								data += '\n' + event.changes
							if event.text:
								data += '\n' + event.text
							data = '<note><text>%s</text></note>' % escape(data)
							urlfetch.fetch('http://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (self.request.get('ProjectName'), tid), payload=data, method='POST', headers=headers, deadline=10)

						break

				# If the token has been updated, also update it in the integration object
				if obj.fbtoken <> conn.token:
					obj.fbtoken = conn.token
					obj.put()

		self.response.out.write('OK')

def main():
	application = webapp.WSGIApplication([(r'/(features|limitations|howto|new|edit|delete)?', MainPage),
											(r'/(.+)/CaseFeed/', CaseFeedHandler),
											(r'/(.+)/WebHook/', WebHookHandler),
											(r'/(.+)/URLTrigger/', URLTriggerHandler),
											],
										debug=True)
	util.run_wsgi_app(application)


if __name__ == '__main__':
	main()
