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

import re, random, time, logging
from datetime import datetime
from xml.sax.saxutils import escape
from xml.dom import minidom
from xml.parsers.expat import ExpatError

from google.appengine.ext import webapp
from google.appengine.ext.webapp import util, template
from google.appengine.api import urlfetch, users, taskqueue
from google.appengine.ext import db

from pyfogbugz import connection
from pyfogbugz.exceptions import FogBugzClientError, FogBugzServerError
from model import Integration

def add_task(queue, url, method, payload=None, params=None, countdown=0):
	while True:
		try:
			if payload:
				taskqueue.add(queue_name=queue, url=url, method=method, payload=payload, countdown=countdown)
			elif params:
				taskqueue.add(queue_name=queue, url=url, method=method, params=params, countdown=countdown)
			else:
				taskqueue.add(queue_name=queue, url=url, method=method, countdown=countdown)
		except taskqueue.TransientError:
			logging.exception('TransientError in the Task Queue.')
			countdown += 1
			continue
		else:
			break


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
				token = self.request.get('token')
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
				token = self.request.get('token')

				# Retrieve POST parameters
				fburl = self.request.get('fburl')
				fbuser = self.request.get('fbuser')
				fbpass = self.request.get('fbpass')
				pttoken = self.request.get('pttoken')
				tagsync = self.request.get('tagsync') == 'on'
				ptprop = self.request.get('ptprop') == 'on'
				ptintid = self.request.get('ptintid')
				mapping = self.request.get('mapping')
				resolve = self.request.get('resolve')

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
				if fbpass == '' and not token:
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
								cc = False
								if fburl != entry.fburl:
									entry.fburl = fburl
									cc = True
								if fbuser != entry.fbuser:
									entry.fbuser = fbuser
									cc = True
								if fbpass and fbpass != entry.fbpass:
									entry.fbpass = fbpass
									cc = True
								if cc:
									# If either the url, username, or password has changed, we must get a new token
									entry.fbtoken = None

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
				token = self.request.get('token')
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
		stat = '<span class="ok">OK</span>'

		output = '<?xml version="1.0" encoding="UTF-8"?>\n'
		output += '<external_stories type="array">\n'

		conn = None
		try:
			conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken)

			# This is the query used to specify the cases to include in the feed
			query = self.request.get('q')

			cases = conn.list_cases((query + ' status:active -tag:"ts@*"').encode('utf8'), 'ixBug,ixBugParent,ixBugChildren,sTitle,sPersonAssignedTo,sCategory,dtOpened,events', 500)

			for case in cases:
				output += ' <external_story>\n'
				output += '  <external_id>%s</external_id>\n' % case.id
				output += '  <name>%s</name>\n' % escape(case.title)

				summary = case.events[0].text
				if case.parent_case > '0':
					summary = 'Parent Case: %s/default.asp?%s\n\n' % (obj.fburl, case.parent_case) + summary
				if case.child_cases:
					summary += '\n\nChild Cases:'
					for cc in case.child_cases.split(','):
						summary += '\n%s/default.asp?' % obj.fburl + cc
				output += '  <description>%s</description>\n' % escape(summary)

				output += '  <requested_by>%s</requested_by>\n' % escape(case.assigned_to_name)
				output += '  <created_at type="datetime">%s</created_at>\n' % case.date_opened.replace('T', ' ').replace('Z', ' UTC')

				# Get the corresponding Tracker story type from the FogBugz category name
				category = case.category_name.lower()

				stype = None
				for ln in obj.mapping.splitlines():
					t = ln.partition('=')
					if t[0].strip().lower() in (category, '*') and t[2].strip() != '*':
						stype = t[2].strip().lower()
						break

				if stype is None:
					if category == 'bug' or category == 'feature':
						stype = category
					else:
						stype = 'chore'

				output += '  <story_type>%s</story_type>\n' % escape(stype)

#				if obj.tagsync and case.tags:
#					output += '  <labels>%s</labels>\n' % escape(','.join(case.tags))

				output += ' </external_story>\n'
		except (FogBugzClientError, FogBugzServerError), e:
			logging.exception(str(e))
			stat = '<span class="error">Error</span>'

		output += '</external_stories>\n'

		# If the token has been updated, also update it in the integration object
		if (conn and obj.fbtoken != conn.token) or obj.status != stat:
			if conn:
				obj.fbtoken = conn.token
			obj.status = stat
			obj.put()

		self.response.headers.add_header("Content-Type", 'text/xml')
		self.response.out.write(output.encode('utf8'))

class Story(object):
	def __init__(self, fbid, ptid):
		self.fbid = fbid
		self.ptid = ptid

		# These changes are propagated to FogBugz
		self.title = None
		self.stype = None
		self.notes = []

		# This change is propagated to FogBugz if there is an equivalent status there, otherwise it's notified in FogBugz
		self.state = None

		# This change is propagated to FogBugz if enabled in options, otherwise it's notified in FogBugz
		self.labels = None

		# These changes are notified in FogBugz
		self.description = None
		self.estimate = None
		self.owner = None
		self.requester = None

