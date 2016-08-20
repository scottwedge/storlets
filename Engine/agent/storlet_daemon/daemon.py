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
import logging
from logging.handlers import SysLogHandler
import errno
import os
import pwd
import sys
import uuid
from sbus import SBus
from sbus.command import SBUS_CMD_PREFIX


EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def command_handler(func):
    """
    Decorator for handler functions for command
    """
    func.is_command_handler = True
    return func


class Daemon(object):

    def __init__(self, storlet_name, sbus_path, logger, pool_size):
        self.storlet_name = storlet_name
        self.sbus_path = sbus_path
        self.logger = logger
        self.pool_size = pool_size
        self.task_id_to_pid = {}
        self.chunk_size = 16

    def _cleanup_pids(self):
        """
        Remove pids which are already terminated
        """
        terminated = []
        for task_id, daemon_pid in self.task_id_to_pid.iteritems():
            try:
                pid, rc = os.waitpid(daemon_pid, os.WNOHANG)
                if pid or rc:
                    terminated.append(task_id)
            except OSError as err:
                if err.errno == errno.ESRCH:
                    terminated.append(task_id)
                if err.errno == errno.ECHILD:
                    # TODO(takashi): Can we skip checking the remaining ones?
                    terminated.append(task_id)
                else:
                    self.logger.exception('Failed to get the status of '
                                          'the subprocess with pid %d' %
                                          daemon_pid)
        for task_id in terminated:
            self.task_id_to_pid.pop(task_id)

    def _remove_pid(self, pid):
        """
        Remove pid from map dict

        :param pid: the pid of the terminated process
        """
        for task_id, daemon_pid in self.task_id_to_pid.iteritems():
            if daemon_pid == pid:
                self.task_id_to_pid.pop(task_id)
                break

    def _wait_child_process(self):
        """
        Wait until the one of the subprocesses gets terminated
        """
        # We save current length of pid map
        prev_num = len(self.task_id_to_pid)

        # First, we need to remove remaining pids of terminated processes
        self._cleanup_pids()
        if not self.task_id_to_pid or len(self.task_id_to_pid) < prev_num:
            # We don't need have to wait here, when we find
            #  1. we do not have any subprocesses
            #  2. some of the subprocesses are already terminated
            # as the result of cleaning up pid map
            return

        try:
            pid = os.wait()[0]
            self._remove_pid(pid)
        except OSError as e:
            if e.errno == errno.ECHILD:
                # Currently we don't have any subprocesses, so reset the dict
                # here
                self.task_id_to_pid = {}
                pass
            else:
                self.logger.exception('Failed to wait existing subprocesses')

    def _wait_all_child_processes(self):
        self.logger.debug('Wait until all of the subprocesses are '
                          'terminated')
        while len(self.task_id_to_pid):
            self._wait_child_process()

    @command_handler
    def halt(self, dtg):
        return False

    def _safe_close_fd(self, fd):
        try:
            os.close(fd)
        except OSError as err:
            if err.errno != errno.EBADF:
                self.logger.exception('Failed to close fd: %d' % fd)
                raise
            pass

    def _safe_close_fds(self, fds):
        for fd in fds:
            self._safe_close_fd(fd)

    @command_handler
    def execute(self, dtg):
        task_id_out_fd = dtg.task_id_out_fd

        task_id = str(uuid.uuid4())[:8]

        while len(self.task_id_to_pid) >= self.pool_size:
            self._wait_child_process()

        self.logger.debug('Returning task_id: %s ' % task_id)
        with os.fdopen(task_id_out_fd, 'w') as outfile:
            outfile.write(task_id)

        in_fds = dtg.object_in_fds
        in_md = dtg.object_in_metadata
        out_md_fds = dtg.object_metadata_out_fds
        out_fds = dtg.object_out_fds
        logger_fd = dtg.logger_out_fd

        pid = os.fork()
        if pid:
            self.logger.debug('Create a subprocess %d for task %s' %
                              (pid, task_id))
            self.task_id_to_pid[task_id] = pid

            self._safe_close_fds(in_fds)
            self._safe_close_fds(out_md_fds)
            self._safe_close_fds(out_fds)
            self._safe_close_fd(logger_fd)
        else:
            try:
                self.logger.debug('Start storlet invocation')

                self.logger.debug('in_fds:%s in_md:%s out_md_fds:%s out_fds:%s'
                                  % (in_fds, in_md, out_md_fds, out_fds))
                with os.fdopen(out_md_fds[0], 'w') as out_md_file:
                    self.logger.debug('Returning metadata')
                    out_md_file.write(json.dumps(in_md[0]))

                with os.fdopen(in_fds[0], 'r') as in_file, \
                        os.fdopen(out_fds[0], 'w') as out_file, \
                        os.fdopen(logger_fd, 'w') as log_file:
                    self.logger.debug('Start to return object data')
                    log_file.write('Executed\n')
                    while True:
                        buf = in_file.read(self.chunk_size)
                        self.logger.debug('Recieved %d bytes' % len(buf))
                        self.logger.debug('Writing back %d bytes' % len(buf))
                        out_file.write(buf)

                        if not buf:
                            break

                self.logger.debug('Completed')
            except Exception:
                self.logger.exception('Error in storlet invocation')
            finally:
                sys.exit()
        return True

    @command_handler
    def descriptor(self, dtg):
        # NOTE(takashi): Currently we don't use this one, but we need to
        #                implement this maybe when we implement multi output
        #                support
        self.logger.error('Descriptor operation is not implemented')
        raise NotImplementedError()

    @command_handler
    def ping(self, dtg):
        out_fd = dtg.service_out_fd
        with os.fdopen(out_fd, 'w') as outfile:
            outfile.write('OK')
        return True

    @command_handler
    def cancel(self, dtg):
        out_fd = dtg.service_out_fd
        task_id = dtg.task_id
        pid = self.task_id_to_pid.get(task_id)
        with os.fdopen(out_fd, 'w') as outfile:
            if not pid:
                outfile.write('BAD')
            else:
                try:
                    os.kill(pid)
                    self._remove_pid(pid)
                    outfile.write('OK')
                except OSError:
                    self.logger.exception('Failed to kill subprocess: %d' %
                                          pid)
                    outfile.write('ERROR')
        return False

    def get_handler(self, command):
        """
        Decide handler function correspoiding to the recieved command

        :param command: command
        :returns: handler function
        """
        if not command.startswith(SBUS_CMD_PREFIX):
            raise ValueError('got unknown command %s' % command)
        func_name = command[len(SBUS_CMD_PREFIX):].lower()
        try:
            handler = getattr(self, func_name)
            getattr(handler, 'is_command_handler')
        except AttributeError:
            raise ValueError('got unknown command %s' % command)
        return handler

    def dispatch_command(self, dtg, container_id):
        command = dtg.command
        self.logger.debug("Received command {0}".format(command))

        try:
            handler = self.get_handler(command)
        except ValueError:
            self.logger.exception('Failed to decide handler')
            return True
        else:
            self.logger.debug('Do %s' % command)
            return handler(dtg)

    def main_loop(self, container_id):
        sbus = SBus()
        fd = sbus.create(self.sbus_path)
        if fd < 0:
            self.logger.error("Failed to create SBus. exiting.")
            return EXIT_FAILURE

        while True:
            rc = sbus.listen(fd)
            if rc < 0:
                self.logger.error("Failed to wait on SBus. exiting.")
                return EXIT_FAILURE

            dtg = sbus.receive(fd)
            if dtg is None:
                self.logger.error("Failed to receive message. exiting")
                return EXIT_FAILURE

            if not self.dispatch_command(dtg, container_id):
                break

        self.logger.debug('Leaving main loop')
        self._wait_all_child_processes()
        return EXIT_SUCCESS


