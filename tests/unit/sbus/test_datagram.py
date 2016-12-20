# Copyright (c) 2015-2016 OpenStack Foundation
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

import json
import unittest
import storlets.sbus.file_description as sbus_fd
from storlets.sbus.datagram import FDMetadata, SBusDatagram, \
    SBusServiceDatagram, SBusExecuteDatagram, build_datagram_from_raw_message
from storlets.sbus.command import SBUS_CMD_PING, SBUS_CMD_EXECUTE

ALL_FD_TYPES = [
    sbus_fd.SBUS_FD_INPUT_OBJECT, sbus_fd.SBUS_FD_OUTPUT_OBJECT,
    sbus_fd.SBUS_FD_OUTPUT_OBJECT_METADATA,
    sbus_fd.SBUS_FD_OUTPUT_OBJECT_AND_METADATA,
    sbus_fd.SBUS_FD_LOGGER, sbus_fd.SBUS_FD_OUTPUT_CONTAINER,
    sbus_fd.SBUS_FD_OUTPUT_TASK_ID, sbus_fd.SBUS_FD_SERVICE_OUT,
]


class TestFDMetadata(unittest.TestCase):
    def setUp(self):
        pass

    def test_to_dict(self):
        md = FDMetadata('MYTYPE', {'storlets_key': 'storlets_value'},
                        {'storage_key': 'storage_value'})
        self.assertEqual({'storlets': {'type': 'MYTYPE',
                                       'storlets_key': 'storlets_value'},
                          'storage': {'storage_key': 'storage_value'}},
                         md.to_dict())

    def test_from_dict(self):
        md = FDMetadata.from_dict(
            {'storlets': {'type': 'MYTYPE',
                          'storlets_key': 'storlets_value'},
             'storage': {'storage_key': 'storage_value'}})
        self.assertEqual('MYTYPE', md.fdtype)
        self.assertEqual({'storlets_key': 'storlets_value'},
                         md.storlets_metadata)
        self.assertEqual({'storage_key': 'storage_value'},
                         md.storage_metadata)


class TestSBusDatagram(unittest.TestCase):
    def test_check_required_fd_types_not_implemented(self):
        # SBusDatagram designed not to be called independently
        with self.assertRaises(NotImplementedError) as err:
            SBusDatagram('', [], [])
        self.assertEqual(
            'SBusDatagram class should not be initialized as bare',
            err.exception.message)

    def test_invalid_child_class_definition(self):
        # no definition for _requried_fd_types
        class InvalidSBusDatagram(SBusDatagram):
            pass

        with self.assertRaises(NotImplementedError) as err:
            InvalidSBusDatagram('', [], [])
        self.assertEqual(
            'SBusDatagram class should define _required_fd_types',
            err.exception.message)