# This class receives activity notifications from Tracker, and updates FogBugz accordingly via API
class WebHookHandler(webapp.RequestHandler):
	def post(self, token, go):
		if go != 'go':
			# A new activity has occured, we will process it in an offline task (for the longer processing time available)
			random.seed(token)
			x = random.randint(1, 10)
			add_task('queue%s' % x, '/%s/WebHook/go' % token, 'POST', payload = self.request.body)
		else:
			# We are in an offline task, or the client asked us to do the processing online. Either case, do the processing.
			# First check whether we are in an offline task or not, if so we can use a longer deadline in urlfetch calls.
			offline = 'X-AppEngine-QueueName' in self.request.headers
			if offline:
				deadline = 60
			else:
				deadline = 10

			# Get the integration object
			obj = Integration.all().filter('token = ', token).get()
			if obj is None:
				self.response.set_status(404)
				return
			stat = '<span class="ok">OK</span>'

			conn = None

			# We must parse the XML no matter what, because any type of event can contain a note/comment in it
			dom = minidom.parseString(self.request.body)
			type = dom.getElementsByTagName('event_type')[0].firstChild.nodeValue
			proj_id = dom.getElementsByTagName('project_id')[0].firstChild.nodeValue
			# We put the author of the activity into the event text to indicate who did this.
			try:
				author = dom.getElementsByTagName('author')[0].firstChild.nodeValue
			except IndexError:
				author = 'Unknown User'
			stories = dom.getElementsByTagName('stories')[0]
			entries = []
			for story in stories.childNodes:
				try:
					if story.nodeName == 'story':
						# First check whether this story is an import from the FogBugz installation specified in this
						# integration profile.

						# Unfortunately, Tracker no longer puts the integration_id, other_id and other_url fields in the
						# body of the activity hook request, making it impossible to tell whether this is an external
						# story or not. Therefore, we now have to make another request to fetch the story. However, this
						# only works if the story still exists, and if not (e.g. this is a story_delete event), we have
						# to search The FogBugz installation to get the linked case there if existed.
						full_story = story
						ptid = story.getElementsByTagName('id')[0].firstChild.nodeValue

						if type != 'story_delete':
							headers = {}
							headers['X-TrackerToken'] = obj.pttoken
							retries = 0
							while retries <= 2:
								resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, ptid), method='GET', headers=headers, deadline=deadline)
								if resp.status_code >= 300:
									logging.exception('URLFetch returned with HTTP %s:\n%s' % (resp.status_code, resp.content))
									stat = '<span class="error">Error</span>'

									# If this is a server error, we retry the request up to 2 times
									if resp.status_code >= 500:
										retries += 1
										# Wait a couple seconds before another attempt
										if offline:
											time.sleep(retries*2)
										else:
											time.sleep(1)
										continue
								else:
									try:
										rdom = minidom.parseString(resp.content)
										full_story = rdom.getElementsByTagName('story')[0]
									except (ExpatError, IndexError), e:
										logging.exception(str(e))
										stat = '<span class="error">Error</span>'
								break

						fbid = None
						if full_story == story:
							# Search in the FogBugz installation
							if conn is None:
								conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken, offline=offline)

							cases = conn.list_cases('tag:"ts@%s-%s"' % (proj_id, ptid), 'ixBug')
							if cases:
								fbid = cases[0].id


						if fbid:
							# We already know that this story is an import from this FogBugz installation, no further
							# checking necessary
							pass
						elif full_story.getElementsByTagName('integration_id'):
							# This story is an import, check the source
							try:
								url = full_story.getElementsByTagName('other_url')[0].firstChild.nodeValue.partition('://')[2]
								fburl = obj.fburl.partition('://')[2]
								if url.find(fburl) != 0:
									# This story was not imported from this FogBugz installation, nothing needs to be done
									continue
							except IndexError:
								# This story is under another kind of integration
								continue
						else:
							# We want to play the safety card here, if we failed to fetch the full story, we cannot be sure
							# whether it's already an external story or not.
							if full_story == story:
								continue

							# This story isn't an import from any source, check its labels if obj.ptprop is True
							if obj.ptprop:
								labels = story.getElementsByTagName('labels')
								if labels:
									labels = labels[0].firstChild.nodeValue.split(',')
									proj = None
									for i in range(len(labels)-1, -1, -1):
										if labels[i][:3] == 'fb:':
											proj = labels[i][3:]
											del labels[i]

									if proj:
										# We should propagate the story to FogBugz
										tags = 'ts@%s-%s' % (proj_id, ptid)

										# If tagsync is True, add the labels as tags to the new case
										if obj.tagsync and labels:
											tags += ',' + ','.join(labels)

										fields = ['sTags', 'sProject']
										values = [tags.encode('utf8'), proj.encode('utf8')]

										try:
											title = full_story.getElementsByTagName('name')[0].firstChild.nodeValue
										except IndexError:
											pass
										else:
											fields.append('sTitle')
											values.append(title.encode('utf8'))

										try:
											desc = full_story.getElementsByTagName('description')[0].firstChild.nodeValue
										except IndexError:
											pass
										else:
											fields.append('sEvent')
											values.append(desc.encode('utf8'))

										try:
											assigned_to = full_story.getElementsByTagName('requested_by')[0].firstChild.nodeValue
										except IndexError:
											pass
										else:
											fields.append('sPersonAssignedTo')
											values.append(assigned_to.encode('utf8'))

										try:
											stype = full_story.getElementsByTagName('story_type')[0].firstChild.nodeValue.lower()
										except IndexError:
											pass
										else:
											# Get the corresponding FogBugz category of the Tracker type stype
											category = None
											for ln in obj.mapping.splitlines():
												t = ln.partition('=')
												if t[2].strip().lower() in (stype, '*') and t[0].strip() != '*':
													category = t[0].strip()
													break

											# stype is either 'bug', 'feature', 'chore' or 'release'
											if category is None:
												if stype == 'release':
													category = 'Schedule Item'
												else:
													category = stype

											fields.append('sCategory')
											values.append(category.encode('utf8'))

										# Now create the case
										try:
											if conn is None:
												conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken, offline=offline)

											case = conn.edit_case(None, fields, values, cmd = 'new')[0]

											# We must link the story in Tracker to the FogBugz case
											headers = {}
											headers['X-TrackerToken'] = obj.pttoken
											headers['Content-Type'] = 'application/xml'
											data = '<story><other_id>%s</other_id><integration_id>%s</integration_id></story>' % (case.id, obj.ptintid)
											retries = 0
											while retries <= 2:
												resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, ptid), payload=data, method='PUT', headers=headers, deadline=deadline)
												if resp.status_code >= 300:
													logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data))
													stat = '<span class="error">Error</span>'

													# If this is a server error, we retry the request up to 2 times
													if resp.status_code >= 500:
														retries += 1
														# Wait a couple seconds before another attempt
														if offline:
															time.sleep(retries*2)
														else:
															time.sleep(1)
														continue
												break

											# Create a case event for each note/comment in the Tracker story
											notes = full_story.getElementsByTagName('notes')
											if notes:
												for note in notes[0].childNodes:
													if note.nodeName == 'note':
														dt = note.getElementsByTagName('text')[0].firstChild.nodeValue
														au = note.getElementsByTagName('author')[0].firstChild.nodeValue
														tm = note.getElementsByTagName('noted_at')[0].firstChild.nodeValue
														conn.edit_case(case.id, ['sEvent'], [('A comment was posted by ' + au + ' in Pivotal Tracker at ' + tm + ':\n' + dt).encode('utf8')])

											# Finally add a comment to the case to indicate that this is imported from Tracker
											conn.edit_case(case.id, ['sEvent'], [('This case has been created by ' + author + ' from the following Pivotal Tracker story:\nhttps://www.pivotaltracker.com/story/show/%s' % ptid).encode('utf8')])

											# And add a comment to the story to indicate that it has been imported into FogBugz
											data = 'A FogBugz case has been created by ' + author + ' for this story:\n%s/default.asp?%s' % (obj.fburl, case.id)
											data = '<note><text>%s</text></note>' % escape(data)

											retries = 0
											while retries <= 2:
												resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (proj_id, ptid), payload=data.encode('utf8'), method='POST', headers=headers, deadline=deadline)
												if resp.status_code >= 300:
													logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data.encode('utf8')))
													stat = '<span class="error">Error</span>'

													# If this is a server error, we retry the request up to 2 times
													if resp.status_code >= 500:
														retries += 1
														# Wait a couple seconds before another attempt
														if offline:
															time.sleep(retries*2)
														else:
															time.sleep(1)
														continue
												break

										except (FogBugzClientError, FogBugzServerError), e:
											logging.exception(str(e))
											stat = '<span class="error">Error</span>'

							continue

						# If we are here, it means this story is an import from this FogBugz installation
						if not fbid:
							fbid = full_story.getElementsByTagName('other_id')[0].firstChild.nodeValue
						entry = Story(fbid, ptid)
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
							except IndexError:
								pass
							else:
								changed = True

							try:
								entry.stype = story.getElementsByTagName('story_type')[0].firstChild.nodeValue.lower()
							except IndexError:
								pass
							else:
								changed = True

							try:
								entry.state = story.getElementsByTagName('current_state')[0].firstChild.nodeValue.lower()
							except IndexError:
								pass
							else:
								changed = True

							try:
								entry.labels = story.getElementsByTagName('labels')[0].firstChild.nodeValue
							except IndexError:
								pass
							else:
								changed = True

							try:
								notes = story.getElementsByTagName('notes')[0]
								for note in notes.childNodes:
									if note.nodeName == 'note':
										data = note.getElementsByTagName('text')[0].firstChild.nodeValue
										# Only propagate the note to FogBugz if it's not itself propagated from there
										if re.match(r'[^\n]* in FogBugz at [\d\-:\s]* UTC(\n|$)|(A FogBugz case has been created by [^\n]* for this story|This story has been imported by [^\n]* from the following FogBugz case):\n', data) is None:
											entry.notes.append(data)
							except IndexError:
								pass
							if entry.notes:
								changed = True

							if story.getElementsByTagName('description'):
								entry.description = True
								changed = True

							try:
								entry.estimate = story.getElementsByTagName('estimate')[0].firstChild.nodeValue
							except IndexError:
								pass
							else:
								changed = True

							try:
								entry.owner = story.getElementsByTagName('owned_by')[0].firstChild.nodeValue
							except IndexError:
								pass
							else:
								if entry.owner == '':
									entry.owner = 'Nobody'
								changed = True

							try:
								entry.requester = story.getElementsByTagName('requested_by')[0].firstChild.nodeValue
							except IndexError:
								pass
							else:
								if entry.requester:
									changed = True
								else:
									entry.requester = None

							if changed:
								entries.append(entry)
				except:
					pass

			if entries:
				# At least one of the listed stories is an import from FogBugz, and more operations are needed
				if conn is None:
					try:
						conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken, offline=offline)
					except (FogBugzClientError, FogBugzServerError), e:
						logging.exception(str(e))
						obj.status = '<span class="error">Error</span>'
						obj.put()
						return self.response.out.write('OK')

				for entry in entries:
					if type == 'story_create':
						# A new story has just been created (by importing an existing case from FogBugz)
						try:
							# First, get all tags and a list of all existing events of the FogBugz case
							case = conn.list_cases(entry.fbid, 'ixBug,tags,events')[0]

							# Second, if tagsync is checked, propagate the tags to the new Tracker story
							headers = {}
							headers['X-TrackerToken'] = obj.pttoken
							headers['Content-Type'] = 'application/xml'
							if obj.tagsync and case.tags:
								data = '<story><labels>%s</labels></story>' % escape(','.join(case.tags))
								retries = 0
								while retries <= 2:
									resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, entry.ptid), payload=data.encode('utf8'), method='PUT', headers=headers, deadline=deadline)
									if resp.status_code >= 300:
										logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data.encode('utf8')))
										stat = '<span class="error">Error</span>'

										# If this is a server error, we retry the request up to 2 times
										if resp.status_code >= 500:
											retries += 1
											# Wait a couple seconds before another attempt
											if offline:
												time.sleep(retries*2)
											else:
												time.sleep(1)
											continue
									break

							# Third, add all existing events in this FogBugz case into Tracker as comments on this story
							first = True
							for event in case.events:
								data = event.description + ' in FogBugz at ' + event.date.replace('T', ' ')[:-4] + ' UTC'
								if event.changes:
									data += '\n' + event.changes
								if event.text and not first:
									data += '\n' + event.text
								data = '<note><text>%s</text></note>' % escape(data)

								retries = 0
								while retries <= 2:
									resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (proj_id, entry.ptid), payload=data.encode('utf8'), method='POST', headers=headers, deadline=deadline)
									if resp.status_code >= 300:
										logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data.encode('utf8')))
										stat = '<span class="error">Error</span>'

										# If this is a server error, we retry the request up to 2 times
										if resp.status_code >= 500:
											retries += 1
											# Wait a couple seconds before another attempt
											if offline:
												time.sleep(retries*2)
											else:
												time.sleep(1)
											continue
									break

								first = False

							# Finally, add a tag in this FogBugz case to link to the story in Tracker
							case.tags.insert(0, 'ts@%s-%s' % (proj_id, entry.ptid))
							fields = ['sTags', 'sEvent']
							values = [','.join(case.tags).encode('utf8'), ('A Pivotal Tracker story has been created by ' + author + ' for this case:\nhttps://www.pivotaltracker.com/story/show/%s' % entry.ptid).encode('utf8')]
							conn.edit_case(entry.fbid, fields, values)

							# And add a comment to the Tracker story to indicate that it's imported from FogBugz
							data = 'This story has been imported by ' + author + ' from the following FogBugz case:\n%s/default.asp?%s' % (obj.fburl, case.id)
							data = '<note><text>%s</text></note>' % escape(data)

							retries = 0
							while retries <= 2:
								resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (proj_id, entry.ptid), payload=data.encode('utf8'), method='POST', headers=headers, deadline=deadline)
								if resp.status_code >= 300:
									logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data.encode('utf8')))
									stat = '<span class="error">Error</span>'

									# If this is a server error, we retry the request up to 2 times
									if resp.status_code >= 500:
										retries += 1
										# Wait a couple seconds before another attempt
										if offline:
											time.sleep(retries*2)
										else:
											time.sleep(1)
										continue
								break

						except (FogBugzClientError, FogBugzServerError), e:
							logging.exception(str(e))
							stat = '<span class="error">Error</span>'
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
						for note in entry.notes:
							# A new comment has just been created, add it to FogBugz as a case event
							try:
								if case is None:
									case = conn.edit_case(entry.fbid, ['sEvent'], [('A comment has been posted by ' + author + ' in Pivotal Tracker:\n' + note).encode('utf8')], 'ixBug,tags,ixCategory,sCategory,sTitle')[0]
								else:
									conn.edit_case(entry.fbid, ['sEvent'], [('A comment has been posted by ' + author + ' in Pivotal Tracker:\n' + note).encode('utf8')])
							except (FogBugzClientError, FogBugzServerError), e:
								logging.exception(str(e))
								stat = '<span class="error">Error</span>'

						# Title, category, status and label changes are incorporated into a single edit request
						fields = []
						values = []
						evtText = []

						try:
							# To avoid propagating changes from FogBugz back to FogBugz (and therefore creating useless empty
							# case events), we check the target FogBugz case to see if a change has really been made.
							if case is None:
								case = conn.list_cases(entry.fbid, 'ixBug,tags,ixCategory,sCategory,sTitle')[0]

							if entry.title is not None and entry.title != case.title:
								fields.append('sTitle')
								values.append(entry.title.encode('utf8'))

							if entry.stype is not None:
								# This one is tricky, as category A -> stype B !== stype B -> category A
								# We first get the corresponding Tracker type of the FogBugz category case.category_name
								category = case.category_name.lower()

								stype = None
								for ln in obj.mapping.splitlines():
									t = ln.partition('=')
									if t[0].strip().lower() in (category, '*') and t[2].strip() != '*':
										stype = t[2].strip().lower()
										break

								if stype is None:
									if category == 'bug' or category == 'feature':
										stype = category
									else:
										stype = 'chore'

								if stype != entry.stype:
									# The stype change was not made by FogTracker, propagation to FogBugz is needed
									# Get the corresponding FogBugz category of the Tracker type entry.stype
									category = None
									for ln in obj.mapping.splitlines():
										t = ln.partition('=')
										if t[2].strip().lower() in (entry.stype, '*') and t[0].strip() != '*':
											category = t[0].strip()
											break

									# entry.stype is either 'bug', 'feature', 'chore' or 'release'
									if category is None:
										if entry.stype == 'release':
											category = 'Schedule Item'
										else:
											category = entry.stype

									if category.lower() != case.category_name.lower():
										fields.append('sCategory')
										values.append(category.encode('utf8'))

							if entry.labels is not None:
								for i in range(len(case.tags)-1, -1, -1):
									if case.tags[i][:3] == 'ts@':
										del case.tags[i]
									else:
										case.tags[i] = case.tags[i].lower()
								case.tags.sort()

								labels = entry.labels.split(',')
								modified = False
								for i in range(len(labels)-1, -1, -1):
									if labels[i][:3] == 'fb:':
										del labels[i]
										modified = True
								if modified:
									entry.labels = ','.join(labels)

								if entry.labels.lower() != ','.join(case.tags):
									if obj.tagsync:
										fields.append('sTags')
										if entry.labels:
											values.append(('ts@%s-%s,%s' % (proj_id, entry.ptid, entry.labels)).encode('utf8'))
										else:
											values.append('ts@%s-%s' % (proj_id, entry.ptid))
									else:
										evtText.append('\tLabels changed to ' + entry.labels + '.')

							# Status changes are tricky, as there are restrictions on which status can be changed to which status,
							# while no such restrictions exist in Tracker.
							cmd = 'edit'
							extra = False
							if entry.state in ('unstarted', 'started', 'finished', 'accepted'):
								# We need to know the current status of the FogBugz case to decide which command to use
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

									if type == 'story_delete':
										# Since the story in Tracker is deleted, we need to remove the special tag in the
										# corresponding FogBugz case.
										modified = False
										for i in range(len(case.tags)-1, -1, -1):
											if case.tags[i][:3] == 'ts@':
												del case.tags[i]
												modified = True

										if modified:
											fields.append('sTags')
											values.append(','.join(case.tags).encode('utf8'))

								if entry.state == 'unstarted' or entry.state == 'started':
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
										# This one is especially tricky as we must decide the proper status to resolve to
										cmd = 'resolve'

										# There are two scenarios where we need to resolve a case in FogBugz: either its counterpart
										# in Tracker is finished/accepted, or it's deleted. In the former case, the user can specify
										# the status to resolve to, or if not specified, the default resolve status is used; in the
										# latter case, a simple algorithm is used to determine the resolve status.
										status = None
										if type != 'story_delete':
											# We try to find the status to resolve to in configuration, and if failed, the
											# default resolve status will be used
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
											for status in statuses:
												s = (status.is_deleted, status.is_duplicate, not status.is_work_done, status.order, status.id)
												if t is None or s > t:
													t = s
											status = t[4]

										if status is not None:
											# Finally, insert the status into fields
											fields.append('ixStatus')
											values.append(status)

						except (FogBugzClientError, FogBugzServerError), e:
							logging.exception(str(e))
							stat = '<span class="error">Error</span>'

						if entry.state is not None and cmd == 'edit':
							evtText.append('\tState changed to %s.' % entry.state)

						if entry.estimate is not None:
							if entry.estimate == '-1':
								evtText.append('\tEstimate changed to Unestimated.')
							else:
								evtText.append('\tEstimate changed to %s.' % entry.estimate)

						if entry.owner is not None:
							evtText.append('\tOwner changed to %s.' % entry.owner)

						if entry.requester is not None:
							evtText.append('\tRequester changed to %s.' % entry.requester)

						if entry.description is not None:
							evtText.append('\tStory description is changed.')

						if fields or cmd != 'edit' or evtText:
							if type != 'story_delete':
								evtText.append('By ' + author + ' in Pivotal Tracker.')
							else:
								evtText.append('Story deleted by ' + author + ' in Pivotal Tracker.')

							fields.append('sEvent')
							values.append('\n'.join(evtText).encode('utf8'))
							try:
								conn.edit_case(entry.fbid, fields, values, cmd=cmd)
							except (FogBugzClientError, FogBugzServerError), e:
								logging.exception(str(e))
								stat = '<span class="error">Error</span>'

							if extra:
								# Extra step needed to close the case (after resolving it)
								try:
									if type != 'story_delete':
										conn.edit_case(entry.fbid, ['sEvent'], [('By ' + author + ' in Pivotal Tracker.').encode('utf8')], cmd='close')
									else:
										conn.edit_case(entry.fbid, ['sEvent'], [('Story deleted by ' + author + ' in Pivotal Tracker.').encode('utf8')], cmd='close')
								except (FogBugzClientError, FogBugzServerError), e:
									logging.exception(str(e))
									stat = '<span class="error">Error</span>'

			# If the token has been updated, also update it in the integration object
			if (conn and obj.fbtoken != conn.token) or obj.status != stat:
				if conn:
					obj.fbtoken = conn.token
				obj.status = stat
				obj.put()

		self.response.out.write('OK')

