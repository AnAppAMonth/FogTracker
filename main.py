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
							template_values['tagsync'] = entry.tagsync
							template_values['ptprop'] = entry.ptprop
							template_values['ptintid'] = entry.ptintid
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
				tagsync = self.request.get('tagsync', '') == 'on'
				ptprop = self.request.get('ptprop', '') == 'on'
				ptintid = self.request.get('ptintid', '')
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
				if ptprop and ptintid == '':
					template_values['ptintid_empty'] = True

				if template_values != {}:
					# A required field is empty, validation failed
					if token:
						template_values['token'] = token

					template_values['fburl'] = fburl
					template_values['fbuser'] = fbuser
					template_values['pttoken'] = pttoken
					template_values['tagsync'] = tagsync
					template_values['ptprop'] = ptprop
					template_values['ptintid'] = ptintid
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
								entry.tagsync = tagsync
								entry.ptprop = ptprop
								entry.ptintid = ptintid
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
						entry = Integration(account=user.user_id(), token=token, created=created, fburl=fburl, fbuser=fbuser,
											fbpass=fbpass, pttoken=pttoken, tagsync=tagsync, ptprop=ptprop, ptintid=ptintid,
											mapping=mapping, resolve=resolve, status='<span class="new">New</span>')
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

		cases = conn.list_cases(query + ' status:active -tag:"ts@*"', 'ixBug,ixBugParent,ixBugChildren,sTitle,sPersonAssignedTo,ixCategory,dtOpened,events', 1000)

		output = '<?xml version="1.0" encoding="UTF-8"?>\n'
		output += '<external_stories type="array">\n'
		for case in cases:
			if case.category_id != '3':
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

				if obj.tagsync:
					output += ' <labels>%s</labels>\n' % escape(','.join(case.tags))

				output += '  </external_story>\n'
		output += '</external_stories>\n'

		# If the token has been updated, also update it in the integration object
		if obj.fbtoken != conn.token:
			obj.fbtoken = conn.token
			obj.put()

		self.response.headers.add_header("Content-Type", 'text/xml')
		self.response.out.write(output)

class Story(object):
	def __init__(self, fbid):
		self.fbid = fbid
		self.ptid = None
		self.title = None
		self.stype = None
		self.state = None
		self.labels = None
		self.notes = []

