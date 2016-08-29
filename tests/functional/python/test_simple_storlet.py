# Copyright (c) 2010-2016 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from tests.functional import StorletFunctionalTest


class TestSimpleStorlet(StorletFunctionalTest):
    def setUp(self):
        self.storlet_dir = 'python/simple'
        self.storlet_name = 'simple.py'
        self.storlet_main = 'simple.SimpleStorlet'
        self.storlet_log = 'simple.log'
        self.headers = {'X-Object-Meta-Testkey': 'tester'}
        self.storlet_file = 'source.txt'
        self.container = 'myobjects'
        self.dep_names = []
        self.additional_headers = {}
        self.language = 'Python'
        super(TestSimpleStorlet, self).setUp(self.language)

    def test_get(self):
        # TODO(takashi): Implement tests for storlet execution
        # NOTE(takashi): Currently we need this function, which just 'pass'
        #                to execute setUp to test registration
        pass


class TestSimpleStorletOnProxy(TestSimpleStorlet):
    def setUp(self):
        super(TestSimpleStorletOnProxy, self).setUp()
        self.additional_headers = {'X-Storlet-Run-On-Proxy': ''}