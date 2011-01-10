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

class Filter(object):
    def __init__(self, filter_type=None, id=None, name=None, is_current=False, connection=None):
        self.filter_type = filter_type
        self.id = id
        self.name = name
        self.is_current = is_current
        self.connection = connection
    
    def make_current(self):
        response = self.connection.make_request(path="cmd=saveFilter&sFilter=%s" % self.id)
        if response.code == 200:
            self.is_current = True


class FilterList(XmlHandler):
    def __init__(self, connection):
        super(FilterList, self).__init__()
        self.filters = None
        self.current_filter = None
        self.connection = connection
    
    def startElement(self, name, attrs):
        super(FilterList, self).startElement(name, attrs)
        if name == 'filters':
            self.filters = []
        elif name == 'filter':
            self.current_filter = Filter(filter_type=attrs['type'], id=attrs['sFilter'], connection=self.connection)
            self.current_filter.is_current = 'status' in attrs and attrs['status'] == 'current'

    def endElement(self, name):
        if name == 'filter' and self.current_filter:
            self.current_filter.name = self.current_value
            self.filters.append(self.current_filter)    
            self.current_filter = None
        super(FilterList, self).endElement(name)
