from google.appengine.ext import db

# Create your models here.

class Integration(db.Model):
	# Google account under which this integration is created
	account = db.StringProperty(required=True)
	# Token of the integration
	token = db.StringProperty(required=True)
	# Time of creation of the integration
	created = db.DateTimeProperty(required=True)
	# Data fields
	fburl = db.StringProperty(required=True)
	fbuser = db.StringProperty(required=True)
	fbpass = db.StringProperty(required=True)
	fbtoken = db.StringProperty(required=False)
	pttoken = db.StringProperty(required=True)
	mapping = db.TextProperty(required=False)
	resolve = db.TextProperty(required=False)
	# Current status of the integration (working well or having errors)
	status = db.StringProperty(required=True)
