#!/usr/bin/python

# lxc_bootstrap
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

# LXC Bootstrapper, around the lxc-create 'Download' template for userspace
# containers; creates then modifies the container based on specifications.
#
# Designed for Ubuntu / Debian systems.

import sys
import argparse
import crypt
import subprocess as sp
import random
import platform
from string import ascii_letters, digits

SHADOW_SALT_CHARSET = ascii_letters + digits


class TransparentDict(dict):

    def __missing__(self, key):
        return key


# noinspection PyTypeChecker
ARCHITECTURE_MAP = TransparentDict({
    'x86_64': 'amd64',
    'x86': 'i386',
    'armv7l': 'armhf',
    'armv8l': 'arm64'
})


class User:

    def __init__(self, name, password, salt, admin):
        self.name = name
        self.password = password
        self.salt = salt
        self.admin = admin

    @property
    def shadow_password(self):
        if not self.salt or len(self.salt) != 8:
            # Create a random salt
            for _ in range(8):
                try:
                    self.salt += random.SystemRandom().choice(SHADOW_SALT_CHARSET)
                except (TypeError, UnboundLocalError):
                    self.salt = random.SystemRandom().choice(SHADOW_SALT_CHARSET)

        return crypt.crypt(self.password, ('$6${}$'.format(self.salt)))


class Container:
    create_cmd = "/usr/bin/lxc-create -t download -n {0.name} -- -d {0.distribution} -r {0.release} -a {0.architecture}"
    start_cmd = 'lxc-start -n {0.name}'
    attach_cmd = "/usr/bin/lxc-attach -n {0.name} -- "

    def __init__(self,
                 name=None,
                 architecture=None,
                 distribution=None,
                 release=None):
        self.name = name
        self.architecture = architecture
        self.distribution = distribution
        self.release = release
        self.attach_cmd = self.attach_cmd.format(self).split()

    def __call__(self, cmd, error_msg=None):
        cmd = self.attach_cmd + cmd.split()
        try:
            sp.check_call(cmd, stdout=sys.stdout, stderr=sys.stderr)
        except sp.CalledProcessError as e:
            if not error_msg:
                raise e
            print error_msg
            print e
            exit()

    def create(self):
        cmd = self.create_cmd.format(self).split()
        try:
            sp.check_call(cmd, stdout=sys.stdout, stderr=sys.stderr)
        except sp.CalledProcessError as e:
            print "Something went wrong when creating the container."
            print e
            exit()

    def start(self):
        cmd = self.start_cmd.format(self).split()
        try:
            sp.check_call(cmd, stdout=sys.stdout, stderr=sys.stderr)
        except sp.CalledProcessError as e:
            print "Could not start the container, cannot continue with bootstrap."
            print e
            exit()

    def bootstrap_users(self, users):
        # Default comes with 'ubuntu' user and group; let's nuke them
        self("deluser --remove-all-files {}".format("ubuntu"),
             "Could not delete default user and/or group, please refer to error logs.")
        try:
            self("delgroup --only-if-empty {}".format("ubuntu"))
        except sp.CalledProcessError as e:
            if e.returncode == 5:
                print "Could not delete default group, it's not empty!"
            elif e.returncode == 3:
                # return code of 3 means that the group doesn't exist, so we can
                # move on.
                pass

        # Since we just nuked the '1000' group and user (default Ubuntu), let's
        # start there now.
        uid, gid = 1000, 1000

        for user in users:
            try:
                self("useradd --create-home -u {uid} -g {gid} -p {user.shadow_password} "
                     "--shell=/bin/bash {user.name}".format(
                    user=user, gid=gid, uid=uid))
                self(
                    "groupadd -g {gid} {user.name}".format(user=user, gid=gid))
                if user.admin:
                    self("usermod -a -G sudo {user.name}".format(user=user))
            except sp.CalledProcessError:
                print "Something went wrong when bootstrapping user '{0.name}'...".format(user)
            uid += 1
            gid += 1

    def bootstrap_packages(self, to_add, to_exclude, autoremove=False):
        self("apt-get install -y {}".format(" ".join(to_add)), "Something went wrong installing "
                                                               "additional packages.")
        self("apt-get remove -y --purge {}".format(" ".join(to_exclude)), "Something went wrong removing specified packages.")
        if autoremove:
            self("apt-get autoremove -y --purge", "Something went wrong cleaning up after removal with 'autoremove'.")


