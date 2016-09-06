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

import errno
import logging
import mock
import unittest
from six import StringIO

import sbus.command

from tests.unit.swift import FakeLogger
from storlet_daemon_factory.daemon_factory import CommandResponse, \
    CommandSuccess, CommandFailure, SDaemonError, DaemonFactory, start_logger


class TestCommandResponse(unittest.TestCase):
    def setUp(self):
        pass

    def test_init(self):
        resp = CommandResponse(True, 'ok')
        self.assertTrue(resp.status)
        self.assertEqual('ok', resp.message)
        self.assertTrue(resp.iterable)

        resp = CommandResponse(False, 'error', False)
        self.assertFalse(resp.status)
        self.assertEqual('error', resp.message)
        self.assertFalse(resp.iterable)

    def test_report_message(self):
        resp = CommandResponse(True, 'msg', True)
        self.assertEqual('True: msg', resp.report_message)


class TestCommandSuccess(unittest.TestCase):
    def setUp(self):
        pass

    def test_init(self):
        resp = CommandSuccess('ok')
        self.assertTrue(resp.status)
        self.assertEqual('ok', resp.message)
        self.assertTrue(resp.iterable)


class TestCommandFailure(unittest.TestCase):
    def setUp(self):
        pass

    def test_init(self):
        resp = CommandFailure('error')
        self.assertFalse(resp.status)
        self.assertEqual('error', resp.message)
        self.assertTrue(resp.iterable)


class TestLogger(unittest.TestCase):
    def setUp(self):
        pass

    def test_start_logger(self):
        sio = StringIO()
        logger = logging.getLogger('CONT #abcdef: test')
        logger.addHandler(logging.StreamHandler(sio))

        # set log level as INFO
        logger = start_logger('test', 'INFO', 'abcdef')
        self.assertEqual(logging.INFO, logger.level)
        # INFO message is recorded with INFO leg level
        logger.info('test1')
        self.assertEqual(sio.getvalue(), 'test1\n')
        # DEBUG message is not recorded with INFO leg level
        logger.debug('test2')
        self.assertEqual(sio.getvalue(), 'test1\n')

        # set log level as DEBUG
        logger = start_logger('test', 'DEBUG', 'abcdef')
        self.assertEqual(logging.DEBUG, logger.level)
        # DEBUG message is recorded with DEBUG leg level
        logger.debug('test3')
        self.assertEqual(sio.getvalue(), 'test1\ntest3\n')

        # If the level parameter is unknown, use ERROR as log level
        logger = start_logger('test', 'foo', 'abcdef')
        self.assertEqual(logging.ERROR, logger.level)