class SBusDatagramTestMixin(object):
    def setUp(self):
        self.params = {'param1': 'paramvalue1'}
        self.task_id = 'id'
        self.dtg = self._test_class(self.command, self.fds, self.metadata,
                                    self.params, self.task_id)

    def test_init(self):
        self.assertEqual(self.command, self.dtg.command)
        self.assertEqual(self.fds, self.dtg.fds)
        self.assertEqual(self.metadata, self.dtg.metadata)
        self.assertEqual(self.params, self.dtg.params)
        self.assertEqual(self.task_id, self.dtg.task_id)

    def test_num_fds(self):
        self.assertEqual(len(self.types), self.dtg.num_fds)

    def test_cmd_params(self):
        self.assertEqual({'command': self.command,
                          'params': self.params,
                          'task_id': self.task_id},
                         self.dtg.cmd_params)

    def test_serialized_metadata(self):
        self.assertEqual(self.metadata,
                         json.loads(self.dtg.serialized_metadata))

    def test_serialized_cmd_params(self):
        res = {'command': self.command,
               'params': self.params,
               'task_id': self.task_id}
        self.assertEqual(res, json.loads(self.dtg.serialized_cmd_params))

    def test_check_required_fd_types_mismatch(self):
        invalid_types = (
            [],  # empty list
            ['Invalid'] + self.types,  # invalid type inserted at the first
            # TODO(kota_): we may want *strict* check (not only checking first
            #              N items.
        )

        for invalid_type in invalid_types:
            with self.assertRaises(ValueError) as cm:
                self.dtg._check_required_fd_types(invalid_type)
            self.assertTrue(cm.exception.message.startswith(
                'Fd type mismatch given_fd_types'))

    def test_check_fd_nums(self):
        with self.assertRaises(ValueError):
            self.dtg._check_fd_nums([], self.metadata)

    def test_find_fds(self):
        # prepare all fd types and then pop out in the loop below
        not_in_fd_types = ALL_FD_TYPES[:]
        # N.B. fd should start from 1 (not 0), really?
        for index, fd_type in enumerate(self.types, 1):
            found_fds = self.dtg._find_fds(fd_type)
            # at least 1 fd should be found
            self.assertTrue(found_fds)
            # and the index is in the types
            self.assertIn(index, found_fds)

            if fd_type in not_in_fd_types:
                # N.B. ALL_FD_TYPES should be unique list
                not_in_fd_types.remove(fd_type)

        # sanity, not a fd type results in []
        self.assertEqual([], self.dtg._find_fds('DUMMY_TYPE'))

        # sanity, no other types are found
        for fd_type in not_in_fd_types:
            self.assertEqual([], self.dtg._find_fds(fd_type))

    def test_find_fd(self):
        # prepare all fd types and then pop out in the loop below
        not_in_fd_types = ALL_FD_TYPES[:]
        # N.B. fd should start from 1 (not 0), really?
        for index, fd_type in enumerate(self.types, 1):
            found_fd = self.dtg._find_fd(fd_type)
            # at least 1 fd should be found
            self.assertEqual(index, found_fd)

            if fd_type in not_in_fd_types:
                # N.B. ALL_FD_TYPES should be unique list
                not_in_fd_types.remove(fd_type)

        # sanity, not a fd type results in None
        self.assertIs(None, self.dtg._find_fd('DUMMY_TYPE'))

        # sanity, no other types are found
        for fd_type in not_in_fd_types:
            self.assertIs(None, self.dtg._find_fd(fd_type))


class TestSBusServiceDatagram(SBusDatagramTestMixin, unittest.TestCase):
    _test_class = SBusServiceDatagram

    def setUp(self):
        self.command = 'SBUS_CMD_TEST'
        self.types = [sbus_fd.SBUS_FD_SERVICE_OUT]
        self.fds = [1]
        self.metadata = [FDMetadata(sbus_fd.SBUS_FD_SERVICE_OUT).to_dict()]
        super(TestSBusServiceDatagram, self).setUp()

    def test_service_out_fd(self):
        self.assertEqual(1, self.dtg.service_out_fd)


