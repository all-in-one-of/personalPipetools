# =============================================================================
# $Id: __init__.py,v 1.1 2011/06/10 00:35:21 fdu Exp $
# =============================================================================
# Module: rh.app.rpc.utils
# Contacts: FXDG & Pipeline, Rhythm & Hues Studios
# =============================================================================
"""
rpyc API to start servers, lifted from rpyc/servers/classic_server script.

Most applications trying to launch an rpyc server should use the
serveThreaded() function.  The others have not been tested.

To see available options hardcoded into this module one can run:

python -c 'import rh.rpyc.server.classic as classicserver; classicserver.PARSER.print_help()'
"""
# System imports
import sys
import os
import rpyc
from optparse import OptionParser
import threading

# rpyc imports
from rpyc.utils.server import ThreadedServer, ForkingServer
from rpyc.utils.classic import DEFAULT_SERVER_PORT
from rpyc.utils.registry import REGISTRY_PORT
from rpyc.utils.registry import UDPRegistryClient, TCPRegistryClient
from rpyc.utils.authenticators import VdbAuthenticator
from rpyc.core import SlaveService


PARSER = OptionParser()
PARSER.add_option("-m", "--mode", action="store", dest="mode", metavar="MODE",
    default="threaded", type="string", help="mode can be 'threaded', 'forking', "
    "or 'stdio' to operate over the standard IO pipes (for inetd, etc.). "
    "Default is 'threaded'")
PARSER.add_option("-p", "--port", action="store", dest="port", type="int", 
    metavar="PORT", default=DEFAULT_SERVER_PORT, help="specify a different "
    "TCP listener port. Default is 18812")
PARSER.add_option("--host", action="store", dest="host", type="str", 
    metavar="HOST", default="0.0.0.0", help="specify a different "
    "host to bind to. Default is 0.0.0.0")
PARSER.add_option("--logfile", action="store", dest="logfile", type="str", 
    metavar="FILE", default=None, help="specify the log file to use; the "
    "default is stderr")
PARSER.add_option("-q", "--quiet", action="store_true", dest="quiet", 
    default=False, help="quiet mode (no logging). in stdio mode, "
    "writes to /dev/null")
PARSER.add_option("--vdb", action="store", dest="vdbfile", metavar="FILENAME",
    default=None, help="starts an TLS/SSL authenticated server (using tlslite);"
    "the credentials are loaded from the vdb file. if not given, the server"
    "is not secure (unauthenticated). use vdbconf.py to manage vdb files"
)
PARSER.add_option("--dont-register", action="store_false", dest="auto_register", 
    default=True, help="disables this server from registering at all. "
    "By default, the server will attempt to register")
PARSER.add_option("--registry-type", action="store", dest="regtype", type="str", 
    default="udp", help="can be 'udp' or 'tcp', default is 'udp'")
PARSER.add_option("--registry-port", action="store", dest="regport", type="int", 
    default=REGISTRY_PORT, help="the UDP/TCP port. default is %s" % (REGISTRY_PORT,))
PARSER.add_option("--registry-host", action="store", dest="reghost", type="str", 
    default=None, help="the registry host machine. for UDP, the default is "
    "255.255.255.255; for TCP, a value is required")

def getOptions():
    """Parses options for our various servers."""
    options, args = PARSER.parse_args()
    if args:
        PARSER.error("does not take positional arguments: %r" % (args,))

    options.mode = options.mode.lower()

    if options.regtype.lower() == "udp":
        if options.reghost is None:
            options.reghost = "255.255.255.255"
        options.registrar = UDPRegistryClient(ip = options.reghost, port = options.regport)
    elif options.regtype.lower() == "tcp":
        if options.reghost is None:
            PARSER.error("must specific --registry-host")
        options.registrar = TCPRegistryClient(ip = options.reghost, port = options.regport)
    else:
        PARSER.error("invalid registry type %r" % (options.regtype,))

    if options.vdbfile:
        if not os.path.exists(options.vdbfile):
            PARSER.error("vdb file does not exist")
        options.authenticator = VdbAuthenticator.from_file(options.vdbfile, mode = "r")
    else:
        options.authenticator = None

    mode = options.mode
    options.handler = "serve%s" % (mode[0].upper() + mode[1:],)
    if options.handler not in globals():
        PARSER.error("invalid mode %r" % (options.mode,))

    return options


def serveBgThreaded(options):
    """Starts a background threaded server.  This is what you want in most cases."""
    ts = ThreadedServer(SlaveService, hostname = options.host,
         port = options.port, reuse_addr = True,
         authenticator = options.authenticator, registrar = options.registrar,
         auto_register = options.auto_register)
    ts.logger.quiet = options.quiet
    if options.logfile:
        ts.logger.console = open(options.logfile, "w")
    topThread = threading.Thread(target = ts.start)
    topThread.setDaemon(True)
    topThread.start()
    return [ts, topThread]


def serveThreaded(options):
    """Starts a threaded server."""
    t = ThreadedServer(SlaveService, hostname = options.host,
        port = options.port, reuse_addr = True,
        authenticator = options.authenticator, registrar = options.registrar,
        auto_register = options.auto_register)
    t.logger.quiet = options.quiet
    if options.logfile:
        t.logger.console = open(options.logfile, "w")
    t.start()
    return t


def serveForking(options):
    """Starts a forking server."""
    t = ForkingServer(SlaveService, hostname = options.host,
        port = options.port, reuse_addr = True,
        authenticator = options.authenticator, registrar = options.registrar,
        auto_register = options.auto_register)
    t.logger.quiet = options.quiet
    if options.logfile:
        t.logger.console = open(options.logfile, "w")
    t.start()
    return t


def serveStdio(options):
    """Starts a shell based server."""
    origstdin = sys.stdin
    origstdout = sys.stdout
    if options.quiet:
        dev = os.devnull
    elif sys.platform == "win32":
        dev = "con:"
    else:
        dev = "/dev/tty"
    try:
        sys.stdin = open(dev, "r")
        sys.stdout = open(dev, "w")
    except (IOError, OSError):
        sys.stdin = open(os.devnull, "r")
        sys.stdout = open(os.devnull, "w")
    conn = rpyc.classic.connect_pipes(origstdin, origstdout)
    try:
        try:
            conn.serve_all()
        except KeyboardInterrupt:
            print "User interrupt!"
    finally:
        conn.close()
