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
