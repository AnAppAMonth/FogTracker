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

from pyfogbugz import XmlHandler

class Status(object):
	def __init__(self):
		self.id = None
		self.name = None
		self.category_id = None
		self.is_work_done = None
		self.is_resolved = None
		self.is_duplicate = None
		self.is_deleted = None
		self.order = None

class StatusList(XmlHandler):
	def __init__(self):
		super(StatusList, self).__init__()
		self.statuses = None
		self.current_status = None

	def startElement(self, name, attrs):
		super(StatusList, self).startElement(name, attrs)
		if name == 'statuses':
			self.statuses = []
		elif name == 'status':
			self.current_status = Status()

	def endElement(self, name):
		# Container elements
		if name == 'status' and self.current_status is not None:
			self.statuses.append(self.current_status)
			self.current_status = None
		elif name == 'statuses':
			self.current_status = None

		# Elements of a status
		if self.current_status is not None:
			if name == 'ixStatus':
				self.current_status.id = self.current_value
			elif name == 'sStatus':
				self.current_status.name = self.current_value
			elif name == 'ixCategory':
				self.current_status.category_id = self.current_value
			elif name == 'fWorkDone':
				self.current_status.is_work_done = (self.current_value == 'true')
			elif name == 'fResolved':
				self.current_status.is_resolved = (self.current_value == 'true')
			elif name == 'fDuplicate':
				self.current_status.is_duplicate = (self.current_value == 'true')
			elif name == 'fDeleted':
				self.current_status.is_deleted = (self.current_value == 'true')
			elif name == 'iOrder':
				self.current_status.order = int(self.current_value)

		super(StatusList, self).endElement(name)
