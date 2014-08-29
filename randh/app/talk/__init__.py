# =============================================================================
# Module: rh.app.talk
# Contacts: Josh Tomlinson
# =============================================================================
"""Execute arbitrary commands inside of external applications

Classes:
    SessionBase - The base class for all session objects.
    PortSession - Sessions defined by connecting to a host and port.
    FileSession - Sessions defined by a opening a pipe to a shell command.
    Session - Factory class creates appropriate type based on supplied args.
    SessionError - Exception class for session errors.

This module is used to create pipe or socket connections between applications.  
You create a Session() object and pass commands into it. 

rh.app.talk understands these languages:

    parsley hscript mel 

Here's an example of how to create a pipe to a voodoo file.

    from rh.app.talk import Session

    s = Session(command='/muse/bin/voodoo', 
                echo=True, 
                echoCmd=True, 
                language='parsley')

    s.command('obj ball/s -create')
    s.command('obj cube/s -create')
    s.command('write myfile.vdu')
    s.close()

Here's an example of how to open a pipe to hscript.

    from rh.app.talk import Session
    
    s = Session(command='/usr/apps/bin/hscript',
                language='hscript')
    dir = s.command('oppwd')
    s.close()

Here's an example of how to create a socket connection to a parsley app

    from rh.app.talk import Session

    s = Session(host='localhost',
                port=8663,
                echo=True, 
                echoCmd=True, 
                language='parsley')

    objects = s.command('obj * -ls name')
    s.close

Here's an example of how to create a socket connection to an hscript app

    from rh.app.talk import Session

    s = Session(host='localhost',
                port=8663,
                echo=True, 
                echoCmd=True, 
                language='hscript')

    oplist = s.command('opls')
    s.close()

"""

