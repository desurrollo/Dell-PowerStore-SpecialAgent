#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
"""Check_MK Dell PowerStore Special Agent"""

# Developed with Dell PowerStore 500T
# https://www.dell.com/support/manuals/cs-cz/powerstore-500t/pwrstr-apidevg/managing-a-rest-api-session
# https://dell.com/powerstoredocs

import argparse
from collections.abc import Sequence
import os
import re
from requests.sessions import Session
from requests.auth import HTTPBasicAuth
import socket
import sys
import tempfile
from pathlib import Path
import urllib3

from cmk.special_agents.v0_unstable.agent_common import (
    SectionWriter,
    special_agent_main,
)
from cmk.special_agents.v0_unstable.argument_parsing import (
    Args,
    create_default_argument_parser,
)
import cmk.utils.password_store



# .
#   .--args----------------------------------------------------------------.
#   |                                                                      |
#   |                          __ _ _ __ __ _ ___                          |
#   |                         / _` | '__/ _` / __|                         |
#   |                        | (_| | | | (_| \__ \                         |
#   |                         \__,_|_|  \__, |___/                         |
#   |                                   |___/                              |
#   '----------------------------------------------------------------------'

def file_path(path):
    if os.path.isfile(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_file:{path} is not a valid path")

def parse_arguments(argv: Sequence[str] | None) -> Args:

    parser = create_default_argument_parser(description=__doc__)

    # flags
    parser.add_argument("--no-cert-check",
                        action="store_true",
                        help="""Disables the checking of the servers ssl certificate""")

    parser.add_argument("--ca-bundle",
        type=file_path,
        default='/etc/ssl/certs/ca-bundle.crt',
        help="""Set the path to CA BUNDLE for SSL server certificate verification.""")
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=60,
        help="""Set the network timeout to Dell PowerStore to SECS seconds. The timeout is not only
        applied to the connection, but also to each individual subquery.""")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=443,
        help="""Alternative port number (default is 443 for the https connection).""")

    # optional arguments (from a coding point of view - should some of them be mandatory?)
    parser.add_argument("-u", "--user", default=None, help="""Username for login""")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-s",
        "--password",
        default=None,
        help="""Password for login. Preferred over --password-id""",
    )
    group.add_argument(
        "--password-id",
        default=None,
        help="""Password store reference to the password for login""",
    )

    # positional arguments
    parser.add_argument("host_address",
                        metavar="HOST",
                        help="""Host name or IP address of Dell PowerStore""")

    return parser.parse_args(argv)


#.
#   .--Connection----------------------------------------------------------.
#   |             ____                       _   _                         |
#   |            / ___|___  _ __  _ __   ___| |_(_) ___  _ __              |
#   |           | |   / _ \| '_ \| '_ \ / _ \ __| |/ _ \| '_ \             |
#   |           | |__| (_) | | | | | | |  __/ |_| | (_) | | | |            |
#   |            \____\___/|_| |_|_| |_|\___|\__|_|\___/|_| |_|            |
#   |                                                                      |
#   '----------------------------------------------------------------------'


class DPSUnauthorized(RuntimeError):
    """ 401 Unauthorized """
    pass

class DPSForbidden(RuntimeError):
    """ 403 Forbidden """
    pass

class DPSUndecoded(RuntimeError):
    """ XXX Undecoded """
    pass


class DPSSession(Session):
    """Encapsulates the Sessions with the Dell PowerStore system"""

    def __init__(self, address, port, verify='/etc/ssl/certs/ca-certificates.crt',
                 user=None, secret=None):
        super(DPSSession, self).__init__()
        self.verify = verify
        if not self.verify:
            # Watch out: we must provide the verify keyword to every individual request call!
            # Else it will be overwritten by the REQUESTS_CA_BUNDLE env variable
            urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)

        self._rest_api_url = f"https://{address}:{port}/api/rest"
        self.headers.update({
            "Accept": "application/json",
            "User-Agent": "Checkmk special agent for Dell PowerStore",
        })
        if user is not None and secret is not None:
            self.auth = HTTPBasicAuth(user, secret)

    def query(self, method, urlsubd, **kwargs):
        if hasattr(self, 'csrf_token'):
            kwargs.setdefault('headers', {})['DELL-EMC-TOKEN'] = self.csrf_token
        response = method(self._rest_api_url + '/' + urlsubd, **kwargs, verify=self.verify)
        self.csrf_token = response.headers['DELL-EMC-TOKEN']
        if response.status_code == 200:
            return response.json()
        if response.status_code == 206:
            json1 = response.json()
            crange = response.headers['Content-Range']
            crd, clen = crange.split('/', 1)
            istart, iend = crd.split('-', 1)
            clen = int(clen)
            istart = int(istart)
            iend = int(iend)
            inext = iend +1
            if inext < clen:
                hdr = kwargs.get('headers', {})
                hdr["Range"] = f"{inext}-"
                kwargs['headers'] = hdr
                json1.extend(self.query_get(urlsubd, **kwargs))
            return json1
        if response.status_code == 401:
            raise DPSUnauthorized("401 Unauthorized")
        if response.status_code == 403:
            raise DPSForbidden("403 Forbidden")
        raise DPSUndecoded(f"{response.status_code} Undecoded status code")

    def query_get(self, urlsubd, **kwargs):
        return self.query(self.get, urlsubd, **kwargs)

    def query_post_json(self, urlsubd, json, **kwargs):
        return self.query(self.post, urlsubd, json=json, **kwargs)