# This class receives activity notifications from Tracker, and updates FogBugz accordingly via API
class WebHookHandler(webapp.RequestHandler):
	def post(self, token):
		# First get the integration object
		obj = Integration.all().filter('token = ', token).get()
		if obj is None:
			self.response.set_status(404)
			return

		conn = None

		# We must parse the XML no matter what, because any type of event can contain a note/comment in it
		dom = minidom.parseString(self.request.body)
		type = dom.getElementsByTagName('event_type')[0].firstChild.nodeValue
		proj_id = dom.getElementsByTagName('project_id')[0].firstChild.nodeValue
		# We put the author of the activity into the event text to indicate who did this.
		try:
			author = dom.getElementsByTagName('author')[0].firstChild.nodeValue
		except IndexError:
			author = 'Unknown'
		stories = dom.getElementsByTagName('stories')[0]
		entries = []
		for story in stories.childNodes:
			try:
				if story.nodeName == 'story':
					# First check whether this story is an import from the FogBugz installation specified in this
					# integration profile.
					if story.getElementsByTagName('integration_id'):
						# This story is an import, check the source
						url = story.getElementsByTagName('other_url')[0].firstChild.nodeValue.partition('://')[2]
						fburl = obj.fburl.partition('://')[2]
						if url.find(fburl) != 0:
							# This story was not imported from this FogBugz installation, nothing needs to be done
							continue
					else:
						# This story isn't an import from any source, check its labels if obj.ptprop is True
						if obj.ptprop:
							labels = story.getElementsByTagName('labels')
							if labels:
								labels = labels[0].firstChild.nodeValue.split(',')
								proj = None
								for i in range(len(labels)):
									if labels[i][:3] == 'fb:':
										proj = labels[i][3:]
										del labels[i]
										break

								if proj:
									# We should propagate the story to FogBugz
									if conn is None:
										conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken)

									ptid = story.getElementsByTagName('id')[0].firstChild.nodeValue
									tags = 'ts@%s-%s' % (proj_id, ptid)

									# If tagsync is True, add the labels as tags to the new case
									if obj.tagsync and labels:
										tags += ',' + ','.join(labels)

									fields = ['sTags', 'sProject']
									values = [tags, proj]

									try:
										title = story.getElementsByTagName('name')[0].firstChild.nodeValue
									except IndexError:
										pass
									else:
										fields.append('sTitle')
										values.append(title)

									try:
										desc = story.getElementsByTagName('description')[0].firstChild.nodeValue
									except IndexError:
										pass
									else:
										fields.append('sEvent')
										values.append(desc)

									try:
										stype = story.getElementsByTagName('story_type')[0].firstChild.nodeValue.lower()
									except IndexError:
										pass
									else:
										# Get the corresponding FogBugz category of the Tracker type stype
										category = None
										for ln in obj.mapping.splitlines():
											t = ln.partition('=')
											if t[2].strip().lower() == stype:
												category = t[0].strip()
												break

										# stype is either 'bug', 'feature', 'chore' or 'release'
										if category is None:
											if stype == 'release':
												category = 'Schedule Item'
											else:
												category = stype

										fields.append('sCategory')
										values.append(category)

									try:
										assigned_to = story.getElementsByTagName('requested_by')[0].firstChild.nodeValue
									except IndexError:
										pass
									else:
										fields.append('sPersonAssignedTo')
										values.append(assigned_to)

									# Now create the case
									case = conn.edit_case(None, fields, values, cmd = 'new')[0]

									# Add a comment to the case to indicate that this is imported from Tracker
									conn.edit_case(case.id, ['sEvent'], ['Story created and imported into FogBugz by ' + author + '.'])

									# Finally, we must link the story in Tracker to the FogBugz case
									headers = {}
									headers['X-TrackerToken'] = obj.pttoken
									headers['Content-Type'] = 'application/xml'
									data = '<story><other_id>%s</other_id><integration_id>%s</integration_id></story>' % (case.id, obj.ptintid)
									urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, ptid), payload=data, method='PUT', headers=headers, deadline=10)

						continue

					# If we are here, it means this story is an import from this FogBugz installation
					fbid = story.getElementsByTagName('other_id')[0].firstChild.nodeValue
					entry = Story(fbid)
					entry.ptid = story.getElementsByTagName('id')[0].firstChild.nodeValue
					if type == 'story_create':
						entries.append(entry)
					elif type == 'story_delete':
						entry.state = 'accepted'
						entries.append(entry)
					else:
						# Only record title changes, category changes, status changes, label changes and new notes
						changed = False
						try:
							entry.title = story.getElementsByTagName('name')[0].firstChild.nodeValue
						except:
							pass
						else:
							changed = True

						try:
							entry.stype = story.getElementsByTagName('story_type')[0].firstChild.nodeValue.lower()
						except:
							pass
						else:
							changed = True

						try:
							entry.state = story.getElementsByTagName('current_state')[0].firstChild.nodeValue.lower()
						except:
							pass
						else:
							changed = True

						if obj.tagsync:
							try:
								entry.labels = story.getElementsByTagName('labels')[0].firstChild.nodeValue
							except:
								pass
							else:
								changed = True

						try:
							notes = story.getElementsByTagName('notes')[0]
							for note in notes.childNodes:
								if note.nodeName == 'note':
									entry.notes.append(note.getElementsByTagName('text')[0].firstChild.nodeValue)
						except:
							pass
						else:
							changed = True

						if changed:
							entries.append(entry)
			except:
				pass

		if entries:
			# At least one of the listed stories is an import from FogBugz, and more operations are needed
			if conn is None:
				conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken)

			for entry in entries:
				if type == 'story_create':
					# A new story has just been created (by importing an existing case from FogBugz)
					# First, get all tags and a list of all existing events of the FogBugz case
					case = conn.list_cases(entry.fbid, 'ixBug,tags,events')[0]

					# Second, add a tag in the corresponding FogBugz case to link to the story in Tracker,
					case.tags.insert(0, 'ts@%s-%s' % (proj_id, entry.ptid))
					fields = ['tags', 'sEvent']
					values = [','.join(case.tags), 'Case imported into Pivotal Tracker by ' + author + '.']
					conn.edit_case(entry.fbid, fields, values)

					# Finally, add all existing events in this FogBugz case into Tracker as comments on this story
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

						urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (proj_id, entry.ptid), payload=data, method='POST', headers=headers, deadline=10)
				else:
					# A story has just been edited, currently we only propogate title changes, category changes, status
					# changes, label changes and new notes/comments to FogBugz

					# If multiple actions are performed at once, we first create a Fogbugz case event for each note/comment
					# included, and finally create another case event for all other changes (if any), including title,
					# category, status and label changes. We feel it makes more sense this way (e.g. comments on why an
					# action is performed appear before the action itself), and it also saves some work.

					# An instance of Case that contains information we need for certain operations
					case = None

					# Each new note is sent in its own edit request
					if entry.notes:
						# A new comment has just been created, add it to FogBugz as a case event
						for i in range(len(entry.notes)):
							if case is None:
								case = conn.edit_case(entry.fbid, ['sEvent'], ['Comment posted by ' + author + ' in Pivotal Tracker:\n\n' + entry.notes[i]], 'ixBug,tags,ixCategory,sCategory')[0]
							else:
								conn.edit_case(entry.fbid, ['sEvent'], ['Comment posted by ' + author + ' in Pivotal Tracker:\n\n' + entry.notes[i]])

					# Title and status changes are incorporated in a single edit request
					fields = []
					values = []

					if entry.title is not None:
						fields.append('sTitle')
						values.append(entry.title)

					if entry.stype is not None:
						# Get the corresponding FogBugz category of the Tracker type entry.stype
						category = None
						for ln in obj.mapping.splitlines():
							t = ln.partition('=')
							if t[2].strip().lower() == entry.stype:
								category = t[0].strip()
								break

						# entry.stype is either 'bug', 'feature', 'chore' or 'release'
						if category is None:
							if entry.stype == 'release':
								category = 'Schedule Item'
							else:
								category = entry.stype

						fields.append('sCategory')
						values.append(category)

					if entry.labels is not None:
						fields.append('sTags')
						values.append('ts@%s-%s,%s' % (proj_id, entry.ptid, entry.labels))

					# Status changes are tricky, as there are restrictions on which status can be changed to which status,
					# while no such restrictions exist in Tracker.
					extra = False
					if entry.state in ('started', 'finished', 'accepted'):
						# We need to know the current status of the FogBugz case to decide which command to use
						if case is None:
							case = conn.list_cases(entry.fbid, 'ixBug,tags,ixCategory,sCategory')[0]

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
								# This one is especially tricky as we must find out the proper status to resolve to
								cmd = 'resolve'

								# There are two scenarios where we need to resolve a case in FogBugz: either its counterpart
								# in Tracker is finished/accepted, or it's deleted. In the former case, the user can specify
								# the status to resolve to, or if not specified, the default resolve status is used; in the
								# latter case, a simple algorithm is used to determine the resolve status.
								status = None
								if type != 'story_delete':
									# We try to find the status to resolve to in configuration
									for line in obj.resolve.splitlines():
										t = line.partition(':')
										if t[0].strip().lower() == case.category_name.lower():
											status = t[2].strip()
											break
								else:
									# First fetch all resolved statuses of this category from FogBugz
									statuses = conn.list_statuses(case.category_id, True)

									# Now choose the "best" status in the list to use.
									# The criteria is to prefer statuses that are "deleted", a "duplicate", not "work done",
									# and order lowly, in this order.
									t = None
									for i in range(len(statuses)):
										s = (statuses[i].is_deleted, statuses[i].is_duplicate, not statuses[i].is_work_done, statuses[i].order, statuses[i].id)
										if t is None or s > t:
											t = s
									status = t[4]

									# Since the story in Tracker is deleted, we also need to remove the special tag in the
									# corresponding FogBugz case.
									modified = False
									for i in range(len(case.tags)-1, -1, -1):
										if case.tags[i][:3] == 'ts@':
											del case.tags[i]
											modified = True

									if modified:
										fields.append('sTags')
										values.append(','.join(case.tags))

								if status is not None:
									# Finally, insert the status into fields
									fields.append('ixStatus')
									values.append(status)

					else:
						cmd = 'edit'

					if fields != [] or cmd != 'edit':
						fields.append('sEvent')
						if type != 'story_delete':
							values.append('By ' + author + ' in Pivotal Tracker.')
						else:
							values.append('Story deleted by ' + author + ' in Pivotal Tracker.')
						conn.edit_case(entry.fbid, fields, values, cmd=cmd)

						if extra:
							# Extra step needed to close the case (after resolving it)
							if type != 'story_delete':
								conn.edit_case(entry.fbid, ['sEvent'], ['By ' + author + ' in Pivotal Tracker.'], cmd='close')
							else:
								conn.edit_case(entry.fbid, ['sEvent'], ['Story deleted by ' + author + ' in Pivotal Tracker.'], cmd='close')

		# If the token has been updated, also update it in the integration object
		if conn:
			if obj.fbtoken != conn.token:
				obj.fbtoken = conn.token
				obj.put()

		self.response.out.write('OK')

