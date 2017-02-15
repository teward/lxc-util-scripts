#!/usr/bin/python

# lxc_nuke
# Copyright (C) 2017  Thomas Ward <teward@ubuntu.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# LXC utility script to 'nuke' a container, whether it is running or not.
# Basically, we stop the container if it is running, then destroy.
#
# Designed for Ubuntu / Debian systems.

import sys
import argparse
import traceback as tb
import subprocess as sp

CONTAINERS = None


# noinspection PyClassHasNoInit
class LXC:
    create = '/usr/bin/lxc-create '
    destroy = '/usr/bin/lxc-destroy '
    list = '/usr/bin/lxc-ls '
    stop = '/usr/bin/lxc-stop '


def _parse_arguments():
    argparser = argparse.ArgumentParser(description="A script that can find and destroy both active and "
                                                    "inactive LXC containers.", add_help=True)
    argparser.add_argument('name', type=str, help="The name of the container to 'nuke'")

    return argparser.parse_args()


def _get_container_list():
    listcmd = str(LXC.list)
    listexec = sp.Popen(listcmd.split(), stdout=sp.PIPE, stderr=sp.PIPE).communicate()
    if listexec[1] != '':
        print "Unable to get container list from LXC, cannot continue"
        exit()

    # noinspection PyUnboundLocalVariable
    return listexec[0]


def _container_exists(container_name):
    if container_name in containers:
        return True
    else:
        return False


def _container_is_running(container_name):
    g1exec = str(LXC.list) + '--fancy'
    grep1 = sp.Popen(g1exec.split(), stdout=sp.PIPE, stderr=sp.PIPE)
    grep2 = sp.Popen(str('grep %s' % container_name).split(), stdin=grep1.stdout, stdout=sp.PIPE, stderr=sp.PIPE)
    grep3 = sp.Popen('grep RUNNING'.split(), stdin=grep2.stdout, stdout=sp.PIPE, stderr=sp.PIPE).communicate()

    print grep3
    if grep3[1] != '':
        print "An error occurred checking if container [%s] is running, stopping nuke process." % container_name
        exit()
    elif 'RUNNING' in grep3[0]:
        return True
    else:
        return False


def _stop_container(container_name):
    stopcmd = str(LXC.stop) + ("-n %s" % container_name)
    stopexec = sp.Popen(stopcmd.split(), stdout=sp.PIPE, stdin=sp.PIPE).communicate()
    if stopexec[1] != '':
        print stopexec[1]
        print "An error occurred trying to stop container [%s]." % container_name
        exit()
    else:
        print "Container [%s] has been stopped." % container_name


def _destroy_container(container_name):
    destroycmd = str(LXC.destroy) + ('-n %s' % container_name)
    destroyexec = sp.Popen(destroycmd.split(), stdout=sp.PIPE, stderr=sp.PIPE).communicate()
    if destroyexec[1] != '':
        print destroyexec[1]
        print "An error occured trying to destroy container [%s]." % container_name
        exit()
    else:
        print "Container [%s] has been destroyed.\n" % container_name


# noinspection PyUnreachableCode
def _run():
    args = _parse_arguments()

    container_name = args.name

    print "Checking if container [%s] exists..." % container_name
    if not _container_exists(container_name):
        print "Container [%s] does not exist, nothing to nuke.\n" % container_name
        exit()
    else:
        print "Container [%s] found, working to nuke container...\n" % container_name

    if _container_is_running(container_name):
        print "Container [%s] is running, stopping the container..." % container_name
        _stop_container(container_name)
        print "Container [%s] has been stopped, we can now destroy it.\n" % container_name
    else:
        print "Container [%s] is not running, attempting to destroy container...\n" % container_name

    print "Now attempting to destroy container [%s]..." % container_name
    _destroy_container(container_name)

    print "Container [%s] nuked successfully." % container_name
    exit()


if __name__ == "__main__":
    # noinspection PyBroadException
    try:
        containers = _get_container_list()
        _run()
    except not SystemExit:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        print "\n"
        tb.print_exception(exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout)