# =============================================================================
# BASE CLASS 
# =============================================================================
class SessionBase(object):
    """Base class for all Session objects.
    
    Instance attributes:
        (bool) echo: If true, print cmd output to stdout.
        (bool) echoCmd: If true, print cmd to stdout before sending to app.
        (string) lastCmd: The last command sent to the application.
        (string) lastResponse: The last response from the application.
    
    The SessionBase object provides a base class with functionality common to
    all Session objects.  
    
    """

    # str used when checking if the application is done sending a response
    _DONE_STR = 'DONEXXX' #pylint: disable=W0511

    # this dict is used to check supported languages.  it houses the 
    # commands to send to check for a complete response and for quitting
    # the application 
    _LANGUAGE_INFO = {
        'parsley': {
            'done': 'echo %s' % (_DONE_STR),
            'quit': 'quit',
        },
        'hscript': {
            'done': 'echo %s' % (_DONE_STR),
            'quit': 'quit',
        },
        'mel': {
            'done': 'print "%s\\n"' % (_DONE_STR),
            'quit': 'quit -f',
        },
    }

    # -------------------------------------------------------------------------
    #    Name: _validateCommonArgs()
    #    Args: (dict) args
    # Returns: n/a
    #  Raises: SessionError - if args cannot be validated properly
    #    Desc: Validate supplied args common to all Session types.
    # -------------------------------------------------------------------------
    def _validateCommonArgs(self, args):
        # ---- echo - default is False

        if 'echo' in args.keys():
            if args['echo']:
                self.echo = True
            else:
                self.echo = False
        else:
            self.echo = False

        # ---- echoCmd - default is False

        if 'echoCmd' in args.keys():
            if args['echoCmd']:
                self.echoCmd = True
            else:
                self.echoCmd = False
        else:
            self.echoCmd = False

        # ---- language - required

        if 'language' in args.keys():

            # make sure the supplied language is supported
            if args['language'] in self.__class__._LANGUAGE_INFO.keys():
                self._language = args['language']     
            else:
                raise SessionError('Supplied language is unknown.')
        else:
            raise SessionError('All sessions require a language.')

        # ---- reader - required
            
        if 'reader' in args.keys():
            self._reader = args['reader']
        else:
            raise SessionError('No file reader supplied to constructor.')

        # ---- writer - required

        if 'writer' in args.keys():
            self._writer = args['writer']
        else:
            raise SessionError('No file writer supplied to constructor.')
            
    def __init__(self, args):
        """Initialize a SessionBase object with the supplied arguments.
        
        Args:
            (dict) args: Dictionary of options for creation.  Valid keys are:
                echo=(bool): Optional value to echo the output of commands. 
                echoCmd=(bool): Optional value to echo the command itself.
                language=(str): Required language of the commands.
                reader=(file): Required file handle for reading.
                writer=(file): Required file handle for writing. 

        Raises:
            SessionError: Raised when any of the following criteria is met:
                * No reader supplied
                * No writer supplied
                * No language supplied
                * Supplied language is unsupported
                * Problem communicating with the session.
                * Failure to receive output from the session
        
        Initializes a SessionBase object based on the supplied argument 
        dictionary.  The dictionary must contain a file handle for reading, 
        a file handle for writing, and a command language.  

        """

        # set up some defaults for our instance attributes
        self._language = None
        self._reader = None
        self._writer = None
        self.echo = False
        self.echoCmd = False

        self._validateCommonArgs(args)

        # initialize the last command and response attributes to None
        self.lastCmd = None
        self.lastResponse = None

        # launching an app can send data to stdout or stderr.  
        # go ahead and receive all that output and forget about it
        self._receive()
        
    # -------------------------------------------------------------------------
    #    Name: _preCommand()
    #    Args: (str) cmd - command string
    # Returns: n/a
    #  Raises: n/a
    #    Desc: Handle tasks common to all sessions before cmd is executed.
    # -------------------------------------------------------------------------
    def _preCommand(self, cmd):
        if self.echoCmd:
            print cmd
       
    # -------------------------------------------------------------------------
    #    Name: _postCommand()
    #    Args: (str) cmd - command string
    #          (str) output - output printed as a result of cmd
    # Returns: n/a
    #  Raises: n/a
    #    Desc: Handle tasks common to all sessions after command is executed.
    # -------------------------------------------------------------------------
    def _postCommand(self, cmd, output):
        if self.echo:
            print output

        # remember the last command and response
        self.lastCmd = cmd
        self.lastResponse = output

    # -------------------------------------------------------------------------
    #    Name: _send()
    #    Args: (str) cmd - command string
    # Returns: n/a
    #  Raises: SessionError
    #    Desc: Send the supplied command to the session.
    # -------------------------------------------------------------------------
    def _send(self, cmd):
        # make sure the file is still open
        if self._writer.closed:
            raise SessionError('Session has closed unexpectedly.')
        
        # attempt the write
        try: 
            self._writer.write("%s\n" % (cmd))
        except IOError as (_, errMsg):
            raise SessionError('Failed to write to application: %s' % (errMsg))

        # must call flush for file objects from socket.makefile() 
        try:
            self._writer.flush()
        except:
            raise SessionError('Problem communicating with session')

    # -------------------------------------------------------------------------
    #    Name: _receive()
    #    Args: n/a
    # Returns: (str) output
    #  Raises: SessionError
    #    Desc: Receive output from the session.
    # -------------------------------------------------------------------------
    def _receive(self):
        doneStr = self.__class__._DONE_STR
        doneCmd = self.__class__._LANGUAGE_INFO[self._language]['done']

        # send the command to mark the end of our commands.
        self._send(doneCmd)

        output = ''

        while True:

            # make sure the file is still open
            if self._reader.closed:
                raise SessionError('Session has closed unexpectedly.')

            # read a line from the reader file handle
            try: 
                line = self._reader.readline()
            except IOError as (_, errMsg):
                raise SessionError('Failed to read from application: %s' % 
                                   (errMsg))
            
            # TODO - deal with hscript stuff from AppTalk.pm

            # we've hit the end of the commands, process appropriately
            if doneStr in line:
                # strip off the done string and any newlines, then add the 
                # rest to the output as long as its not empty
                line = line.replace(doneStr, '')
                line = line.rstrip()
                if line is not '':
                    output += line
                break
            else:
                output += line

        return output

    def command(self, cmd):
        """Send the supplied command to the Session.

        Args:
            (str) cmd: The command to execute in the session.

        Raises:
            SessionError: Raised when any of the following criteria is met:
                * Session closed unexpectedly
                * Failure to send the command to the session
                * Problem communicating with the session.
                * Failure to receive output from the session

        Executes the supplied command in the session.  Automatically appends
        a newline character to the command.  Handles echoing the command and
        the output if the appropriate instance attributes are set to True.

        """
        
        self._preCommand(cmd)
        self._send(cmd)

        # read in the results of the commands
        output = self._receive()
        
        self._postCommand(cmd, output)

        return output

    def connected(self):
        """Return True if reader and writer handles are open."""

        if not self._reader.closed and not self._writer.closed:
            return True
        else:
            return False
        
    def __del__(self):
        """Ensure the file handles are closed on destruction."""

        self.close()
    

    def close(self):
        """Closes the session connections to the application."""

        if not self._reader.closed:
            self._reader.close()

        if not self._writer.closed:
            self._writer.close()

