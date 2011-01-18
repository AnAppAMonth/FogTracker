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

from google.appengine.ext import db

# Create your models here.

class Integration(db.Model):
	# Google account under which this integration is created
	account = db.StringProperty(required=True)
	# Token of the integration
	token = db.StringProperty(required=True)
	# Time of creation of the integration
	created = db.DateTimeProperty(required=True)

	# FogBugz base URL and credentials
	fburl = db.StringProperty(required=True)
	fbuser = db.StringProperty(required=True)
	fbpass = db.StringProperty(required=True)
	fbtoken = db.StringProperty(required=False)

	# Tracker token to use
	pttoken = db.StringProperty(required=True)

	# Category mapping and resolve status mapping
	mapping = db.TextProperty(required=False)
	resolve = db.TextProperty(required=False)

	# Whether tags in FogBugz and labels in Tracker are synchronized by the integration
	tagsync = db.BooleanProperty(required=True)

	# Whether a new Tracker story satisfying a certain criteria (has a label of the format fb:proj) should be
	# propagated to FogBugz
	ptprop = db.BooleanProperty(required=True)

	# The integration id in Tracker, required if ptprop is set to True
	ptintid = db.StringProperty(required=False)

	# Current status of the integration (working well or having errors)
	status = db.StringProperty(required=True)
