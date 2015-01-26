import re

def parse(file_name):
    return [Measure(line) for line in open(file_name)
            if len(line) > 0 and line[0] != '#']

class Note:
    def __init__(self, pitch, duration):
        self.pitch = pitch
        self.duration = duration # 1 = whole note, 2 = half, etc.

    def __str__(self):
        return '%d %d' % (self.pitch, self.duration)

    # Note pattern a b c d e f g
    _pitch_map = [0,2,3,5,7,8,10]
    _pitch_map = [p - 3 for p in _pitch_map]
    # TODO: .
    _pattern = r"([a-gr])(es|is)?(,*|'*)(\d+)(\.*)"
    @staticmethod
    def from_str(str):
        parsed = re.match(Note._pattern, str)
        assert parsed
        note, alter, octave, dur, dots = parsed.groups()
        octave_mod = 5 # the middle octave
        if octave:
            if octave[0] == "'":
                octave_mod += len(octave)
            else:
                octave_mod -= -len(octave)
        if note == 'r':
            pitch = 0
        else:
            pitch = octave_mod*12 + Note._pitch_map[ord(note) - ord('a')]
            if alter == 'is':
                pitch += 1
            elif alter == 'es':
                pitch -= 1
        dur = float(dur)
        if dots:
            dur = 1.0/dur
            for i in range(len(dots)):
                dur += dur/(i+2)
            dur = 1.0/dur
        return Note(pitch, float(dur))

class Measure:
    def __init__(self, s):
        self.orig_str = s
        self.events = [Note.from_str(note) for note in s.split()]
        self.length = sum(4.0 / note.duration for note in self.events)

    def __str__(self):
        return ' | '.join([str(e) for e in self.events])
