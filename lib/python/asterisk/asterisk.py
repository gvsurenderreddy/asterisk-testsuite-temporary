#!/usr/bin/env python
""" Asterisk Instances in Python.

This module provides an interface for creating instances of Asterisk
from within python code.

Copyright (C) 2010, Digium, Inc.
Russell Bryant <russell@digium.com>

This program is free software, distributed under the terms of
the GNU General Public License Version 2.
"""

import sys
import os
import signal
import time
import shutil
import subprocess
import utils

from config import ConfigFile
from version import AsteriskVersion


class Asterisk:
    """An instance of Asterisk.

    This class assumes that Asterisk has been installed on the system.  The
    installed version of Asterisk will be mirrored for this dynamically created
    instance.

    Instantiate an Asterisk object to create an instance of Asterisk from
    within python code.  Multiple instances of Asterisk are allowed.  However,
    custom configuration will need to be provided to prevent some modules from
    conflicting with each other.  For example, modules that listen for network
    connections will need to be configured to use different ports on each
    instance of Asterisk.

    To set values for the [options] section in asterisk.conf, provide a
    dictionary to the ast_conf_options parameter.  The key should be the option
    name and the value is the option's value to be written out into
    asterisk.conf.
    """

    def __init__(self, base=None, ast_conf_options=None):
        """Construct an Asterisk instance.

        Keyword Arguments:
        base -- This is the root of the files associated with this instance of
        Asterisk.  By default, the base is "tmp/" within the current working
        directory.  Given a base, a unique directory name will be generated to
        hold all files.

        Example Usage:
        self.asterisk = Asterisk(base=os.path.join(os.getcwd(),
                                                   "tests/ami-login/tmp"))
        """
        self.directories = {}
        self.ast_version = AsteriskVersion()

        self.astetcdir = "/etc/asterisk"
        self.ast_binary = utils.which("asterisk") or "/usr/sbin/asterisk"

        # Find the system installed asterisk.conf
        ast_confs = [
                "/etc/asterisk/asterisk.conf",
                "/usr/local/etc/asterisk/asterisk.conf"
        ]
        ast_conf = None
        for c in ast_confs:
            if os.path.exists(c):
                ast_conf = ConfigFile(c)
                break
        if ast_conf is None:
            print "No asterisk.conf found on the system!"
            return

        # Choose an install base
        self.base = base
        if self.base is None:
            self.base = "%s/tmp" % os.getcwd()
        i = 1
        while True:
            if not os.path.isdir("%s/ast%d" % (self.base, i)):
                self.base = "%s/ast%d" % (self.base, i)
                break
            i += 1
        os.makedirs(self.base)

        # Mirror system install directory structure
        dir_cat = None
        for c in ast_conf.categories:
            if c.name == "directories":
                dir_cat = c
        if dir_cat is None:
            print "Unable to discover dir layout from asterisk.conf"
            return
        self.__gen_ast_conf(ast_conf, dir_cat, ast_conf_options)
        for (var, val) in dir_cat.options:
            self.__mirror_dir(var, val)

        self.install_configs(os.getcwd() + "/configs")

    def start(self):
        """Start this instance of Asterisk.

        This function starts up this instance of Asterisk.

        Example Usage:
        asterisk.start()
        """
        cmd = [
            self.ast_binary,
            "-f", "-g", "-q", "-m", "-n",
            "-C", "%s" % os.path.join(self.astetcdir, "asterisk.conf")
        ]
        try:
            self.process = subprocess.Popen(cmd)
        except OSError:
            print "Failed to execute command: %s" % str(cmd)
            return False

        # Be _really_ sure that Asterisk has started up before returning.
        time.sleep(5.0)
        self.cli_exec("core waitfullybooted")

    def stop(self):
        """Stop this instance of Asterisk.

        This function is used to stop this instance of Asterisk.

        Example Usage:
        asterisk.stop()
        """
        # Start by asking to stop gracefully.
        if self.ast_version < AsteriskVersion("1.6.0"):
            self.cli_exec("stop gracefully")
        else:
            self.cli_exec("core stop gracefully")
        for i in xrange(5):
            time.sleep(1.0)
            if self.process.poll() is not None:
                return self.process.returncode

        # Check for locks
        self.cli_exec("core show locks")

        # If the graceful shutdown did not complete within 5 seconds, ask
        # Asterisk to stop right now.
        if self.ast_version < AsteriskVersion("1.6.0"):
            self.cli_exec("stop now")
        else:
            self.cli_exec("core stop now")
        for i in xrange(5):
            time.sleep(1.0)
            if self.process.poll() is not None:
                return self.process.returncode

        # If even a "stop now" didn't do the trick, fall back to sending
        # signals to the process.  First, send a SIGTERM.  If it _STILL_ hasn't
        # gone away after another 5 seconds, send SIGKILL.
        try:
            os.kill(self.process.pid, signal.SIGTERM)
            for i in xrange(5):
                time.sleep(1.0)
                if self.process.poll() is not None:
                    return self.process.returncode
            os.kill(self.process.pid, signal.SIGKILL)
        except OSError:
            # Probably that we sent a signal to a process that was already
            # dead.  Just ignore it.
            pass

        # We have done everything we can do at this point.  Wait for the
        # process to exit.
        self.process.wait()

        return self.process.returncode

    def install_configs(self, cfg_path):
        """Installs all files located in the configuration directory for this
        instance of Asterisk.

        By default, the configuration used will be whatever is found in the
        system install of Asterisk.  However, custom configuration files to be
        used only by this instance can be provided via this API call.

        Keyword Arguments:
        cfg_path -- This argument must be the path to the configuration directory
        to be installed into this instance of Asterisk. Only top-level files will
        be installed, sub directories will be ignored.

        Example Usage:
        asterisk.install_configs("tests/my-cool-test/configs")
        """
        for f in os.listdir(cfg_path):
            target = "%s/%s" % (cfg_path, f)
            if os.path.isfile(target):
                self.install_config(target)

    def install_config(self, cfg_path):
        """Install a custom configuration file for this instance of Asterisk.

        By default, the configuration used will be whatever is found in the
        system install of Asterisk.  However, custom configuration files to be
        used only by this instance can be provided via this API call.

        Note: If a sub-directory is found to have the same name as the running
        instance, install_config() will use the sub-directories version in place
        of the top-level version.

        For example, testsuite is running a test against 1.4 (branch-1.4):

            configs/manager.conf
            configs/sip.conf
            configs/branch-1.4/sip.conf

        Because the sip.conf file exists in the branch-1.4 directory, it will
        be used in place of the top-level sip.conf.  As for the manager.conf
        file, because it does not exists in the branch-1.4 direcory, the
        top-level manager.conf will be used.

        Keyword Arguments:
        cfg_path -- This argument must be the path to the configuration file
        to be installed into the directory tree for this instance of Asterisk.

        Example Usage:
        asterisk.install_config("tests/my-cool-test/configs/manager.conf")
        """
        if not os.path.exists(cfg_path):
            print "Config file '%s' does not exist" % cfg_path
            return

        tmp = "%s/%s/%s" % (os.path.dirname(cfg_path), self.ast_version.branch, os.path.basename(cfg_path))
        if os.path.exists(tmp):
            cfg_path = tmp
        target_path = os.path.join(self.astetcdir, os.path.basename(cfg_path))
        if os.path.exists(target_path):
            os.remove(target_path)
        try:
            shutil.copyfile(cfg_path, target_path)
        except shutil.Error:
            print "'%s' and '%s' are the same file" % (cfg_path, target_path)
        except IOError:
            print "The destination is not writable '%s'" % target_path

    def cli_originate(self, argstr, blocking=True):
        """Starts a call from the CLI and links it to an application or
        context.

        Must pass a valid argument string in the following form:

        <tech/data> application <appname> appdata
        <tech/data> extension <exten>@<context>

        If no context is specified, the 'default' context will be
        used. If no extension is given, the 's' extension will be used.

        Keyword Arguments:
        blocking -- When True, do not return from this function until the CLI
                    command finishes running.  The default is True.

        Example Usage:
        asterisk.originate("Local/a_exten@context extension b_exten@context")
        """

        args = argstr.split()
        raise_error = False
        if len(args) != 3 and len(args) != 4:
            raise_error = True
            print "Wrong number of arguments."
        if args[1] != "extension" and args[1] != "application":
            raise_error = True
            print '2nd argument must be "extension" or "application"'
        if args[0].find("/") == -1:
            raise_error = True
            print 'Channel dial string must be in the form "tech/data".'
        if raise_error is True:
            raise Exception, "Cannot originate call!\n\
            Argument string must be in one of these forms:\n\
            <tech/data> application <appname> appdata\n\
            <tech/data> extension <exten>@<context>"

        if self.ast_version < AsteriskVersion("1.6.2"):
            self.cli_exec("originate %s" % argstr, blocking=blocking)
        else:
            self.cli_exec("channel originate %s" % argstr, blocking=blocking)

    def cli_exec(self, cli_cmd, blocking=True):
        """Execute a CLI command on this instance of Asterisk.

        Keyword Arguments:
        cli_cmd -- The command to execute.
        blocking -- When True, do not return from this function until the CLI
                    command finishes running.  The default is True.

        Example Usage:
        asterisk.cli_exec("core set verbose 10")
        """
        cmd = [
            self.ast_binary,
            "-C", "%s" % os.path.join(self.astetcdir, "asterisk.conf"),
            "-rx", "%s" % cli_cmd
        ]
        print "Executing %s ..." % cmd

        if not blocking:
            process = subprocess.Popen(cmd)
            return ""

        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
        except OSError:
            print "Failed to execute command: %s" % str(cmd)
            return ""

        output = ""
        try:
            for l in process.stdout.readlines():
                print l,
                output += l
        except IOError:
            pass
        try:
            process.wait()
        except OSError:
            pass
        return output

    def __gen_ast_conf(self, ast_conf, dir_cat, ast_conf_options):
        for (var, val) in dir_cat.options:
            if var == "astetcdir":
                self.astetcdir = "%s%s" % (self.base, val)
                os.makedirs(self.astetcdir)

        local_ast_conf_path = os.path.join(self.astetcdir, "asterisk.conf")

        try:
            f = open(local_ast_conf_path, "w")
        except IOError:
            print "Failed to open %s" % local_ast_conf_path
            return
        except:
            print "Unexpected error: %s" % sys.exc_info()[0]
            return

        for c in ast_conf.categories:
            f.write("[%s]\n" % c.name)
            if c.name == "directories":
                for (var, val) in c.options:
                    self.directories[var] = val
                    f.write("%s = %s%s\n" % (var, self.base, val))
            elif c.name == "options":
                f.write("#include \"%s/asterisk.options.conf.inc\"\n" %
                        (self.astetcdir))
                if ast_conf_options:
                    for (var, val) in ast_conf_options.iteritems():
                        f.write("%s = %s\n" % (var, val))
                for (var, val) in c.options:
                    if not ast_conf_options or var not in ast_conf_options:
                        f.write("%s = %s\n" % (var, val))
            else:
                for (var, val) in c.options:
                    f.write("%s = %s\n" % (var, val))
            f.write("\n")

        f.close()

    def __mirror_dir(self, ast_dir_name, ast_dir_path):
        self.__makedirs(ast_dir_path)
        dirs_only = [ "astrundir", "astlogdir", "astspooldir" ]
        if ast_dir_name in dirs_only:
            return
        blacklist = [ "astdb" ]
        for dirname, dirnames, filenames in os.walk(ast_dir_path):
            for filename in filenames:
                target = "%s/%s" % (self.base, os.path.join(ast_dir_path,
                                    dirname, filename))
                if os.path.exists(target) or filename in blacklist:
                    continue
                os.symlink(os.path.join(ast_dir_path, dirname, filename),
                           target)

    def __makedirs(self, ast_dir_path):
        target_dir = "%s%s" % (self.base, ast_dir_path)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        for dirname, dirnames, filenames in os.walk(ast_dir_path):
            for d in dirnames:
                self.__makedirs(os.path.join(target_dir, dirname, d))
