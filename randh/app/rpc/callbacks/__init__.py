# =============================================================================
# $Id
# =============================================================================
# Module:   rh.app.rpc.callbacks
# Contacts: fxdev
# =============================================================================

"""Rhythm and Hues python rpc callbacks.

This module defines failure (possibly success in the future) callbacks for
scripts run over a port.  Users are welcome to import callbacks directly or use
the findCallbackByApp method which abstracts away all callbacks by finding one
associated with the application metatag or a default one.
"""

__version__ = "$Id: __init__.py,v 1.4 2011/09/07 23:54:33 tfan Exp $"

# System imports
import sys

# R&H imports
from rh.logutils import logWarning

# Generic error msg format
ERR_MSG_FMT = "RPC command:\n\n'{0} -port {1}' pid ({2})\n\nfailed!  Check shell!"
ERR_MSG_NOPORT_FMT = "RPC command:\n\n'{0}' pid ({1})\n\nfailed!  Check shell!"

# -----------------------------------------------------------------------------
#    Name: _buildErrMsg
#    Args: N/A
# Returns: String with the generic error message.
#  Raises: N/A
#    Desc: Returns a generic error message depending on whether or not a port
#          was supplied.
# -----------------------------------------------------------------------------
def _buildErrMsg(cmd, port, pid):
    # If we passed a port that had been opened
    if isinstance(port, int):
        return ERR_MSG_FMT.format(cmd, port, pid)

    return ERR_MSG_NOPORT_FMT.format(cmd, pid)


def houdiniCallback(cmd, port, pid):
    """The generic Houdini failure callback."""
    try:
        import hou
        errMsg = _buildErrMsg(cmd=cmd, port=port, pid=pid)
        sys.stderr.write(errMsg)
        hou.ui.displayMessage(errMsg, hou.severityType.Error)
    except ImportError:
        raise CallbackError('houdiniCallback run outside of Houdini!')


def defaultCallback(cmd, port, pid):
    """The generic application agnostic callback."""
    logWarning('Issuing default callback')
    errMsg = _buildErrMsg(cmd=cmd, port=port, pid=pid)
    sys.stderr.write(errMsg)


def findCallbackByApp(app):
    """Finds the appropriate callback by application."""
    if app == 'houdini':
        return houdiniCallback
    # default callback
    else:
        return defaultCallback


# =============================================================================
# EXCEPTIONS
# =============================================================================

class CallbackError(StandardError):
    """Base class callback related exceptions"""
    pass
