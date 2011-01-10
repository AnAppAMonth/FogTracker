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

import sys
from xml.sax.handler import ContentHandler

Version = '0.1'
UserAgent = 'PyFogBugz/%s (%s)' % (Version, sys.platform)

class XmlHandler(object, ContentHandler):
    def __init__(self):
        self.error_code = None
        self.error_message = None
        self.has_error = False
        self.current_value = ''
    def characters(self, content):
        self.current_value += content
    def startElement(self, name, attrs):
        self.current_value = ''
        if name == 'error':
            self.error_code = int(attrs['code'])
            self.has_error = True
    def endElement(self, name):
        if name == 'error':
            self.error_message = self.current_value
        self.current_value = ''