# http://fogtracker.appspot.com/<token>/URLTrigger/?CaseNumber={CaseNumber}&CaseEventID={CaseEventID}&EventType={EventType}
# This class receives activity notifications from FogBugz, and updates Tracker accordingly via API
class URLTriggerHandler(webapp.RequestHandler):
	def get(self, token, go):
		cid = self.request.get('CaseNumber')
		eid = self.request.get('CaseEventID')
		type = self.request.get('EventType')
		if cid and eid and type:
			if go != 'go':
				# A new case event has occured, we will process it in an offline task (for the longer processing time available)
				random.seed(token)
				x = random.randint(1, 10)
				add_task('queue%s' % x, '/%s/URLTrigger/go' % token, 'GET', params = {'CaseNumber':cid, 'CaseEventID':eid, 'EventType':type})
			else:
				# We are in an offline task, or the client asked us to do the processing online. Either case, do the processing.
				# First check whether we are in an offline task or not, if so we can use a longer deadline in urlfetch calls.
				offline = 'X-AppEngine-QueueName' in self.request.headers
				if offline:
					deadline = 60
				else:
					deadline = 10

				# Get the integration object
				obj = Integration.all().filter('token = ', token).get()
				if obj is None:
					self.response.set_status(404)
					return
				stat = '<span class="ok">OK</span>'

				conn = None
				try:
					# Fetch all events from that case to get detailed info
					conn = connection.FogBugzConnection(obj.fburl, obj.fbuser, obj.fbpass, obj.fbtoken, offline=offline)

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
					if proj_id and tid:
						# The case is already imported into Tracker
						for i in range(len(case.events)-1, -1, -1):
							if case.events[i].id == eid:
								# This is the event we just received
								event = case.events[i]

								# If this event was created as a result of propagating changes/notes from Tracker to FogBugz,
								# we obviously shouldn't propagate these changes back.
								if re.search(r'^By [^\n]* in Pivotal Tracker\.$', event.text, re.MULTILINE):
									break
								elif re.match(r'(A comment (was|has been) posted by [^\n]* in Pivotal Tracker( at [^\n]*)?|(This case|A Pivotal Tracker story) has been created by [^\n]* (from the following Pivotal Tracker story|for this case)):\n', event.text):
									break

								# See what changes have been made
								tc = False		# the title was changed
								pe = False		# the first post was edited
								cc = False		# the category was changed
								tar = False		# one or more tags were added or removed

								mo = re.search(r'(?:^|\.\s+)Title changed from ', event.changes, re.MULTILINE)
								if mo:
									tc = True

								mo = re.search(r'(?:^|\.\s+)Revised.*?from\s([\d/]+)\sat\s([\d:]+)\sUTC', event.changes, re.MULTILINE)
								if mo:
									# A comment is changed in this event
									d = mo.group(1).split('/')
									t = mo.group(2).split(':')
									s = '%s-%02d-%02dT%02d:%02d' % (d[0], int(d[1]), int(d[2]), int(t[0]), int(t[1]))
									if case.events[0].date.find(s) == 0:
										# The first comment is changed
										pe = True

								# If the parent or children of the case have changed, the effect is the same as a change
								# to the first comment: we have to update the description of the corresponding story.
								mo = re.search(r'(?:^|\.\s+)(Parent changed from|(Added|Removed) subcases?) ', event.changes, re.MULTILINE)
								if mo:
									pe = True

								mo = re.search(r'(?:^|\.\s+)Category changed from ', event.changes, re.MULTILINE)
								if mo:
									cc = True

								if obj.tagsync:
									mo = re.search(r"(?:^|\.\s+)(Added|Removed) tags? '", event.changes, re.MULTILINE)
									if mo:
										tar = True

								headers = {}
								headers['X-TrackerToken'] = obj.pttoken
								headers['Content-Type'] = 'application/xml'

								fetched = False
								if tc or pe or cc or tar:
									# We must modify the story (title/description/category/labels/state)
									data = '<story>'
									if tc:
										data += '<name>%s</name>' % escape(case.title)

									if pe:
										summary = case.events[0].text
										if case.parent_case > '0':
											summary = 'Parent Case: %s/default.asp?%s\n\n' % (obj.fburl, case.parent_case) + summary
										if case.child_cases:
											summary += '\n\nChild Cases:'
											for cc in case.child_cases.split(','):
												summary += '\n%s/default.asp?' % obj.fburl + cc
										data += '<description>%s</description>' % escape(summary)

									if cc:
										# Get the corresponding Tracker story type from the FogBugz category name
										category = case.category_name.lower()

										stype = None
										for ln in obj.mapping.splitlines():
											t = ln.partition('=')
											if t[0].strip().lower() in (category, '*') and t[2].strip() != '*':
												stype = t[2].strip().lower()
												break

										if stype is None:
											if category == 'bug' or category == 'feature':
												stype = category
											else:
												stype = "chore"

										data += '<story_type>%s</story_type>' % escape(stype)

									if tar:
										# First remove the special tag
										for i in range(len(case.tags)-1, -1, -1):
											if case.tags[i][:3] == 'ts@':
												del case.tags[i]
										data += '<labels>%s</labels>' % escape(','.join(case.tags))

									data += '</story>'

									retries = 0
									while retries <= 2:
										resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, tid), payload=data.encode('utf8'), method='PUT', headers=headers, deadline=deadline)
										if resp.status_code >= 300:
											logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data.encode('utf8')))
											stat = '<span class="error">Error</span>'

											# If this is a server error, we retry the request up to 2 times
											if resp.status_code >= 500:
												retries += 1
												# Wait a couple seconds before another attempt
												if offline:
													time.sleep(retries*2)
												else:
													time.sleep(1)
												continue
										else:
											fetched = True
										break

								# We use a separate request for state changes to isolate errors. The most frequently used
								# commands here (resolve and close) requires an extra fetch of the story anyway, so in most
								# cases this doesn't cause an increase in the total number of requests.
								if type != 'CaseEdited':
									ne = False
									if type in ('CaseResolved', 'CaseClosed'):
										# We must fetch the story type and estimate from Tracker. If failed, we take the
										# safe road and assume the type is "chore"
										stype = 'chore'
										estimate = '1'
										if not fetched:
											headers2 = {}
											headers2['X-TrackerToken'] = obj.pttoken
											retries = 0
											while retries <= 2:
												resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, tid), method='GET', headers=headers2, deadline=deadline)
												if resp.status_code >= 300:
													logging.exception('URLFetch returned with HTTP %s:\n%s' % (resp.status_code, resp.content))
													stat = '<span class="error">Error</span>'

													# If this is a server error, we retry the request up to 2 times
													if resp.status_code >= 500:
														retries += 1
														# Wait a couple seconds before another attempt
														if offline:
															time.sleep(retries*2)
														else:
															time.sleep(1)
														continue
												else:
													fetched = True
												break

										if fetched:
											try:
												rdom = minidom.parseString(resp.content)
												full_story = rdom.getElementsByTagName('story')[0]
												stype = full_story.getElementsByTagName('story_type')[0].firstChild.nodeValue.lower()
												if stype == 'feature':
													estimate = full_story.getElementsByTagName('estimate')[0].firstChild.nodeValue
												elif stype != 'release':
													# estimates may or may not be allowed
													try:
														estimate = full_story.getElementsByTagName('estimate')[0].firstChild.nodeValue
													except IndexError:
														# estimates are probably not allowed
														estimate = None
											except (ExpatError, IndexError), e:
												logging.exception(str(e))
												stat = '<span class="error">Error</span>'

										if type == 'CaseResolved':
											# We should finish the story in Tracker. However, Tracker stories of type "chore"
											# or "release" don't have the "finished" state, and thus we use "accepted" instead.
											if stype in ('bug', 'feature'):
												data = '<current_state>finished</current_state>'
											else:
												data = '<current_state>accepted</current_state>'
										else:
											# Accept the story in Tracker
											data = '<current_state>accepted</current_state>'

										if stype != 'release':
											# An estimate is only required/allowed for story types other than "release"
											if estimate == '-1':
												data += '<estimate>1</estimate>'
											elif estimate is not None:
												# We might need to add the estimate field later if an error is encountered
												ne = True

									elif type == 'CaseReactivated' or type == 'CaseReopened':
										# Unstart the story in Tracker
										data = '<current_state>unstarted</current_state>'
									else:
										data = ''

									if data:
										data = '<story>' + data
										retries = 0
										while retries <= 2:
											resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s' % (proj_id, tid), payload=data + '</story>', method='PUT', headers=headers, deadline=deadline)
											if resp.status_code >= 300:
												logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data + '</story>'))
												stat = '<span class="error">Error</span>'

												# If this is a server error, we retry the request up to 2 times
												if resp.status_code >= 500 or resp.status_code == 422:
													retries += 1
													if retries == 1 and ne:
														# This error probably occured because we tried to change the state of an unestimated story
														data += '<estimate>1</estimate>'
													# Wait a couple seconds before another attempt
													if offline:
														time.sleep(retries*2)
													else:
														time.sleep(1)
													continue
											break

								# Finally add a comment in Tracker to reflect this case event
								data = event.description + ' in FogBugz at ' + event.date.replace('T', ' ')[:-4] + ' UTC'
								if event.changes:
									data += '\n' + event.changes
								if event.text:
									data += '\n' + event.text
								data = '<note><text>%s</text></note>' % escape(data)
								retries = 0
								while retries <= 2:
									resp = urlfetch.fetch('https://www.pivotaltracker.com/services/v3/projects/%s/stories/%s/notes' % (proj_id, tid), payload=data.encode('utf8'), method='POST', headers=headers, deadline=deadline)
									if resp.status_code >= 300:
										logging.exception('URLFetch returned with HTTP %s:\n%s\n\nData Sent:\n%s' % (resp.status_code, resp.content, data.encode('utf8')))
										stat = '<span class="error">Error</span>'

										# If this is a server error, we retry the request up to 2 times
										if resp.status_code >= 500:
											retries += 1
											# Wait a couple seconds before another attempt
											if offline:
												time.sleep(retries*2)
											else:
												time.sleep(1)
											continue
									break

								break

				except (FogBugzClientError, FogBugzServerError), e:
					logging.exception(str(e))
					stat = '<span class="error">Error</span>'

				# If the token has been updated, also update it in the integration object
				if (conn and obj.fbtoken != conn.token) or obj.status != stat:
					if conn:
						obj.fbtoken = conn.token
					obj.status = stat
					obj.put()

		self.response.out.write('OK')

def main():
	# Note the "go" option. It's recommended that you leave it out, and the processing will be done in an offline task
	# (the online request handler will create a task to do the processing and return immediately). This way we have up
	# to 10 minutes to process each request, useful when a lot of work needs to be done (e.g. when a FogBugz case containing
	# a large number of events is imported into Tracker). However, This method also brings with it certain limitations:
	# it requires longer time to process each request, eats up more CPU time, and at most 50 requests can be processed
	# every second (an AppEngine limit). If you find yourself having an edge case where these limitations are significant,
	# and if you believe all your requests can be processed within 30 seconds, you can add a "go" to the Tracker web hook
	# and FogBugz URLTrigger URLs you use to tell FogTracker to process the request directly in the request handler.
	application = webapp.WSGIApplication([(r'/(features|notes|howto|new|edit|delete)?', MainPage),
											(r'/(.+)/CaseFeed/', CaseFeedHandler),
											(r'/(.+)/WebHook/(go)?', WebHookHandler),
											(r'/(.+)/URLTrigger/(go)?', URLTriggerHandler),
											],
										debug=True)
	util.run_wsgi_app(application)


if __name__ == '__main__':
	main()
