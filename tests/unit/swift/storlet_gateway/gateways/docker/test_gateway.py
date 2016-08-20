# Copyright (c) 2010-2015 OpenStack Foundation
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

import unittest
from six import StringIO
from tests.unit.swift import FakeLogger
from storlet_gateway.gateways.docker.gateway import DockerStorletRequest, \
    StorletGatewayDocker
from tests.unit import MockSBus
import os
import os.path
from tempfile import mkdtemp
from shutil import rmtree
import mock
import json


class MockInternalClient(object):
    def __init__(self):
        pass


class TestDockerStorletRequest(unittest.TestCase):

    def test_init(self):
        storlet_id = 'Storlet-1.0.jar'
        params = {'Param1': 'Value1', 'Param2': 'Value2'}
        metadata = {'MetaKey1': 'MetaValue1', 'MetaKey2': 'MetaValue2'}
        options = {'storlet_main': 'org.openstack.storlet.Storlet',
                   'storlet_dependency': 'dep1,dep2'}
        dsreq = DockerStorletRequest(storlet_id, params, metadata,
                                     iter(StringIO()), options=options)

        self.assertEqual(metadata, dsreq.user_metadata)
        self.assertEqual(params, dsreq.params)
        self.assertEqual('Storlet-1.0.jar', dsreq.storlet_id)
        self.assertEqual('org.openstack.storlet.Storlet', dsreq.storlet_main)
        self.assertEqual(['dep1', 'dep2'], dsreq.dependencies)

        options = {'storlet_main': 'org.openstack.storlet.Storlet'}
        dsreq = DockerStorletRequest(storlet_id, params, metadata,
                                     iter(StringIO()), options=options)

        self.assertEqual(metadata, dsreq.user_metadata)
        self.assertEqual(params, dsreq.params)
        self.assertEqual('Storlet-1.0.jar', dsreq.storlet_id)
        self.assertEqual('org.openstack.storlet.Storlet', dsreq.storlet_main)
        self.assertEqual([], dsreq.dependencies)

    def test_init_with_range(self):
        storlet_id = 'Storlet-1.0.jar'
        params = {}
        metadata = {}
        options = {'storlet_main': 'org.openstack.storlet.Storlet',
                   'storlet_dependency': 'dep1,dep2',
                   'range_start': 1,
                   'range_end': 6}
        dsreq = DockerStorletRequest(storlet_id, params, metadata,
                                     None, 0, options=options)

        self.assertEqual('Storlet-1.0.jar', dsreq.storlet_id)
        self.assertEqual('org.openstack.storlet.Storlet', dsreq.storlet_main)
        self.assertEqual(['dep1', 'dep2'], dsreq.dependencies)
        self.assertEqual(1, dsreq.start)
        self.assertEqual(6, dsreq.end)

        options = {'storlet_main': 'org.openstack.storlet.Storlet',
                   'storlet_dependency': 'dep1,dep2',
                   'range_start': 0,
                   'range_end': 0}
        dsreq = DockerStorletRequest(storlet_id, params, metadata,
                                     None, 0, options=options)

        self.assertEqual('Storlet-1.0.jar', dsreq.storlet_id)
        self.assertEqual('org.openstack.storlet.Storlet', dsreq.storlet_main)
        self.assertEqual(['dep1', 'dep2'], dsreq.dependencies)
        self.assertEqual(0, dsreq.start)
        self.assertEqual(0, dsreq.end)

    def test_has_range(self):
        storlet_id = 'Storlet-1.0.jar'
        params = {}
        metadata = {}
        options = {'storlet_main': 'org.openstack.storlet.Storlet',
                   'storlet_dependency': 'dep1,dep2'}
        dsreq = DockerStorletRequest(storlet_id, params, metadata,
                                     None, 0, options=options)
        self.assertFalse(dsreq.has_range)

        options = {'storlet_main': 'org.openstack.storlet.Storlet',
                   'storlet_dependency': 'dep1,dep2',
                   'range_start': 1,
                   'range_end': 6}
        dsreq = DockerStorletRequest(storlet_id, params, metadata,
                                     None, 0, options=options)
        self.assertTrue(dsreq.has_range)

        options = {'storlet_main': 'org.openstack.storlet.Storlet',
                   'storlet_dependency': 'dep1,dep2',
                   'range_start': 0,
                   'range_end': 6}
        dsreq = DockerStorletRequest(storlet_id, params, metadata,
                                     None, 0, options=options)
        self.assertTrue(dsreq.has_range)


