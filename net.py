# Socket wrapper copied from MechMania

import socket
import time

class SocketError(Exception):
    pass

# We send the length with each message to ensure that we don't
# accidentally get either part of a message or
# multiple messages strung together.
class SocketWrapper:
    def __init__(self, conn, timeout=0):
        self.conn = conn
        self.timeout = timeout
        if timeout > 0:
            #print 'Set socket timeout to', timeout
            self.conn.settimeout(timeout)

    def send(self, data):
        length = '%10d' % (len(data))
        try:
            self.conn.send(length)
            #print '>>> %s: %s' % (length, data)
            self.conn.send(data)
        except socket.error, socket.timeout:
            raise SocketError('Error sending data')

    def recv(self):
        try:
            starttime = time.time()
            LENSIZE = 10
            lenstr = ''
            while len(lenstr) != LENSIZE:
                lenstr = lenstr + self.conn.recv(LENSIZE - len(lenstr))
                if self.timeout > 0 and time.time() - starttime > self.timeout:
                    raise SocketError('recv took too long')

            packetsize = int(lenstr)
            packet = ''
            while len(packet) != packetsize:
                packet = packet + self.conn.recv(packetsize - len(packet))
                if self.timeout > 0 and time.time() - starttime > self.timeout:
                    raise SocketError('recv took too long')
            #print '<<< %s' % packet
            return packet
        except (ValueError, socket.error, socket.timeout), e:
            raise SocketError('Error or timeout receiving data')

    def close(self):
        # For completeness of wrapping API
        self.conn.close()