def _parse_arguments():
    current_platform = platform.platform()
    if 'Windows' in current_platform:
        raise OSError(
            "LXC doesn't work on Windows, so we can't use this script. Sorry!")
    elif 'Linux' not in current_platform:
        raise OSError("This script only works for Linux OSes, sorry!")

    argparser = argparse.ArgumentParser(
        description="LXC Container Bootstrapper Assistant", add_help=True)
    argparser.add_argument('-e', '--existing', '--bootstrap-existing', dest="container_bootstrap_existing",
                           default=False, required=False, action='store_true',
                           help="Don't create a container, run bootstrapping on "
                           "an already-existing container.")
    argparser.add_argument('-n', '--name', type=str, dest="container_name", required=True,
                           help="The name to assign to the LXC container.")
    argparser.add_argument('-a', '--arch', type=str, dest="container_arch", default=None, required=False,
                           help="The architecture for the container")
    argparser.add_argument('-d', '--dist', '--distro', type=str, dest="container_dist", default=None, required=False,
                           help="The distribution for the container")
    argparser.add_argument('-r', '--release', '--codename', type=str, dest="container_release", default=None,
                           required=False, help="The specific release of the container")
    argparser.add_argument('--add-packages', type=str, dest="packages_add", required=False,
                           default='openssh-server,software-properties-common,haveged,python,python-dev,'
                           'python3,python3-dev,perl-modules,ubuntu-server,iptables',
                           help="Comma-separated list of packages to add to the container.")
    argparser.add_argument('--exclude-packages', type=str, dest="packages_exclude", required=False,
                           default='lxd,lxd-client,lxd-tools,lxc',
                           help="Comma-separated list of packages to exclude from the container.")
    argparser.add_argument('--users', '--userdata', '--userfile', type=str, dest="user_datafile", required=False,
                           default=None,
                           help="Path to a file containing user data, one user per line in USERNAME:PASSWORD:SALT:ADMIN"
                           " format, where SALT is an optional 8-character alpha numeric string, and ADMIN is "
                           "'True' or 'False'")

    args = argparser.parse_args()
    args.container_name = args.container_name.strip('\'')

    if not args.container_bootstrap_existing:
        if not args.container_arch:
            args.container_arch = ARCHITECTURE_MAP[
                platform.machine()]

        if not args.container_dist:
            lsb_dist = sp.Popen('/usr/bin/lsb_release -s -i'.split(),
                                stdout=sp.PIPE, stderr=sp.PIPE).communicate()
            if lsb_dist[1]:
                raise SystemError("Error getting release distributor ID.")
            else:
                args.container_dist = lsb_dist[0].lower().strip('\r\n')

        if not args.container_release:
            lsb_codename = sp.Popen('/usr/bin/lsb_release -s -c'.split(),
                                    stdout=sp.PIPE, stderr=sp.PIPE).communicate()
            if lsb_codename[1]:
                raise SystemError(
                    "Error getting release codename from lsb_release")
            args.container_release = lsb_codename[0].lower().strip('\r\n')

    args.to_add = {'openssh-server', 'software-properties-common', 'haveged', 'python', 'python-dev',
                   'python3', 'python3-dev', 'perl-modules', 'ubuntu-server', 'iptables', 'libnetfilter-conntrack3'}
    args.to_remove = {'lxd', 'lxd-client', 'lxd-tools', 'lxc'}
    args.autoremove_after = False
    if args.packages_add:
        args.to_add |= set(map(str.lower, args.packages_add.split(',')))

    if args.packages_exclude:
        delpackages = set(map(str.lower, args.packages_exclude.split(',')))
        args.to_add -= delpackages
        args.to_remove |= delpackages
    return args


def get_users(user_datafile):
    users = []
    if user_datafile:
        with open(user_datafile) as datafile:
            for row in datafile:
                data = row.split(':')
                if len(data) != 4:
                    raise IOError("Invalid data provided from datafile.")
                users.append(User(data[0], data[1], data[2], int(data[3])))
    return users


def run():
    args = _parse_arguments()
    container = Container(args.container_name,
                          args.container_arch,
                          args.container_dist,
                          args.container_release)

    users = [User('teward', 'BLAH', None, True)]
    users += get_users(args.user_datafile)

    if not args.container_bootstrap_existing:
        container.create()

    container.start()
    container.bootstrap_packages(args.to_add, args.to_exclude)
    container.bootstrap_users(users)


if __name__ == "__main__":
    run()
