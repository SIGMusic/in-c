import gtk
import gobject
import xmlrpclib
import gm
import simplejson
import socket
import net
import sys
import threading
import random

import score

server = None
instrs = {}

class InstrumentInfo:
    def __init__(self, instr_id, pgm, name, velocity):
        self.id = instr_id
        self.pgm = pgm
        self.name = name
        self.velocity = velocity
        self.location = -1
        self.x_offset = random.randrange(-4,4)
        self.color = (random.randrange(65535),
                      random.randrange(65535),
                      random.randrange(65535))
        # Set by the GUI
        self.gtk_color = None
        self.name_lbl = None
        self.volume_adj = None
        self.pgm_choose = None

    def html_color(self):
        scaled = tuple(val/256 for val in self.color)
        return '%02x%02x%02x' % scaled

    def set_velocity(self, velocity):
        self.velocity = velocity
        self.volume_adj.set_value(self.velocity)

    def set_pgm(self, pgm):
        self.pgm = pgm
        self.pgm_choose.set_active(
            gm.gm_name_list.index(gm.gm_names[pgm]))


def midi_adj(vertical=True):
    adj = gtk.Adjustment(value=80, lower=0, upper=127,
                         step_incr=1, page_incr=10)
    if vertical:
        scale = gtk.VScale(adjustment=adj)
        scale.set_inverted(True)
    else:
        scale = gtk.HScale(adjustment=adj)
        scale.set_value_pos(gtk.POS_RIGHT)
    scale.set_update_policy(gtk.UPDATE_DELAYED)
    return adj, scale

class ControlsWindow:
    def __init__(self):
        self.wnd = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.wnd.set_title('"In C" In C (... in Python!)')
        self.wnd.set_border_width(5)
        self.wnd.connect('destroy', self.destroy)
        #self.wnd.set_size_request(300,300)
        #self.wnd.set_default_size(300,300)

        tempo_adj = gtk.Adjustment(value=120, lower=40, upper=300,
                                   step_incr=1, page_incr=10)
        tempo = gtk.VScale(adjustment=tempo_adj)
        tempo.set_update_policy(gtk.UPDATE_DELAYED)
        tempo.set_inverted(True)
        tempo.set_size_request(-1,120)
        tempo_adj.connect('value_changed', self.tempo_changed)
        volume_adj, volume = midi_adj()
        volume.set_size_request(-1,120)
        volume_adj.connect('value_changed', self.volume_changed)

        master_table = gtk.Table(rows=2, columns=2,
                                 homogeneous=False)
        tempo_lbl = gtk.Label('Tempo')
        volume_lbl = gtk.Label('Volume')
        master_table.attach(tempo_lbl, 0, 1, 0, 1,
                            yoptions=gtk.SHRINK,
                            xoptions=gtk.SHRINK,
                            xpadding=5, ypadding=5)
        master_table.attach(volume_lbl, 1, 2, 0, 1,
                            xpadding=5, ypadding=5)
        master_table.attach(tempo, 0, 1, 1, 2,
                            yoptions=gtk.EXPAND|gtk.FILL)
        master_table.attach(volume, 1, 2, 1, 2,
                            yoptions=gtk.EXPAND|gtk.FILL)

        self.instr_vbox = gtk.VBox()
        self.draw_instruments(self.instr_vbox)
        self.add_button = gtk.Button('Add instrument', gtk.STOCK_ADD)
        self.add_button.connect('clicked', self.add_instrument)
        self.instr_vbox.pack_start(self.add_button)
        
        instr_frame = gtk.Frame(label='Instruments')
        instr_frame.add(self.instr_vbox)
        
        master_frame = gtk.Frame(label='Master')
        master_frame.add(master_table)
        
        controls_vbox = gtk.VBox()
        controls_vbox.pack_start(master_frame, expand=False)
        controls_vbox.pack_start(instr_frame)
        self.wnd.add(controls_vbox)
        self.wnd.show_all()

    def draw_instruments(self, parent):
        global instrs
        for instr_id, pgm, name, velocity in server.all_instrument_info():
            instr = InstrumentInfo(instr_id, pgm, name, velocity)
            instrs[instr_id] = instr
            self.draw_instrument(parent, instr)

    def draw_instrument(self, parent, instr):
        hb = gtk.HBox()
        instr.name_lbl = gtk.Label()
        instr.name_lbl.set_use_markup(True)
        instr.name_lbl.set_markup('<span color="#%s">%s</span>' % (
            instr.html_color(), instr.name))
        instr.name_lbl.set_size_request(200, -1)
        hb.pack_start(instr.name_lbl)
        
        hb.pack_start(instr.name_lbl)
        pgm_choose = gtk.combo_box_new_text()
        instr.pgm_choose = pgm_choose
        pgm_choose.set_wrap_width(5)
        for instr_name in gm.gm_name_list:
            pgm_choose.append_text(instr_name)
        instr.set_pgm(instr.pgm)
        pgm_choose.connect('changed', self.instr_pgm_changed, instr.id)
        hb.pack_start(pgm_choose)
        
        vol_vbox = gtk.VBox()
        vol_lbl = gtk.Label('Volume')
        vol_vbox.pack_start(vol_lbl)
        instr.volume_adj, volume = midi_adj(vertical=False)
        instr.set_velocity(instr.velocity)
        instr.volume_adj.connect('value_changed', self.instr_volume_changed,
                                 instr.id)
        volume.set_size_request(120, -1)
        vol_vbox.pack_start(volume)
        hb.pack_start(vol_vbox)

        hurry_btn = gtk.Button('Hurry')
        hurry_btn.connect('clicked', self.instr_hurry, instr.id)
        hb.pack_start(hurry_btn)
        
        parent.pack_start(hb)
        self.wnd.show_all()

    def add_instrument(self, btn):
        instr = InstrumentInfo(*server.add_instrument())
        instrs[instr.id] = instr
        self.draw_instrument(self.instr_vbox, instr)
        self.instr_vbox.reorder_child(self.add_button, -1)

    def tempo_changed(self, tempo_adj):
        server.set_tempo(tempo_adj.value)

    def volume_changed(self, volume_adj):
        server.set_volume(volume_adj.value)

    def instr_volume_changed(self, volume_adj, instr_id):
        server.set_instrument_vol(instr_id, volume_adj.value)

    def instr_pgm_changed(self, pgm_box, instr_id):
        model = pgm_box.get_model()
        idx = pgm_box.get_active()
        if idx >= 0:
            active_text = model[idx][0]
            server.set_instrument_pgm(instr_id, gm.gm_numbers[active_text])

    def instr_hurry(self, hurry_btn, instr_id):
        server.hurry_instrument(instr_id)
    
    def destroy(self, widget, data=None):
        gtk.main_quit()