def start_logger(logger_name, log_level, container_id):
    """

    Initialize logging of this process and set logger format

    :param logger_name: The name to report with
    :param log_level: The verbosity level. This should be selected
    :param container_id: container id
    """
    logging.raiseExceptions = False
    log_level = log_level.upper()

    # NOTE(takashi): currently logging.WARNING is defined as the same value
    #                as logging.WARN, so we can properly handle WARNING here
    try:
        level = getattr(logging, log_level)
    except AttributeError:
        level = logging.ERROR

    logger = logging.getLogger("CONT #" + container_id + ": " + logger_name)

    if log_level == 'OFF':
        logging.disable(logging.CRITICAL)
    else:
        logger.setLevel(level)

    log_handler = SysLogHandler('/dev/log')
    str_format = '%(name)-12s: %(levelname)-8s %(funcName)s' + \
                 ' %(lineno)s [%(process)d, %(threadName)s]' + \
                 ' %(message)s'
    formatter = logging.Formatter(str_format)
    log_handler.setFormatter(formatter)
    log_handler.setLevel(level)
    logger.addHandler(log_handler)
    return logger


def usage():
    """
    Print the expected command line arguments.
    """
    print("storlets-daemon <storlet_name> <sbus_path> <log_level> "
          "<pool_size> <cotnainer id>")


def main(argv):
    """
    The entry point of daemon_factory process

    :param argv: parameters given from command line
    """
    if (len(argv) != 5):
        usage()
        return EXIT_FAILURE

    storlet_name = argv[0]
    sbus_path = argv[1]
    log_level = argv[2]
    pool_size = argv[3]
    container_id = argv[4]

    # Initialize logger
    logger = start_logger("storlets-daemon", log_level, container_id)
    logger.debug("Storlet Daemon started")
    SBus.start_logger("DEBUG", container_id=container_id)

    # Impersonate the swift user
    pw = pwd.getpwnam('swift')
    os.setresgid(pw.pw_gid, pw.pw_gid, pw.pw_gid)
    os.setresuid(pw.pw_uid, pw.pw_uid, pw.pw_uid)

    # create an instance of storlet daemon
    daemon = Daemon(storlet_name, sbus_path, logger, pool_size)

    # Start the main loop
    return daemon.main_loop(container_id)