# =============================================================================
# CONNECT VIA COMMAND (subprocess)
# =============================================================================
class FileSession(SessionBase):
    """Run a command and connect to the subprocess' stdin/out/err."""

    # -------------------------------------------------------------------------
    #    Name: _validateArgs()
    #    Args: (dict) args
    # Returns: n/a
    #  Raises: SessionError
    #    Desc: Validate arguments for file sessions.
    # -------------------------------------------------------------------------
    def _validateArgs(self, args):
        # ---- command - required

        if 'command' in args.keys():
            self._command = args['command']
        else:
            raise SessionError('File session creation requires a command.')

    def __init__(self, args):
        """Initialize a FileSession object with the supplied arguments.
        
        Args:
            (dict) args: Dictionary of options for creation.  Valid keys are:
                command=(str): Required command str to execute subprocess.

        Raises:
            SessionError: Raised when any of the following criteria is met:
                * Failed to open pipe(s) to the subprocess
        
        Initializes a FileSession object based on the supplied argument 
        dictionary.  The dictionary must contain a command string.

        """

        import subprocess

        # set up some defaults for our instance attributes
        self._command = None

        self._validateArgs(args)     

        # open up a pipe to the supplied command.  create new pipes for 
        # stdin and stdout.  also redirect stderr to stdout so that we get 
        # that too.  voodoo, for example, outputs to both stderr and stdout
        try: 
            pipe = subprocess.Popen(self._command, shell=True,
                                    stdin=subprocess.PIPE, 
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        except OSError as (_, errMsg): 
            raise SessionError('Failed to open pipe: %s' % (errMsg))

        # the subprocess pipe has stdout and stdin attributes that we can use
        args['reader'] = pipe.stdout
        args['writer'] = pipe.stdin

        # call the super class init with the reader and writer to populate 
        # the common session attributes.
        super(FileSession, self).__init__(args)

    def close(self):
        """Quit the application and close the file session."""
    
        # send the quit command to the application if the writer is open
        if not self._writer.closed:
            quitCmd = self.__class__._LANGUAGE_INFO[self._language]['quit']
            self._send(quitCmd)

        # make sure the file handles are closed
        super(FileSession, self).close()

# =============================================================================
# CONNECT VIA PORT (socket)
# =============================================================================
class PortSession(SessionBase):
    """Connect to a port for sending/receiving commands to an app."""

    # -------------------------------------------------------------------------
    #    Name: _validateArgs()
    #    Args: (dict) args
    # Returns: n/a
    #  Raises: SessionError
    #    Desc: Validate arguments for port sessions.
    # -------------------------------------------------------------------------
    def _validateArgs(self, args):
        # ---- port - required as an int

        if 'port' in args.keys():
            
            # ensure port is an integer
            try:
                int(args['port'])
            except:
                raise SessionError('Supplied port is not an integer.')
            
            self.port = args['port']
        else:
            raise SessionError('Port session creation requires a port number.')

        # ---- host - optional, defaults to 'localhost'

        if 'host' in args.keys():
            self.host = args['host']
        else:
            self.host = 'localhost'

    def __init__(self, args):
        """Initialize a PortSession object with the supplied arguments.
        
        Args:
            (dict) args: Dictionary of options for creation.  Valid keys are:
                host=(str): Optional connection host.  Default is localhost
                port=(int): Required port number on the host.

        Raises:
            SessionError: Raised when any of the following criteria is met:
                * No port supplied
                * Supplied port is not an integer
                * Failed to connect to host:port
        
        Initializes a FileSession object based on the supplied argument 
        dictionary.  The dictionary must contain a command string.

        """
        import socket

        # set up some defaults for our instance attributes
        self.host = None
        self.port = None

        self._validateArgs(args)     

        # connect to the supplied host and port
        try:
            s = socket.socket()
            s.connect((self.host, self.port))
        except socket.error:
            raise SessionError('Failed to connect to: %s:%s' % 
                (self.host, str(self.port)))

        # create read/write file handles from the socket 
        args['writer'] = s.makefile('wb')
        args['reader'] = s.makefile('rb')

        # no need to keep the socket around, the file handles are separate 
        s.close()

        # call the super class init with the reader and writer to populate 
        # the common session attributes.
        super(PortSession, self).__init__(args)

# =============================================================================
# FACTORY CLASS
# =============================================================================
class Session(object):
    """Factory class returns an object based on the supplied args."""

    def __new__(cls, **kwargs):
        """Return a Session based on the supplied arguments.
        
        Args:
            (dict) kwargs: Dictionary of options for creation.  Valid keys are:
                Port Connections:
                  host=(str): Optional connection host.  Default is localhost
                  port=(int): Required port number on the host.
                File Connections:
                  command=(str): Required command str to execute subprocess.
                All Connection Types:
                  language=(str): Required language of the commands.
                  echo=(bool): Optional value to echo the command output. 
                  echoCmd=(bool): Optional value to echo the command itself.

        Raises:
            SessionError: Raised when any of the following criteria is met:
                * Could not determine session type from the supplied args
        
        Return a session based on the supplied arguments.  The argument 
        dictionary supplied must contain either a port argument or a command
        argument.  All sessions require a language argument.  

        """
    
        args = kwargs.keys()
    
        if 'port' in args:
            return PortSession(kwargs)
        elif 'command' in args:
            return FileSession(kwargs)
        else:
            raise SessionError('Could not determine session type from args.')

# =============================================================================

class SessionError(Exception):
    """Exception class for application communication sessions."""

    def __init__(self, msg, *args, **kwargs):
        super(SessionError, self).__init__(*args, **kwargs)
        self.msg = msg

    def __str__(self):
        return self.msg