# http://fogtracker.appspot.com/<token>/URLTrigger/?CaseNumber={CaseNumber}&CaseEventID={CaseEventID}&EventType={EventType}
# This class receives activity notifications from FogBugz, and updates Tracker accordingly via API
class URLTriggerHandler(webapp.RequestHandler):
	def get(self, token):
		cid = self.request.get('CaseNumber')
		eid = self.request.get('CaseEventID')
		type = self.request.get('EventType')
		if cid and eid and type:
			# A new case event has occured
			# First get the integration object
			obj = Integration.all().filter('token = ', token).get()
			if obj is None:
				self.response.set_status(404)
				return

			# Now fetch all events from that case to get detailed info
			conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken)
			case = conn.list_cases(cid, 'ixBug,ixBugParent,ixBugChildren,sTitle,sCategory,tags,events')[0]

			# We need to check whether the case is already imported into Tracker
			proj_id = None
			tid = None
			for tag in case.tags:
				if tag[:3] == 'ts@':
					t = tag[3:].partition('-')
					proj_id = t[0]
					tid = t[2]
					break
			if tid:
				# The case is already imported into Tracker
				for i in range(len(case.events)-1, -1, -1):
					if case.events[i].id == eid:
						# This is the event we just received
						event = case.events[i]

						# See what changes have been made
						tc = False		# the title was changed
						pe = False		# the first post was edited
						cc = False		# the category was changed
						tar = False		# one or more tags were added or removed

						mo = re.search(r'(?:^|\.\s)Title changed from ', event.changes, re.MULTILINE)
						if mo:
							tc = True

						mo = re.search(r'(?:^|\.\s)Revised.*?from\s([\d/]+)\sat\s([\d:]+)\sUTC', event.changes, re.MULTILINE)
						if mo:
							# A comment is changed in this event
							d = 'T'.join(mo.groups()).replace('/', '-')
							if case.events[0].date.find(d) == 0:
								# The first comment is changed
								pe = True

						mo = re.search(r'(?:^|\.\s)Category changed from ', event.changes, re.MULTILINE)
						if mo:
							cc = True

						if obj.tagsync:
							mo = re.search(r"(?:^|\.\s)(Added|Removed) tag '", event.changes, re.MULTILINE)
							if mo:
								tar = True

						headers = {}
						headers['X-TrackerToken'] = obj.pttoken
						headers['Content-Type'] = 'application/xml'

						if tc or pe or cc or tar or type != 'CaseEdited':
							# We must modify the story (title/description/category/labels/state)
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

							if cc:
								# Get the corresponding Tracker story type from the FogBugz category name
								category = case.category_name.lower()

								stype = None
								for ln in obj.mapping.splitlines():
									t = ln.partition('=')
									if t[0].strip().lower() == category:
										stype = t[2].strip().lower()
										break

								if stype is None:
									if category == 'bug' or category == 'feature':
										stype = category
									elif category == 'schedule item':
										stype = 'release'
									else:
										stype = "chore"

								data += '<story_type>%s</story_type>' % escape(stype)

							if tar:
								# First remove the special tag
								for i in range(len(case.tags)-1, -1, -1):
									if case.tags[i][:3] == 'ts@':
										del case.tags[i]
								data += '<labels>%s</labels>' % escape(','.join(case.tags))

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

							urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, tid), payload=data, method='PUT', headers=headers, deadline=10)

						# Finally add a comment in Tracker to reflect this case event (but only when this event wasn't created as a result of a comment in Tracker)
						if re.match(r'Comment posted by [^\n]* in Pivotal Tracker:\n', event.text) is None:
							data = event.description + ' in FogBugz'
							if event.changes:
								data += '\n' + event.changes
							if event.text:
								data += '\n' + event.text
							data = '<note><text>%s</text></note>' % escape(data)
							urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (proj_id, tid), payload=data, method='POST', headers=headers, deadline=10)

						break

			# If the token has been updated, also update it in the integration object
			if obj.fbtoken != conn.token:
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