class TestStorletDockerGateway(unittest.TestCase):

    def setUp(self):
        # TODO(takashi): take these values from config file
        self.tempdir = mkdtemp()
        self.sconf = {
            'host_root': self.tempdir,
            'swift_dir': self.tempdir,
            'storlet_timeout': '9',
            'storlet_container': 'storlet',
            'storlet_dependency': 'dependency',
            'reseller_prefix': 'AUTH'
        }
        self.logger = FakeLogger()

        self.storlet_container = self.sconf['storlet_container']
        self.storlet_dependency = self.sconf['storlet_dependency']

        self.version = 'v1'
        self.account = 'AUTH_account'
        self.container = 'container'
        self.obj = 'object'
        self.sobj = 'storlet-1.0.jar'

        # TODO(kota_): shoudl be 'storlet-internal-client.conf' actually
        ic_conf_path = os.path.join(self.tempdir,
                                    'storlet-proxy-server.conf')
        with open(ic_conf_path, 'w') as f:
            f.write("""
[DEFAULT]
[pipeline:main]
pipeline = catch_errors proxy-logging cache proxy-server

[app:proxy-server]
use = egg:swift#proxy

[filter:cache]
use = egg:swift#memcache

[filter:proxy-logging]
use = egg:swift#proxy_logging

[filter:catch_errors]
use = egg:swift#catch_errors
""")

        self.gateway = StorletGatewayDocker(
            self.sconf, self.logger, self.account)

    def tearDown(self):
        rmtree(self.tempdir)

    @property
    def req_path(self):
        return self._create_proxy_path(
            self.version, self.account, self.container,
            self.obj)

    @property
    def storlet_path(self):
        return self._create_proxy_path(
            self.version, self.account, self.storlet_container,
            self.sobj)

    def _create_proxy_path(self, version, account, container, obj):
        return '/'.join(['', version, account, container, obj])

    def test_check_mandatory_params(self):
        params = {'keyA': 'valueA',
                  'keyB': 'valueB',
                  'keyC': 'valueC'}

        # all mandatory headers are included
        StorletGatewayDocker._check_mandatory_params(
            params, ['keyA', 'keyB'])

        # some of mandatory headers are missing
        with self.assertRaises(ValueError):
            StorletGatewayDocker._check_mandatory_params(
                params, ['keyA', 'KeyD'])

    def test_validate_storlet_registration_java(self):
        # correct name and headers w/ dependency
        obj = 'storlet-1.0.jar'
        params = {'Language': 'java',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'path.to.storlet.class'}
        StorletGatewayDocker.validate_storlet_registration(params, obj)

        # correct name and headers w/o dependency
        obj = 'storlet-1.0.jar'
        params = {'Language': 'java',
                  'Interface-Version': '1.0',
                  'Object-Metadata': 'no',
                  'Main': 'path.to.storlet.class'}
        StorletGatewayDocker.validate_storlet_registration(params, obj)

        # some header keys are missing
        params = {'Language': 'java',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

        # wrong name
        obj = 'storlet.jar'
        params = {'Language': 'java',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'path.to.storlet.class'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

    def test_validate_storlet_registration_python(self):
        # correct name and headers w/ dependency
        obj = 'storlet.py'
        params = {'Language': 'python',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'storlet.Storlet'}
        StorletGatewayDocker.validate_storlet_registration(params, obj)

        # wrong name
        obj = 'storlet.pyfoo'
        params = {'Language': 'python',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'storlet.Storlet'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

        # wrong main class
        obj = 'storlet.py'
        params = {'Language': 'python',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'another_storlet.Storlet'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

        obj = 'storlet.py'
        params = {'Language': 'python',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'storlet'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

        obj = 'storlet.py'
        params = {'Language': 'python',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'storlet.foo.Storlet'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

    def test_validate_storlet_registration_not_suppoeted(self):
        # unsupported language
        obj = 'storlet.foo'
        params = {'Language': 'bar',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'path.to.storlet.class'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

        # same name for storlet and dependency
        obj = 'storlet-1.0.jar'
        params = {'Language': 'java',
                  'Interface-Version': '1.0',
                  'Dependency': 'storlet-1.0.jar',
                  'Object-Metadata': 'no',
                  'Main': 'path.to.storlet.class'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

        # duplicated name in dependencies
        obj = 'storlet-1.0.jar'
        params = {'Language': 'java',
                  'Interface-Version': '1.0',
                  'Dependency': 'dep_file,dep_file',
                  'Object-Metadata': 'no',
                  'Main': 'path.to.storlet.class'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_storlet_registration(params, obj)

    def test_validate_dependency_registration(self):
        # w/o dependency parameter
        obj = 'dep_file'
        params = {'Dependency-Version': '1.0'}
        StorletGatewayDocker.validate_dependency_registration(params, obj)

        # w/ correct dependency parameter
        params = {
            'Dependency-Permissions': '755',
            'Dependency-Version': '1.0'}
        StorletGatewayDocker.validate_dependency_registration(params, obj)

        # w/ wrong dependency parameter
        params = {
            'Dependency-Permissions': '400',
            'Dependency-Version': '1.0'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_dependency_registration(params, obj)

        # w/ invalid dependency parameter
        params = {
            'Dependency-Permissions': 'foo',
            'Dependency-Version': '1.0'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_dependency_registration(params, obj)
        params = {
            'Dependency-Permissions': '888',
            'Dependency-Version': '1.0'}
        with self.assertRaises(ValueError):
            StorletGatewayDocker.validate_dependency_registration(params, obj)

    def test_docker_gateway_communicate(self):
        options = {'generate_log': False,
                   'scope': 'AUTH_account',
                   'storlet_main': 'org.openstack.storlet.Storlet',
                   'storlet_dependency': 'dep1,dep2'}

        st_req = DockerStorletRequest(
            storlet_id=self.sobj,
            params={},
            user_metadata={},
            data_iter=iter('body'), options=options)

        # TODO(kota_): need more efficient way for emuration of return value
        # from SDaemon
        value_generator = iter([
            # Firt is for confirmation for SDaemon running
            'True: daemon running confirmation',
            # Second is stop SDaemon in activation
            'True: stop daemon',
            # Third is start SDaemon again in activation
            'True: start daemon',
            # Forth is return value for invoking as task_id
            'This is task id',
            # Fifth is for getting meta
            json.dumps({'metadata': 'return'}),
            # At last return body and EOF
            'something', '',
        ])

        def mock_read(fd, size):
            try:
                value = next(value_generator)
            except StopIteration:
                raise Exception('called more then expected')
            return value

        def mock_close(fd):
            pass

        # prepare nested mock patch
        # SBus -> mock SBus.send() for container communication
        # os.read -> mock reading the file descriptor from container
        # select.slect -> mock fd communication wich can be readable
        @mock.patch('storlet_gateway.gateways.docker.runtime.SBus', MockSBus)
        @mock.patch('storlet_gateway.gateways.docker.runtime.os.read',
                    mock_read)
        @mock.patch('storlet_gateway.gateways.docker.runtime.os.close',
                    mock_close)
        @mock.patch('storlet_gateway.gateways.docker.runtime.select.select',
                    lambda r, w, x, timeout=None: (r, w, x))
        @mock.patch('storlet_gateway.common.stob.os.read',
                    mock_read)
        def test_invocation_flow():
            sresp = self.gateway.invocation_flow(st_req)
            body = ''
            for data in sresp.data_iter:
                body = body + data
            self.assertEqual('something', body)

        # I hate the decorator to return an instance but to track current
        # implementation, we have to make a mock class for this. Need to fix.

        class MockFileManager(object):
            def get_storlet(self, req):
                return StringIO('mock'), None

            def get_dependency(self, req):
                return StringIO('mock'), None

        st_req.file_manager = MockFileManager()

        test_invocation_flow()


if __name__ == '__main__':
    unittest.main()