class ScoreListener:
    def __init__(self, server_addr, port):
        self.score = score.parse('in_c_score')
        self.measure_height = 18
        
        conn = socket.socket()
        conn.connect((server_addr, port))
        self.conn = net.SocketWrapper(conn, timeout=10)
        gobject.io_add_watch(self.conn.conn, gobject.IO_IN, self.recv)

        self.wnd = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.wnd.set_title('Score Follower')
        self.area = gtk.DrawingArea()
        self.w = 400
        self.h = self.measure_height*len(self.score)
        self.area.set_size_request(self.w, self.h)
        self.area.connect('expose-event', self.draw)
        self.wnd.add(self.area)
        self.area.show()
        self.wnd.show_all()
        self.layout = self.area.create_pango_layout('')
        self.colormap = self.area.get_colormap()
        self.white = self.colormap.alloc_color('white')
        #self.layout.set_height(16)
        
    def draw(self, area, event):
        y = 0
        style = self.area.get_style()
        gc = style.fg_gc[gtk.STATE_NORMAL]
        #gc.set_background(self.white)
        fg_color = gc.foreground
        gc.set_foreground(self.white)
        self.area.window.draw_rectangle(gc, True, 0, 0, self.w, self.h)
        gc.set_foreground(fg_color)
        for measure in self.score:
            self.layout.set_text(measure.orig_str)
            self.area.window.draw_layout(gc, 20, y, self.layout)
            y += self.measure_height

        for instr in instrs.values():
            if instr.location == -1:
                continue
            y = self.measure_height * instr.location
            if instr.gtk_color is None:
                instr.gtk_color = self.colormap.alloc_color(*instr.color)
            gc.set_foreground(instr.gtk_color)
            self.area.window.draw_arc(
                gc, True, 6 + instr.x_offset, y + 4,
                8, 8, 0, 360*64)
        gc.set_foreground(fg_color)

    def recv(self, source, condition):
        json_str = self.conn.recv()
        instr_id, msg_name, data = simplejson.loads(json_str)
        if msg_name == 'location':
            instrs[instr_id].location = data
        elif msg_name == 'volume':
            instrs[instr_id].set_velocity(data)
        elif msg_name == 'instrument':
            instrs[instr_id].set_pgm(data)
        # TODO: add message for instrument changed
        self.area.queue_draw_area(0, 0, self.w, self.h)
        return True

def main(host, port):
    global server
    server = xmlrpclib.Server('http://localhost:8000/')
    ScoreListener(host, port)
    ControlsWindow()
    gtk.main()

if __name__=='__main__':
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = 'localhost'
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    else:
        port = 8001
    main(host, port)
