import socket
import time
import random
import Queue
import gm

from score import *

class StopMessage(Exception):
    pass

# If we tried to sleep for exactly the right amount of time,
# we would eventually fall behind and send midi events late
SLEEP_ADJUST = .99

class InstrumentBase:
    def __init__(self, outq, controller_q, index):
        self.id = index
        self.tempo = 120
        self.name = 'Instrument %d' % index
        self.beat = 0
        # Queue to send midi events to
        self.outq = outq
        # Queue to send messages back to controller
        self.controller_q = controller_q
        # Incoming queue to receive commands
        self.cmd_q = Queue.Queue()
        self._instrument = 0
        self.velocity = 64
    
    def run(self):
        try:
            self._run()
        except StopMessage:
            print self.name, 'quitting'

    def _check_messages(self):
        try:
            msg = self.cmd_q.get_nowait()
        except Queue.Empty:
            pass
        else:
            try:
                handle_fn = getattr(self, 'handle_' + msg)
            except AttributeError:
                pass
            else:
                handle_fn()

    def handle_stop(self):
        raise StopMessage()

    def handle_hurry(self):
        pass

    def handle_restart(self):
        pass

    def set_instrument(self, pgm):
        while not gm.is_valid(pgm):
            pgm = random.randrange(121)
        self._instrument = pgm
        self.outq.put((self.beat, self.id, 'instrument', pgm))

    def set_tempo(self, new_tempo):
        self.tempo = new_tempo

    def set_velocity(self, veloc):
        self.velocity = veloc
        self.outq.put((self.beat, self.id, 'set_velocity', veloc))

class Metronome(InstrumentBase):
    def __init__(self, outq, controller_q, index=0):
        InstrumentBase.__init__(self, outq, controller_q, index)
        self.name = 'Metronome'
        # fake this since we don't have chords
        self.note_list = [
            Measure("c''8 c''8 c''8 c''8 c''8 c''8 c''8 c''8"),
            Measure("c'''8 c'''8 c'''8 c'''8 c'''8 c'''8 c'''8 c'''8")]

    def _run(self):
        num_beats = self.note_list[0].length
        while True:
            self._check_messages()
            for notes in self.note_list:
                note_cmd = (self.beat, self.id, 'notes', notes)
                print 'Sending %d, %d, %s, %s' % note_cmd
                self.outq.put(note_cmd)
            self.beat += num_beats
            time.sleep(60*SLEEP_ADJUST*num_beats / self.tempo)

    def set_tempo(self, new_tempo):
        self.tempo = new_tempo
        self.outq.put((self.beat, self.id, 'tempo', new_tempo))

    def set_volume(self, new_volume):
        self.outq.put((self.beat, self.id, 'volume', new_volume))

class Instrument(InstrumentBase):
    def __init__(self, outq, controller_q, score, index):
        InstrumentBase.__init__(self, outq, controller_q, index)
        self.score = score # List of measures
        self.score_idx = 0
        self.repeat_lbound = 4
        self.repeat_ubound = 16
        self.done = False
        self.hurry = False

    def _run(self):
        print self.name, 'running'
        while self.score_idx < len(self.score):
            num_beats = self.score[self.score_idx].length
            ubound = int(self.repeat_ubound*16.0/(num_beats+1))
            ubound = max(self.repeat_lbound+1, ubound)
            if self.score_idx >= len(self.score) - 1:
                repeat = 40.0 / num_beats
            else:
                repeat = random.randrange(self.repeat_lbound, ubound)
            self._send_info_event()
            for i in range(repeat):
                self._send_current_measure()
                time.sleep(60*SLEEP_ADJUST*num_beats / self.tempo)
                self._check_messages()
                if self.hurry:
                    self.hurry = False
                    break
                self.beat += num_beats
            if self.score_idx >= len(self.score) - 1:
                self.done = True
                #self.set_velocity(self.velocity / 2)
                self.controller_q.put('done')
            else:
                self.score_idx += 1

    def _send_current_measure(self):
        note_cmd = (self.beat, self.id, 'notes', self.score[self.score_idx])
        print 'Sending %d, %d, %s, %s' % note_cmd
        #note_str = '%d:%s:%s' % note_cmd
        self.outq.put(note_cmd)

    def _send_info_event(self):
        info_cmd = (self.beat, self.id, 'location', self.score_idx)
        self.outq.put(info_cmd)

    def get_info(self):
        return (self.id, self._instrument, self.name, self.velocity)

    def handle_hurry(self):
        print self.id, 'hurrying up'
        self.hurry = True

    def handle_restart(self):
        self.set_instrument(-1) # random
        self.done = False
        self.score_idx = 0