class TestSBusExecuteDatagram(SBusDatagramTestMixin, unittest.TestCase):
    _test_class = SBusExecuteDatagram

    def setUp(self):
        self.command = SBUS_CMD_EXECUTE
        self.types = [sbus_fd.SBUS_FD_INPUT_OBJECT,
                      sbus_fd.SBUS_FD_OUTPUT_TASK_ID,
                      sbus_fd.SBUS_FD_OUTPUT_OBJECT,
                      sbus_fd.SBUS_FD_OUTPUT_OBJECT_METADATA,
                      sbus_fd.SBUS_FD_LOGGER]
        self.fds = [i + 1 for i in range(len(self.types))]
        self.metadata = [FDMetadata(self.types[i],
                         {'key%d' % i: 'value%d' % i},
                         {'skey%d' % i: 'svalue%d' % i}).to_dict()
                         for i in range(len(self.types))]
        super(TestSBusExecuteDatagram, self).setUp()

    def test_init_extra_sources(self):
        types = [sbus_fd.SBUS_FD_INPUT_OBJECT,
                 sbus_fd.SBUS_FD_OUTPUT_TASK_ID,
                 sbus_fd.SBUS_FD_OUTPUT_OBJECT,
                 sbus_fd.SBUS_FD_OUTPUT_OBJECT_METADATA,
                 sbus_fd.SBUS_FD_LOGGER,
                 sbus_fd.SBUS_FD_INPUT_OBJECT,
                 sbus_fd.SBUS_FD_INPUT_OBJECT,
                 sbus_fd.SBUS_FD_INPUT_OBJECT]
        fds = [i + 1 for i in xrange(len(types))]
        metadata = [FDMetadata(types[i],
                    {'key%d' % i: 'value%d' % i},
                    {'skey%d' % i: 'svalue%d' % i}).to_dict()
                    for i in xrange(len(types))]
        dtg = self._test_class(
            self.command, fds, metadata, self.params, self.task_id)
        self.assertEqual(dtg.fds, fds)
        self.assertEqual(dtg.metadata, metadata)
        self.assertEqual(dtg.params, self.params)
        self.assertEqual(dtg.task_id, self.task_id)

    def test_object_out_fds(self):
        self.assertEqual([3], self.dtg.object_out_fds)

    def test_object_metadata_out_fds(self):
        self.assertEqual([4], self.dtg.object_metadata_out_fds)

    def test_task_id_out_fd(self):
        self.assertEqual(2, self.dtg.task_id_out_fd)

    def test_logger_out_fd(self):
        self.assertEqual(5, self.dtg.logger_out_fd)

    def test_object_in_fds(self):
        self.assertEqual([1], self.dtg.object_in_fds)

    def test_check_required_fd_types_reverse_order_failed(self):
        types = self.types[:]
        types.reverse()  # reverse order
        with self.assertRaises(ValueError) as cm:
            self.dtg._check_required_fd_types(types)
        self.assertTrue(
            cm.exception.message.startswith('Fd type mismatch given_fd_types'))


class TestBuildDatagramFromRawMessage(unittest.TestCase):

    def test_build_datagram_from_raw_message(self):
        # SBusServiceDatagram scenario
        command = SBUS_CMD_PING
        types = [sbus_fd.SBUS_FD_SERVICE_OUT]
        fds = [1]
        metadata = [FDMetadata(sbus_fd.SBUS_FD_SERVICE_OUT).to_dict()]
        params = {'param1': 'paramvalue1'}
        task_id = 'id'
        cmd_params = {'command': command, 'params': params, 'task_id': task_id}

        str_metadata = json.dumps(metadata)
        str_cmd_params = json.dumps(cmd_params)
        dtg = build_datagram_from_raw_message(fds, str_metadata,
                                              str_cmd_params)

        self.assertEqual(command, dtg.command)
        self.assertEqual(fds, dtg.fds)
        self.assertEqual(metadata, dtg.metadata)
        self.assertEqual(params, dtg.params)
        self.assertEqual(task_id, dtg.task_id)

        # SBusExecuteDatagram scenario
        command = SBUS_CMD_EXECUTE
        types = [sbus_fd.SBUS_FD_INPUT_OBJECT,
                 sbus_fd.SBUS_FD_OUTPUT_TASK_ID,
                 sbus_fd.SBUS_FD_OUTPUT_OBJECT,
                 sbus_fd.SBUS_FD_OUTPUT_OBJECT_METADATA,
                 sbus_fd.SBUS_FD_LOGGER,
                 sbus_fd.SBUS_FD_INPUT_OBJECT,
                 sbus_fd.SBUS_FD_INPUT_OBJECT,
                 sbus_fd.SBUS_FD_INPUT_OBJECT]
        fds = [i + 1 for i in xrange(len(types))]
        metadata = [FDMetadata(types[i],
                    {'key%d' % i: 'value%d' % i},
                    {'skey%d' % i: 'svalue%d' % i}).to_dict()
                    for i in xrange(len(types))]
        params = {'param1': 'paramvalue1'}
        task_id = 'id'
        cmd_params = {'command': command, 'params': params, 'task_id': task_id}

        str_metadata = json.dumps(metadata)
        str_cmd_params = json.dumps(cmd_params)
        dtg = build_datagram_from_raw_message(fds, str_metadata,
                                              str_cmd_params)

        self.assertEqual(command, dtg.command)
        self.assertEqual(fds, dtg.fds)
        self.assertEqual(metadata, dtg.metadata)
        self.assertEqual(params, dtg.params)
        self.assertEqual(task_id, dtg.task_id)


if __name__ == '__main__':
    unittest.main()
