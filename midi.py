import pyalsa.alsaseq as alsaseq
import Queue
import random
from net import *
import socket
import threading
import simplejson

# Lag everything by a few quarter notes to reduce drop-outs
DELAY = 3*96

def instrument_channel(instr):
    return instr%16
    #return 0

def instrument_port(instr):
    # Timidity listens on 4 ports, each with 16 channels
    return min(3, instr/16)

class Sequencer:
    def __init__(self, name, connect=False):
        self.seq = alsaseq.Sequencer(clientname=name,
                                     streams=alsaseq.SEQ_OPEN_OUTPUT,
                                     mode=alsaseq.SEQ_BLOCK)
        self.outq = self.seq.create_queue()
        self.inq = Queue.Queue()
        self.velocity = {} # map instr_id -> key velocity

        self.cid, self.pid = 0, 0
        if connect:
            for cname, cid, ports in self.seq.connection_list():
                if cname == 'TiMidity':
                    pname, pid, pconns = ports[0]
                    print 'Found timidity at %d:%d' % (cid, pid)
                    #self.seq.connect_ports((self.cid, self.port),
                    #                       (cid, pid))
                    self.cid = cid
                    self.pid = pid
        if self.cid == 0:
            self.pid = self.seq.create_simple_port(
                'out', alsaseq.SEQ_PORT_TYPE_APPLICATION,
                alsaseq.SEQ_PORT_CAP_READ | alsaseq.SEQ_PORT_CAP_SUBS_READ)
            self.cid = self.seq.client_id

    def listen(self):
        self.seq.start_queue(self.outq)
        # Defaults to tempo=120, ppq=96 (pulses per quarter note)
        self.tempo, self.ppq = self.seq.queue_tempo(self.outq)
        print 'tempo=%d, ppq=%d' % (self.tempo, self.ppq)
        try:
            while True:
                incoming = self.inq.get()
                if incoming == 'stop':
                    break
                beat, instr_id, event, data = incoming
                handle_fn = getattr(self, event + '_event')
                handle_fn(beat, instr_id, data)
        finally:
            self.seq.sync_output_queue()
            self.seq.stop_queue(self.outq)
            self.seq.delete_queue(self.outq)

    def notes_event(self, beat, instr_id, measure_data):
        # TODO: take advantage of ports 128:1, 128:2, 128:3
        channel = instrument_channel(instr_id)
        event = alsaseq.SeqEvent(alsaseq.SEQ_EVENT_NOTE)
        start_tm = beat * self.ppq # Beginning of measure, in ticks
        try:
            base_velocity = self.velocity[instr_id]
        except KeyError:
            base_velocity = 64
        for note in measure_data.events:
            ticks = int(4 * self.ppq / note.duration)
            if instr_id == 0:
                # Don't jitter the metronome!
                jitter = 0
            else:
                jitter_dist = int(32 / note.duration)
                jitter = random.randrange(jitter_dist)
            if note.pitch != 0:
                event.dest = (self.cid, instrument_port(instr_id)) #self.pid)
                event.queue = self.outq
                event.time = start_tm + jitter + DELAY
                veloc = base_velocity + random.randrange(10)
                dur = ticks + jitter
                event.set_data({'note.note': note.pitch,
                                'note.velocity': veloc,
                                'note.duration': ticks - jitter,
                                'note.off_velocity': veloc,
                                'note.channel': channel})
                #print 'event:', event, event.get_data()
                self.seq.output_event(event)
            start_tm += ticks
        self.seq.drain_output()

    def instrument_event(self, beat, instr_id, new_instrument):
        event = alsaseq.SeqEvent(alsaseq.SEQ_EVENT_PGMCHANGE)
        event.dest = (self.cid, instrument_port(instr_id))
        event.queue = self.outq
        event.time = beat * self.ppq
        event.set_data({'control.value': new_instrument,
                        'control.channel': instrument_channel(instr_id)})
        self.seq.output_event(event)

    def set_velocity_event(self, beat, instr_id, velocity):
        'velocity %d -> %d' % (instr_id, velocity)
        self.velocity[instr_id] = int(velocity)

    def tempo_event(self, beat, instr_id, new_tempo):
        # Ignore beat -- happens immediately
        self.tempo = new_tempo
        self.seq.queue_tempo(self.outq, new_tempo)

    def volume_event(self, beat, instr_id, new_volume):
        # Global volume
        event = alsaseq.SeqEvent(alsaseq.SEQ_EVENT_CONTROLLER)
        event.dest = (self.cid, instrument_port(instr_id))
        event.queue = self.outq
        event.time = beat * self.ppq
        event.set_data({'control.param': 7,
                        'control.value': int(new_volume),
                        'control.channel': 0})
        self.seq.output_event(event)

    # Ignore score follower events
    def location_event(self, beat, instr_id, *args):
        pass

class SocketSequencer:
    def __init__(self, port=8001):
        self.inq = Queue.Queue()
        self.sock = socket.socket()
        # Prevent "address already in use" errors
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', port))
        self.sock.listen(2)
        self.clients = []
        t = threading.Thread(target=self.listen_socket)
        t.setDaemon(1)
        t.start()

    def listen_socket(self):
        while True:
            client, addr = self.sock.accept()
            self.clients.append(SocketWrapper(client))

    def listen(self):
        while True:
            incoming = self.inq.get()
            if incoming == 'stop':
                break
            beat, instr_id, event, data = incoming
            try:
                handle_fn = getattr(self, event + '_event')
            except AttributeError:
                continue
            handle_fn(beat, instr_id, data)

    def location_event(self, beat, instr_id, location):
        self.send_all((instr_id, 'location', location))
    
    def set_velocity_event(self, beat, instr_id, velocity):
        self.send_all((instr_id, 'volume', velocity))

    def send_all(self, data):
        for i, client in enumerate(self.clients):
            if client is None:
                continue
            data_str = simplejson.dumps(data)
            try:
                client.send(data_str)
            except SocketError:
                self.clients[i] = None

class CompositeSequencer:
    def __init__(self, sinks):
        self.inq = Queue.Queue()
        self.sinks = [s for s in sinks if s is not None]

    def listen(self):
        for sink in self.sinks:
            threading.Thread(target=sink.listen).start()
        try:
            while True:
                incoming = self.inq.get()
                if incoming == 'stop':
                    break
                for sink in self.sinks:
                    sink.inq.put(incoming)
        finally:
            for sink in self.sinks:
                sink.inq.put('stop')

class DummySequencer:
    def __init__(self):
        self.inq = Queue.Queue()

    def listen(self):
        while True:
            incoming = self.inq.get()
            if incoming == 'stop':
                break
            measure, event, data = incoming
            handle_fn = getattr(self, event + '_event')
            handle_fn(measure, data)

    def notes_event(self, measure, measure_data):
        print 'DummySequencer: measure', measure
        print 'DummySequencer: data', measure_data

def main():
    seq = Sequencer('in_c')
    seq.listen()
