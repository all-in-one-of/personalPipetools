# =============================================================================
# $Id: __init__.py,v 1.25 2011/10/25 18:17:17 tfan Exp $
# =============================================================================
# Module: rh.app.rpc
# Contacts: fxdev
# =============================================================================
"""
R&H extension to rpyc, for streamlining port communication to ANY app
with a native python environment (crom, Houdini, maya, etc).

rh.app.port is inspired by Houdini's broken hrpyc example and makes everything
self contained.  This module allows us to issue native package python code over
an open port which is a big advantage over the perl/hscript/AppTalk hook
implementation of the past.
"""

__version__ = "$Id: __init__.py,v 1.25 2011/10/25 18:17:17 tfan Exp $"

# =============================================================================
# IMPORTS
# =============================================================================

# Non-R&H imports
import atexit
import copy
import errno        # This is the only way to get standard errno lookups
import itertools
import os
import socket
import subprocess
import sys
import threading
import time

# R&H imports
from rh.logutils import logDebug, logInfo, logWarning, createLogHandler

# rpyc related imports
import rpyc
from rh.app.rpc import utils as rpcutils
from rh.app.rpc import callbacks
from rh.subprocess import Run

# Store all open ports by application
_SERVERS = {}
_OPENEDPORTS = {}
MAX_TRIES = 8
HOU_SLEEP_TIMES = [1, 3, 5, 10]


# =============================================================================
# FUNCTIONS
# =============================================================================

# -----------------------------------------------------------------------------
#    Name: _bindPort
#    Args: (int) port : A port number or 0 to have the kernel give us a port
# Returns: A new port number that may be valid
#  Raises: N/A
#    Desc: Does a socket.bind to find a port number if 0 otherwise tries
#          to bind to that port
# -----------------------------------------------------------------------------
def _bindPort(host='localhost', portNum=0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, portNum))
    except socket.error, sockExc:
        raise UsedOrReservedRPCError('{0} (port {1})'.format(sockExc.strerror, portNum))
    # getsockname() returns (IP, port)
    port = sock.getsockname()[1]
    sock.close()

    return port


def portFromApp(app):
    """
    Returns a port from an application metadata tag.
    """
    if _OPENEDPORTS.has_key(app):
        openports = _OPENEDPORTS[app].keys()
        if len(openports) > 1:
            logWarning('Multiple open ports for app {0} found, returning first opened...')
        return openports[0]

    raise RPCError('No port started for {0}'.format(app))


def startServer(app, port=None, quiet=True, nodup=True):
    """Starts an rpyc server.

    Args:
        (str) app:
            The metadata application name to be associated with this server.

        (int) port=None:
            A port to explicitly start on, if none is specified a free one on
            the system is returned.

        (bool) quiet=True:
            Start our server quietly.  This is an rpyc option.

        (bool) nodup=True:
            Allow for no duplicate servers.

    Typical usage is something like

    startServer(app='houdini')
    startServer(app='crom')

    A random available port on the system will be chosen if one is not
    specified.
    """

    # Let's not make any duplicate servers
    if nodup:
        if _OPENEDPORTS.has_key(app) and _OPENEDPORTS[app]:
            allports = _OPENEDPORTS[app].keys()
            logWarning('Server already started for "{0}" on port(s): {1}'.format(app, allports))
            return

    serverStartTries = 1
    # If a port is not specified, specify port 0.  This causes socket.bind to
    # return a random open port on the system.  Also specify 5 tries if we're
    # trying a random port in case we run into some race condition
    if not port:
        serverStartTries = 5
        port = 0

    port = _bindPort(portNum=port)

    # Inject our port and add dont-register
    args = []
    if quiet:
        args.append('-q')
    args.extend(('-p', str(port), '--dont-register'))

    options, args = rpcutils.PARSER.parse_args(args)
    options.registrar = None
    options.authenticator = None

    triedPorts = []

    # The number of allowable tries before we giveup
    for _ in range(1, serverStartTries+1):
        try:
            _SERVERS[port] = rpcutils.serveBgThreaded(options)
            logDebug("Started rpyc server for '{0}' @ port {1}".format(app, port))
            if not _OPENEDPORTS.has_key(app):
                _OPENEDPORTS[app] = dict()
            _OPENEDPORTS[app].setdefault(port, []).append(os.getpid())
            return _SERVERS[port]
        except (StandardError, socket.error):
            triedPorts.append(str(port))
            # Try again
            continue

    raise RPCError('Server start fail!  Tried ports: {0}'.format(', '.join(triedPorts)))


