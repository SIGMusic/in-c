import midi
import threading
import gm
from SimpleXMLRPCServer import SimpleXMLRPCServer
import signal # ensures main thread always gets KeyboardInterrupt

from instrument import *
import score

class Controller:
    def __init__(self):
        self.n = 6
        self.score = score.parse('in_c_score')
        try:
            midi_sink = midi.Sequencer('in_c', connect=True)
        except midi.alsaseq.SequencerError:
            midi_sink = midi.DummySequencer()
        #try:
        socket_sink = midi.SocketSequencer()
        #except midi.socket.error:
        #    print 'cannot connect to gui'
        #    socket_sink = None
        self.note_sink = midi.CompositeSequencer([midi_sink, socket_sink])
        self.msg_q = Queue.Queue()

    # This is really a public method...
    # we just don't want to expose it to xml-rpc.
    def _start(self):
        threading.Thread(target=self.note_sink.listen).start()
        self.metronome = Metronome(self.note_sink.inq, self.msg_q)
        self.real_instrs = [Instrument(self.note_sink.inq, self.msg_q,
                                       self.score, i+1)
                            for i in range(self.n)]
        self.instrs = [self.metronome] + self.real_instrs
        self.metronome.set_instrument(1)
        for instr in self.real_instrs:
            instr.set_instrument(random.randrange(121))
        for instr in self.instrs:
            threading.Thread(target=instr.run).start()
        t = threading.Thread(target=self._monitor)
        t.setDaemon(1)
        t.start()

    def _monitor(self):
        try:
            while True:
                self._wait_for_finish()
                for instr in self.real_instrs:
                    instr.cmd_q.put('restart')
                # Give each instrument a chance to restart
                # (so we don't incorrectly send hurry up messages
                # and so forth)
                time.sleep(10)
        except StopMessage:
            pass

    def _avg_location(self):
        return sum(instr.score_idx for instr in self.real_instrs) \
               / float(self.n)
        
    def _wait_for_finish(self):
        # Wait for instruments to finish
        # We use a timeout on msg_q.get() because otherwise
        # python ignores Control-C
        done = 0
        while done < self.n:
            avg = self._avg_location()
            for instr in self.real_instrs:
                if instr.score_idx < avg - 4:
                    print 'hurrying instr', instr.id
                    instr.cmd_q.put('hurry')
            try:
                msg = self.msg_q.get(timeout=1)
                if msg == 'done':
                    print done, 'instruments done'
                    done += 1
                elif msg == 'stop':
                    raise StopMessage()
            except Queue.Empty:
                continue
        print 'all instruments done'
        
    def set_tempo(self, tempo):
        if tempo < 40 or tempo > 300:
            return False
        for instr in self.real_instrs:
            instr.set_tempo(tempo)
        self.metronome.set_tempo(tempo)
        return True

    def set_volume(self, volume):
        self.metronome.set_volume(volume)
        return True

    def add_instrument(self, pgm=-1):
        self.n += 1
        instr = Instrument(self.note_sink.inq, self.msg_q,
                           self.score, self.n)
        self.instrs.append(instr)
        self.real_instrs.append(instr)
        instr.set_instrument(pgm)
        # TODO: once we have logic to make instrs stay together,
        # this should be unnecessary -- it will speed itself up
        clonee = self.instrs[self.n-1]
        instr.score_idx = clonee.score_idx
        instr.beat = clonee.beat
        threading.Thread(target=instr.run).start()
        return instr.get_info()

    def set_instrument_pgm(self, instr_id, pgm):
        if not gm.is_valid(pgm):
            return False
        self.instrs[instr_id].set_instrument(pgm)
        return True

    def set_instrument_vol(self, instr_id, vol):
        assert 0 <= vol < 128
        self.instrs[instr_id].set_velocity(vol)
        return True

    def hurry_instrument(self, instr_id):
        self.instrs[instr_id].cmd_q.put('hurry')
        return True

    def instr_info(self, instr_id):
        return self.instrs[instr_id].get_info()
    
    def all_instrument_info(self):
        return [instr.get_info() for instr in self.real_instrs]
        #d = {}
        #for instr in self.real_instrs:
        #    d[instr.id] = instr.get_info()
        #return d
    
if __name__=='__main__':
    c = Controller()
    server = SimpleXMLRPCServer(('localhost', 8000))
    server.register_introspection_functions()
    server.register_instance(c)
    try:
        c._start()
        #c._join()
        server.serve_forever()
    finally:
        print 'sending shutdown messages'
        for instr in c.instrs:
            instr.cmd_q.put('stop')
        c.note_sink.inq.put('stop')