#.
#   .--unsorted------------------------------------------------------------.
#   |                                       _           _                  |
#   |            _   _ _ __  ___  ___  _ __| |_ ___  __| |                 |
#   |           | | | | '_ \/ __|/ _ \| '__| __/ _ \/ _` |                 |
#   |           | |_| | | | \__ \ (_) | |  | ||  __/ (_| |                 |
#   |            \__,_|_| |_|___/\___/|_|   \__\___|\__,_|                 |
#   |                                                                      |
#   '----------------------------------------------------------------------'


def get_information(s: DPSSession, args: Args):
    """get an information from the REST API interface"""

    ainfo = s.query_get('openapi.json')['info']
    with SectionWriter("check_mk", " ") as w:
        w.append("Version: 2.0")
        w.append(f"AgentOS: {ainfo['title']} {ainfo['version']}")

    appliance = s.query_get('appliance?select=*')
    with SectionWriter("appliance") as w:
        w.append_json(appliance)

    with SectionWriter("hardware") as w:
        w.append_json(s.query_get('hardware?select=*'))

    volume = s.query_get('volume?select=*')
    with SectionWriter("volume") as w:
        w.append_json(volume)

    # Map replication_session.id -> volume.name using volume.metro_replication_session_id
    metro_name_by_session_id = {}
    for v in volume:
        sid = v.get("metro_replication_session_id")
        vname = v.get("name") or v.get("display_name") or v.get("description")
        if sid and vname:
            metro_name_by_session_id[str(sid)] = str(vname)

    replication = s.query_get('replication_session?select=*')

    # Enrich replication sessions with GUI "Resource" name
    for rs in replication:
        sid = rs.get("id")
        if sid:
            rs["resource_name"] = metro_name_by_session_id.get(str(sid))
        if not rs.get("resource_name"):
            # Fallback if not found (keep it safe)
            rs["resource_name"] = str(rs.get("local_resource_id") or sid or "<unknown>")

    with SectionWriter("replication_session") as w:
        w.append_json(replication)

#    with SectionWriter("performance_metrics_by_appliance") as w:
#        d = []
#        for app in appliance:
#            d.append(s.query_post_json('metrics/generate', {
#                      "entity": "performance_metrics_by_appliance",
#                      "entity_id": app['id'],
#                      "interval": "Best_Available"
#                    })[-1])
#        w.append_json(d)

    with SectionWriter("space_metrics_by_appliance") as w:
        d = []
        for app in appliance:
            d.append(s.query_post_json('metrics/generate', {
                      "entity": "space_metrics_by_appliance",
                      "entity_id": app['id'],
                      "interval": "Best_Available"
                    })[-1])
        w.append_json(d)

    return 0


#.
#   .--Main----------------------------------------------------------------.
#   |                        __  __       _                                |
#   |                       |  \/  | __ _(_)_ __                           |
#   |                       | |\/| |/ _` | | '_ \                          |
#   |                       | |  | | (_| | | | | |                         |
#   |                       |_|  |_|\__,_|_|_| |_|                         |
#   |                                                                      |
#   '----------------------------------------------------------------------'


def agent_dell_powerstore_main(args: Args) -> int:
    """main function for the special agent"""

    if args.no_cert_check:
        verify = False
    else:
        verify = args.ca_bundle

    if args.password_id:
        pw_id, pw_path = args.password_id.split(":")
    pw = args.password or cmk.utils.password_store.lookup(Path(pw_path), pw_id)

    socket.setdefaulttimeout(args.timeout)
    try:
        s = DPSSession(args.host_address, args.port, verify, args.user, pw)
        s.query_get("login_session")
        get_information(s, args)

    except Exception as exc:
        if args.debug:
            raise
        sys.stderr.write("%s\n" % exc)
        return 1

    return 0


def main() -> int:
    """Main entry point to be used"""
    return special_agent_main(parse_arguments, agent_dell_powerstore_main)


if __name__ == "__main__":
    sys.exit(main())