class TestDaemonFactory(unittest.TestCase):
    base_path = 'storlet_daemon_factory.daemon_factory'
    kill_path = base_path + '.os.kill'
    waitpid_path = base_path + '.os.waitpid'
    sbus_path = base_path + '.SBus'

    def setUp(self):
        self.logger = FakeLogger()
        self.pipe_path = 'path/to/pipe'
        self.dfactory = DaemonFactory(self.pipe_path, self.logger)

    def test_get_jvm_args(self):
        dummy_env = {'CLASSPATH': '/default/classpath',
                     'LD_LIBRARY_PATH': '/default/ld/library/path'}
        with mock.patch('storlet_daemon_factory.daemon_factory.os.environ',
                        dummy_env):
            pargs, env = self.dfactory.get_jvm_args(
                'java', 'path/to/storlet/a', 'Storlet-1.0.jar',
                1, 'path/to/uds/a', 'DEBUG', 'contid')
            self.assertEqual(
                ['/usr/bin/java', 'org.openstack.storlet.daemon.SDaemon',
                 'Storlet-1.0.jar', 'path/to/uds/a', 'DEBUG', '1', 'contid'],
                pargs)
            self.assertEqual(
                {'CLASSPATH': '/default/classpath:'
                              '/opt/storlets/logback-classic-1.1.2.jar:'
                              '/opt/storlets/logback-core-1.1.2.jar:'
                              '/opt/storlets/slf4j-api-1.7.7.jar:'
                              '/opt/storlets/json_simple-1.1.jar:'
                              '/opt/storlets/SBusJavaFacade.jar:'
                              '/opt/storlets/SCommon.jar:'
                              '/opt/storlets/SDaemon.jar:'
                              '/opt/storlets/:path/to/storlet/a',
                 'LD_LIBRARY_PATH': '/default/ld/library/path:'
                                    '/opt/storlets/'},
                env)

    def test_get_python_args(self):
        dummy_env = {'PYTHONPATH': '/default/pythonpath'}
        with mock.patch('storlet_daemon_factory.daemon_factory.os.environ',
                        dummy_env):
            pargs, env = self.dfactory.get_python_args(
                'python', 'path/to/storlet', 'test_storlet.TestStorlet',
                1, 'path/to/uds', 'DEBUG', 'contid')
        self.assertEqual(
            ['/usr/local/bin/storlets-daemon', 'test_storlet.TestStorlet',
             'path/to/uds', 'DEBUG', '1', 'contid'],
            pargs)
        self.assertEqual(
            {'PYTHONPATH': '/default/pythonpath:'
                           '/home/swift/test_storlet.TestStorlet'},
            env)

    def test_spawn_subprocess(self):
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a'}

        class FakePopenObject(object):
            def __init__(self, pid):
                self.pid = pid
                self.stderr = mock.MagicMock()

        with mock.patch(self.base_path + '.subprocess.Popen') as popen, \
                mock.patch(self.base_path + '.time.sleep'), \
                mock.patch(self.waitpid_path) as waitpid, \
                mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read:
            popen.side_effect = [FakePopenObject(1000),
                                 FakePopenObject(1001)]
            waitpid.return_value = 0, 0
            send.return_value = 0
            read.return_value = 'True: OK'
            self.dfactory.spawn_subprocess(
                ['arg0', 'argv1', 'argv2'],
                {'envk0': 'envv0'}, 'storleta')
            self.assertEqual((1000, 1), waitpid.call_args[0])
            self.assertEqual({'storleta': 1000},
                             self.dfactory.storlet_name_to_pid)

        with mock.patch(self.base_path + '.subprocess.Popen') as popen, \
                mock.patch(self.base_path + '.time.sleep'), \
                mock.patch(self.waitpid_path) as waitpid, \
                mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read:
            popen.side_effect = [FakePopenObject(1000),
                                 FakePopenObject(1001)]
            waitpid.return_value = 0, 0
            send.return_value = 0
            read.return_value = 'False: NG'
            with self.assertRaises(SDaemonError):
                self.dfactory.spawn_subprocess(
                    ['arg0', 'argv1', 'argv2'],
                    {'envk0': 'envv0'}, 'storleta')
            self.assertEqual((1000, 1), waitpid.call_args[0])
            self.assertEqual({'storleta': 1000},
                             self.dfactory.storlet_name_to_pid)

        with mock.patch(self.base_path + '.subprocess.Popen') as popen, \
                mock.patch(self.base_path + '.time.sleep'), \
                mock.patch(self.waitpid_path) as waitpid:
            popen.side_effect = [FakePopenObject(1000),
                                 FakePopenObject(1001)]
            waitpid.return_value = 1000, -1
            with self.assertRaises(SDaemonError):
                self.dfactory.spawn_subprocess(
                    ['arg0', 'argv1', 'argv2'],
                    {'envk0': 'envv0'}, 'storleta')
            self.assertEqual((1000, 1), waitpid.call_args[0])

        with mock.patch(self.base_path + '.subprocess.Popen') as popen:
            popen.side_effect = OSError()
            with self.assertRaises(SDaemonError):
                self.dfactory.spawn_subprocess(
                    ['arg0', 'argv1', 'argv2'],
                    {'envk0': 'envv0'}, 'storleta')

    def test_wait_for_daemon_to_initialize(self):
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a'}

        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.time.sleep'), \
                mock.patch(self.base_path + '.os.read') as read:
            send.side_effect = [-1, 0]
            read.return_value = 'True: OK'
            self.assertTrue(
                self.dfactory.wait_for_daemon_to_initialize('storleta'))
            self.assertEqual(2, send.call_count)
            self.assertEqual(1, read.call_count)

        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.time.sleep'), \
                mock.patch(self.base_path + '.os.read') as read:
            send.return_value = 0
            read.return_value = 'False: NG'
            self.assertFalse(
                self.dfactory.wait_for_daemon_to_initialize('storleta'))
            self.assertEqual(
                self.dfactory.NUM_OF_TRIES_PINGING_STARTING_DAEMON,
                send.call_count)
            self.assertEqual(
                self.dfactory.NUM_OF_TRIES_PINGING_STARTING_DAEMON,
                read.call_count)

        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a', 'storletb': 'path/to/uds/b'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.time.sleep'):
            send.return_value = -1
            self.assertFalse(
                self.dfactory.wait_for_daemon_to_initialize('storleta'))
            self.assertEqual(
                self.dfactory.NUM_OF_TRIES_PINGING_STARTING_DAEMON,
                send.call_count)

    def test_process_start_daemon(self):
        # Not running
        self.dfactory.storlet_name_to_pid = {}
        self.dfactory.storlet_name_to_pipe_name = {}

        class FakePopenObject(object):
            def __init__(self, pid):
                self.pid = pid
                self.stderr = mock.MagicMock()

        with mock.patch(self.base_path + '.subprocess.Popen') as popen, \
                mock.patch(self.base_path + '.time.sleep'), \
                mock.patch(self.waitpid_path) as waitpid, \
                mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read:
            popen.side_effect = [FakePopenObject(1000),
                                 FakePopenObject(1001)]
            waitpid.return_value = 0, 0
            send.return_value = 0
            read.return_value = 'True: OK'
            self.assertTrue(self.dfactory.process_start_daemon(
                'java', 'path/to/storlet/a', 'storleta', 1, 'path/to/uds/a',
                'TRACE', 'contid'))
            self.assertEqual({'storleta': 'path/to/uds/a'},
                             self.dfactory.storlet_name_to_pipe_name)

        # Already running
        self.dfactory.storlet_name_to_pid = {'storleta': 1000}
        self.dfactory.storlet_name_to_pipe_name = {'storleta': 'path/to/uds/a'}
        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 0, 0
            self.assertFalse(self.dfactory.process_start_daemon(
                'java', 'path/to/storlet/a', 'storleta', 1, 'path/to/uds/a',
                'TRACE', 'contid'))

        # Unsupported language
        with self.assertRaises(SDaemonError):
            self.dfactory.process_start_daemon(
                'foo', 'path/to/storlet/a', 'storleta', 1, 'path/to/uds/a',
                'TRACE', 'contid')

    def test_get_process_status_by_name(self):
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 0, 0
            self.assertTrue(
                self.dfactory.get_process_status_by_name('storleta'))
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual((1000, 1), waitpid.call_args[0])

        self.assertFalse(
            self.dfactory.get_process_status_by_name('storletc'))

    def test_get_process_status_by_pid(self):
        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 0, 0
            self.assertTrue(
                self.dfactory.get_process_status_by_pid(1000, 'storleta'))
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual((1000, 1), waitpid.call_args[0])

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 1000, 0
            self.assertFalse(
                self.dfactory.get_process_status_by_pid(1000, 'storleta'))
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual((1000, 1), waitpid.call_args[0])

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.side_effect = OSError(errno.ESRCH, '')
            self.assertFalse(
                self.dfactory.get_process_status_by_pid(1000, 'storleta'))
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual((1000, 1), waitpid.call_args[0])

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.side_effect = OSError(errno.EPERM, '')
            exc_pattern = '^No permission to access the storlet daemon' + \
                          ' for storleta$'
            with self.assertRaisesRegexp(SDaemonError, exc_pattern):
                self.dfactory.get_process_status_by_pid(1000, 'storleta')
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual((1000, 1), waitpid.call_args[0])

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.side_effect = OSError()
            exc_pattern = '^Unknown error$'
            with self.assertRaisesRegexp(SDaemonError, exc_pattern):
                self.dfactory.get_process_status_by_pid(1000, 'storleta')
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual((1000, 1), waitpid.call_args[0])

    def test_process_kill(self):
        # Success
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 1000, 0
            self.assertEqual((1000, 0),
                             self.dfactory.process_kill('storleta'))
            self.assertEqual(1, kill.call_count)
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual({'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # When failed to send kill to the storlet daemon
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            kill.side_effect = OSError()
            with self.assertRaises(SDaemonError):
                self.dfactory.process_kill('storleta')
            self.assertEqual(1, kill.call_count)
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # When failed to wait
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            waitpid.side_effect = OSError()
            with self.assertRaises(SDaemonError):
                self.dfactory.process_kill('storleta')
            self.assertEqual(1, kill.call_count)
            self.assertEqual(1, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # if the storlet daemon is not recognised
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            with self.assertRaises(SDaemonError):
                self.dfactory.process_kill('storletc')
            self.assertEqual(0, kill.call_count)
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

    def test_process_kill_all(self):
        # Success
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            waitpid.side_effect = [(1000, 0), (1001, 0)]
            self.dfactory.process_kill_all()
            self.assertEqual(2, kill.call_count)
            self.assertEqual(2, waitpid.call_count)
            self.assertEqual({}, self.dfactory.storlet_name_to_pid)

        # Success (no processes)
        self.dfactory.storlet_name_to_pid = {}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            self.dfactory.process_kill_all()
            self.assertEqual(0, kill.call_count)
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({}, self.dfactory.storlet_name_to_pid)

        # Failure (try_all = True)
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            kill.side_effect = OSError()
            exc_pattern = '^Failed to stop some storlet daemons: .*'
            with self.assertRaisesRegexp(SDaemonError, exc_pattern) as e:
                self.dfactory.process_kill_all()
            self.assertIn('storleta', str(e.exception))
            self.assertIn('storletb', str(e.exception))
            self.assertEqual(2, kill.call_count)
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # Failure (try_all = False)
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path) as waitpid:
            kill.side_effect = OSError()
            exc_pattern = '^Failed to send kill signal to storlet[a-b]$'
            with self.assertRaisesRegexp(SDaemonError, exc_pattern):
                self.dfactory.process_kill_all(False)
            self.assertEqual(1, kill.call_count)
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

    def test_shutdown_all_processes(self):
        # Success
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a', 'storletb': 'path/to/uds/b'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read, \
                mock.patch(self.waitpid_path):
            send.return_value = 0
            read.return_value = 'True: OK'
            terminated = self.dfactory.shutdown_all_processes()
            self.assertEqual(2, len(terminated))
            self.assertIn('storleta', terminated)
            self.assertIn('storletb', terminated)
            self.assertEqual({},
                             self.dfactory.storlet_name_to_pid)

        # Failure (try_all = True)
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'patha', 'storletb': 'pathb'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read, \
                mock.patch(self.waitpid_path) as waitpid:
            send.return_value = -1
            read.return_value = 'True: OK'
            exc_pattern = '^Failed to shutdown some storlet daemons: .*'
            with self.assertRaisesRegexp(SDaemonError, exc_pattern) as e:
                self.dfactory.shutdown_all_processes()
            self.assertIn('storleta', str(e.exception))
            self.assertIn('storletb', str(e.exception))
            self.assertEqual(2, send.call_count)
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # Failure (try_all = False)
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'patha', 'storletb': 'pathb'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read, \
                mock.patch(self.waitpid_path) as waitpid:
            send.return_value = -1
            read.return_value = 'True: OK'
            exc_pattern = '^Failed to send halt to storlet[a-b]$'
            with self.assertRaisesRegexp(SDaemonError, exc_pattern):
                self.dfactory.shutdown_all_processes(False)
            self.assertEqual(1, send.call_count)
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

    def test_shutdown_process(self):
        # Success
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a', 'storletb': 'path/to/uds/b'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read, \
                mock.patch(self.waitpid_path):
            send.return_value = 0
            read.return_value = 'True: OK'
            self.dfactory.shutdown_process('storleta')
            self.assertEqual({'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # Failed to send a command to the storlet daemon
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a', 'storletb': 'path/to/uds/b'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read, \
                mock.patch(self.waitpid_path) as waitpid:
            send.return_value = -1
            read.return_value = 'True: OK'
            with self.assertRaises(SDaemonError):
                self.dfactory.shutdown_process('storleta')
            self.assertEqual(0, waitpid.call_count)
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # Failed to wait
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a', 'storletb': 'path/to/uds/b'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read, \
                mock.patch(self.waitpid_path) as waitpid:
            send.return_value = 0
            read.return_value = 'True: OK'
            waitpid.side_effect = OSError()
            with self.assertRaises(SDaemonError):
                self.dfactory.shutdown_process('storleta')
            self.assertEqual({'storleta': 1000, 'storletb': 1001},
                             self.dfactory.storlet_name_to_pid)

        # If the storlet is not found in pid mapping
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a', 'storletb': 'path/to/uds/b'}
        with self.assertRaises(SDaemonError):
            self.dfactory.shutdown_process('storletc')

    def test_start_daemon(self):
        prms = {'daemon_language': 'java',
                'storlet_path': 'path/to/storlet/a',
                'storlet_name': 'storleta',
                'pool_size': 1,
                'uds_path': 'path/to/uds/a',
                'log_level': 'TRACE'}
        # Not running
        self.dfactory.storlet_name_to_pid = {}
        self.dfactory.storlet_name_to_pipe_name = {}

        class FakePopenObject(object):
            def __init__(self, pid):
                self.pid = pid
                self.stderr = mock.MagicMock()

        with mock.patch(self.base_path + '.subprocess.Popen') as popen, \
                mock.patch(self.base_path + '.time.sleep'), \
                mock.patch(self.waitpid_path) as waitpid, \
                mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read:
            popen.side_effect = [FakePopenObject(1000),
                                 FakePopenObject(1001)]
            waitpid.return_value = 0, 0
            send.return_value = 0
            read.return_value = 'True: OK'
            ret = self.dfactory.start_daemon('contid', prms)
            self.assertTrue(ret.status)
            self.assertEqual('OK', ret.message)
            self.assertTrue(ret.iterable)

        # Already running
        self.dfactory.storlet_name_to_pid = {'storleta': 1000}
        self.dfactory.storlet_name_to_pipe_name = {'storleta': 'path/to/uds/a'}
        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 0, 0
            ret = self.dfactory.start_daemon('contid', prms)
            self.assertTrue(ret.status)
            self.assertEqual('storleta is already running', ret.message)
            self.assertTrue(ret.iterable)

        # Unsupported language
        prms['daemon_language'] = 'foo'
        ret = self.dfactory.start_daemon('contid', prms)
        self.assertFalse(ret.status)
        self.assertEqual('Got unsupported daemon language: foo', ret.message)
        self.assertTrue(ret.iterable)

    def test_stop_daemon(self):
        # Success
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000}
        with mock.patch(self.kill_path), \
                mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 1000, 0
            resp = self.dfactory.stop_daemon(
                'contid', {'storlet_name': 'storleta'})
            self.assertTrue(resp.status)
            self.assertEqual('Storlet storleta, PID = 1000, ErrCode = 0',
                             resp.message)
            self.assertTrue(resp.iterable)

        # Failure
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000}
        with mock.patch(self.kill_path) as kill, \
                mock.patch(self.waitpid_path):
            kill.side_effect = OSError('ERROR')
            resp = self.dfactory.stop_daemon(
                'contid', {'storlet_name': 'storleta'})
            self.assertFalse(resp.status)
            self.assertEqual('Failed to kill the storlet daemon storleta',
                             resp.message)
            self.assertTrue(resp.iterable)

    def test_daemon_status(self):
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 0, 0
            resp = self.dfactory.daemon_status(
                'contid', {'storlet_name': 'storleta'})
            self.assertTrue(resp.status)
            self.assertEqual('Storlet storleta seems to be OK', resp.message)
            self.assertTrue(resp.iterable)

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.return_value = 1000, 0
            resp = self.dfactory.daemon_status(
                'contid', {'storlet_name': 'storleta'})
            self.assertFalse(resp.status)
            self.assertEqual('No running storlet daemon for storleta',
                             resp.message)
            self.assertTrue(resp.iterable)

        with mock.patch(self.waitpid_path) as waitpid:
            waitpid.side_effect = OSError()
            resp = self.dfactory.daemon_status(
                'contid', {'storlet_name': 'storleta'})
            self.assertFalse(resp.status)
            self.assertEqual('Unknown error', resp.message)
            self.assertTrue(resp.iterable)

    def test_halt(self):
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        self.dfactory.storlet_name_to_pipe_name = \
            {'storleta': 'path/to/uds/a', 'storletb': 'path/to/uds/b'}
        with mock.patch(self.sbus_path + '.send') as send, \
                mock.patch(self.base_path + '.os.read') as read, \
                mock.patch(self.waitpid_path):
            send.return_value = 0
            read.return_value = 'True: OK'
            resp = self.dfactory.halt('contid', {})
            self.assertTrue(resp.status)
            self.assertIn('storleta: terminated', resp.message)
            self.assertIn('storletb: terminated', resp.message)
            self.assertFalse(resp.iterable)

    def test_stop_daemons(self):
        # Success
        self.dfactory.storlet_name_to_pid = \
            {'storleta': 1000, 'storletb': 1001}
        with mock.patch(self.kill_path), \
                mock.patch(self.waitpid_path) as waitpid:
            waitpid.side_effect = [(1000, 0), (1001, 0)]
            resp = self.dfactory.stop_daemons(
                'contid', {})
            self.assertTrue(resp.status)
            self.assertEqual('OK', resp.message)
            self.assertFalse(resp.iterable)

    def test_get_handler(self):
        # start daemon
        self.assertEqual(
            self.dfactory.start_daemon,
            self.dfactory.get_handler(
                sbus.command.SBUS_CMD_START_DAEMON))
        # stop daemon
        self.assertEqual(
            self.dfactory.stop_daemon,
            self.dfactory.get_handler(
                sbus.command.SBUS_CMD_STOP_DAEMON))
        # daemon status
        self.assertEqual(
            self.dfactory.daemon_status,
            self.dfactory.get_handler(
                sbus.command.SBUS_CMD_DAEMON_STATUS))
        # stop daemons
        self.assertEqual(
            self.dfactory.stop_daemons,
            self.dfactory.get_handler(
                sbus.command.SBUS_CMD_STOP_DAEMONS))
        # halt
        self.assertEqual(
            self.dfactory.halt,
            self.dfactory.get_handler(
                sbus.command.SBUS_CMD_HALT))
        # ping
        self.assertEqual(
            self.dfactory.ping,
            self.dfactory.get_handler(
                sbus.command.SBUS_CMD_PING))
        # invalid
        with self.assertRaises(ValueError):
            self.dfactory.get_handler('FOO')
        # unknown
        with self.assertRaises(ValueError):
            self.dfactory.get_handler('SBUS_CMD_UNKNOWN')
        # not command handler
        with self.assertRaises(ValueError):
            self.dfactory.get_handler('SBUS_CMD_GET_JVM_ARGS')


if __name__ == '__main__':
    unittest.main()