def closeServer(port):
    """Close a particular RPC server."""
    (threadedServer, topThread) = _SERVERS[port]
    threadedServer.close()
    topThread.join()
    for app in _OPENEDPORTS.keys():
        if _OPENEDPORTS[app].has_key(port):
            del _OPENEDPORTS[app][port]
    del _SERVERS[port]
    logDebug('Successfully closed port {0}'.format(port))


@atexit.register
def closeAllServers():
    """Closes all RPC servers."""
    allServerPorts = _SERVERS.keys()

    if not allServerPorts:
        return

    logInfo('Closing all RPC servers...')
    for port in allServerPorts:
        closeServer(port)

    logDebug('Stopping client cleaner thread...')


def importRemoteModules(port, modules=None, server='localhost', retries=5):
    """Imports a list of modules over a port.

    Args:
        (int) port
            The port number we wish to connect to.

        (list) modules=None
            List of module names we wish to import.

        (str) server='localhost'
            The server hostname.

        (int) retries=5
            Number of attempts to import remote module before raising an error.

    Returns:
        (conn, modulelist)

    Imports module names on server spawned over port.  We need to return a
    connection and the modulelist so that the connection object does not go out
    of scope which makes our modules become NoneTypes.
    """
    tries = 1

    # Let's do a timeout thing
    connection = None

    while tries <= MAX_TRIES:
        try:
            connection = rpyc.classic.connect(server, port)
        except socket.timeout, sockExc:
            if tries < MAX_TRIES:
                tries += 1
                print 'Timed out, trying again...'
                time.sleep(0.5)
            else:
                print sockExc
                raise RPCConnectError('{0} (port {1})'.format(sockExc.strerror, port))
        except IOError as (errno, strerror):
            raise RPCConnectError("I/O error({0}): {1}".format(errno, strerror))
        except EOFError:
            raise RPCConnectError("EOF error")

        if connection:
            break

    if not modules or not isinstance(modules, list):
        raise ValueError('"modules" arg expects a list of module names!')

    remoteModules = []
    if retries < 1:
        retries = 1
    houTry = 0
    while houTry < retries:
        try:
            remoteModules = [connection.modules[mod] for mod in modules]
        except KeyError, e:
            if (houTry + 1) >= retries:
                # we have run out of retries
                # raise an error
                raise NoSuchModuleRPCError(e.args)
            else:
                # keep trying until we run out of retries
                # sleep for some time in between tries
                index = houTry if houTry < len(HOU_SLEEP_TIMES) else -1
                time.sleep(HOU_SLEEP_TIMES[index])
                houTry += 1
                continue
        houTry = retries
        

    return connection, remoteModules


# =============================================================================
# EXCEPTIONS
# =============================================================================

class RPCError(StandardError):
    """Base class for port related exceptions"""
    pass


class RPCConnectError(RPCError):
    """Exception raised when a connection to an RPC server failed."""
    pass


class UsedOrReservedRPCError(RPCError):
    """Exception used to signal a used port, used for control flow as well.
    """
    pass


class CantFindScriptRPCError(RPCError):
    """Exception raised when a script can't be found."""
    def __init__(self, script, area):
        super(self.__class__, self).__init__()
        self._script = script
        self._area = area

    def __str__(self):
        msg = 'Unable to find script "{0}" in area "{1}"'
        return msg.format(self._script, self._area)


class NoSuchModuleRPCError(RPCError):
    """Raised when a module is imported that does not exist."""
    def __init__(self, modName):
        super(self.__class__, self).__init__()
        self._modName = modName

    def __str__(self):
        return 'No such module {0}!'.format(self._modName)
