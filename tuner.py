# Python library to stream media
#
# Copyright (C) 2008-03-17  Jochen Sprickerhof
# Copyright (C) 2008-2019  Jochen Sprickerhof
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Python library to stream media"""

from datetime import datetime
from dateutil import tz
from argparse import ArgumentParser
from json import load
from re import findall, search, sub
from sys import exit
from threading import Thread
from time import sleep
from urllib.request import urlopen
import curses
import gi
import socket
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst


class Station:
    def __init__(self, name, url, title=None, sname=None):
        self.name = name
        self.sname = sname
        self.url = url
        self.startTime = 0
        self.endTime = 0
        self.title = title
        self.akt = ''

    htmlDict = {
        '&auml;': 'ä',
        '&Auml;': 'Ae',
        '&ouml;': 'ö',
        '&Ouml;': 'Oe',
        '&uuml;': 'ü',
        '&Uuml;': 'Ue',
        '&szlig;': 'ß',
        '&apos;': "'",
        '&eacute;': "é",
        '&#x27;': "'",
        '&#39;': "'",
        '&#039;': "'",
        '&amp;': '&',
        '&quot;': '"',
        '&nbsp;': ' ',
        '\t': ' ',
        '\r': ' ',
        '\n': ' ',
        '\x00': ' ',
    }

    @staticmethod
    def replaceDict(string, dict=htmlDict):
        for key in dict:
            string = string.replace(key, dict[key])
        return string

    @staticmethod
    def del_comma(string):
        string = string.replace(', ', ',')
        if ',' in string and '&' not in string and ';' not in string:
            string = string[string.find(',') + 1:] + ' ' + string[:string.find(',')]
        return string

    @staticmethod
    def caps(string):
        list = string.split(' ')
        newlist = []
        for word in list:
            if word.isupper():
                newlist.append(word.capitalize())
            else:
                newlist.append(word)
        return ' '.join(newlist)

    @classmethod
    def tunestring(cls, string):
        if 'DOCTYPE' in string:
            return ''
        string = cls.replaceDict(string)
        string = string.strip()
        string = string.rstrip()
        string = sub('    +', ' ', string)
        string = sub('<[^>]*>', '', string)
        string = cls.caps(string)
        if string == '-':
            return ''
        if string.startswith('- '):
            string = string[2:]
        if string.endswith(' -'):
            string = string[:-2]
        return string

    @staticmethod
    def getsitere(url, reg=None):
        try:
            site = urlopen(url).read().decode('utf-8')    # limit read(100)
        except (Exception, socket.error):
            return None
        if not reg:
            return site
        found = search(reg, site)
        if not found:
            return None
        return found.groups()

    @staticmethod
    def getjson(url):
        try:
            return load(urlopen(url))
        except (Exception, socket.error):
            return None

    def update(self):
        if self.title:
            self.akt = self.tunestring(self.title(self))

    def get_url(self):
        """ workaround for playlists"""
        if self.url.endswith('mp3'):
            return self.url
        if self.url.endswith('m3u8'):
            return self.url
        if self.url.endswith('listen'):    # for jazzradio
            return self.url
        if self.url.endswith('einws'):    # bbc
            return self.url
        try:
            site = urlopen(self.url).read().decode('utf-8')    # read(100)!
        except IOError:
            return None
        if self.url.endswith('wax'):
            uris = findall('mms://[^ \r\n"]*', site)
        else:
            uris = findall('http://[^ \r\n]*', site)
        if uris:
            return uris[0]
        else:
            return None


class Stations(dict):
    def keys(self):
        return sorted(dict.keys(self))


class Screen:
    def get_akt(self):
        return self.__akt

    def set_akt(self, akt):
        self.__akt = akt
        self.redraw()

    akt = property(get_akt, set_akt)

    def get_next(self):
        return self.__next

    def set_next(self, next):
        self.__next = next
        self.redraw()

    next = property(get_next, set_next)

    def get_slide_stop(self):
        return self.__slide_stop

    def set_slide_stop(self, slide_stop):
        self.__slide_stop = slide_stop
        self.redraw()

    slide_stop = property(get_slide_stop, set_slide_stop)

    def __init__(self, screen, update, stations):
        self.__akt = None
        self.__next = None
        self.__slide_stop = True
        self.stations = stations
        self.screen = screen
        self.update = update
        thread = Thread(target=self.grabber)
        thread.setDaemon(True)
        thread.start()
        self.redraw()

    def grabber(self):
        while True:
            [x.update() for x in self.stations.values()]
            self.redraw()
            sleep(self.update)

    def redraw(self):
        line, cols = self.screen.getmaxyx()
        if(line < 7 + len(self.stations)):
            raise ScreenSizeError('Please resize your terminal to at least %d lines' % (7 + len(self.stations)))
        self.screen.clear()
        x = 0
        center = (cols - max([len(l) for l in self.stations.header])) // 2
        for line in self.stations.header:
            self.screen.addstr(x, center, line, curses.color_pair(3))
            x += 1
        x += 1

        now = datetime.now(tz.tzlocal())
        max_station = max([len(st.name) for st in self.stations.values()])
        for i in self.stations:
            if i == self.akt:
                color = 1
                print('\033]0;%s: %s\007' % (self.stations[i].name, self.stations[i].akt))
            elif i == self.next:
                color = 2
            else:
                color = 0
            self.screen.addstr(x, 0, i + ': ')
            self.screen.addstr(self.stations[i].name, curses.color_pair(color))
            self.screen.addstr(x, max_station + 4, self.stations.get_text(i, now)[:100])
            x += 1
        if not self.akt:
            print(f'\033]0;{type(self.stations).__name__}\007')
        x += 1
        self.screen.addstr(x, 0, 'R: redraw, T: ')
        if self.slide_stop:
            self.screen.addstr('slide')
        else:
            self.screen.addstr('slide', curses.color_pair(2))
        self.screen.addstr(', S: stop, space: pause, Q: quit, up/down: next/prev, left/right: seek')
        self.screen.refresh()


class GstPlayer:
    def __init__(self, station, screen, oldPlayer=None):
        self.station = station
        self.screen = screen
        self.oldPlayer = oldPlayer

        self.player = Gst.ElementFactory.make('playbin', None)
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect('message::eos', self.on_eos)
        bus.connect('message::error', self.on_error)
        bus.connect('message::state-changed', self.on_state_changed)
        bus.connect('message::tag', self.on_tag)

        url = self.station.get_url()
        if url:
            self.player.set_property('uri', url)
            self.player.set_state(Gst.State.PLAYING)

    def on_eos(self, bus, message):
        self.player.set_state(Gst.State.NULL)

    def on_error(self, bus, message):
        self.player.set_state(Gst.State.NULL)

    def on_state_changed(self, bus, message):
        old, new, pending = message.parse_state_changed()
        if message.src == self.player and new == Gst.State.PLAYING:
            self.screen.akt = self.screen.next
            self.screen.next = None
            if self.oldPlayer:
                self.oldPlayer.stop()

    def on_tag(self, bus, message):
        tag, title = message.parse_tag().get_string('title')
        if tag:
            self.station.akt = title

    def stop(self):
        if(self.oldPlayer):
            self.oldPlayer.stop()
        self.player.set_state(Gst.State.NULL)

    def pause(self):
        if self.player.get_state(Gst.CLOCK_TIME_NONE).state == Gst.State.PLAYING:
            self.player.set_state(Gst.State.PAUSED)
        else:
            self.player.set_state(Gst.State.PLAYING)

    def rewind(self):
        rc, pos_int = self.player.query_position(Gst.Format.TIME)
        seek_ns = pos_int - 100 * 1000000000
        if seek_ns < 0:
            seek_ns = 0
        self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, seek_ns)

    def forward(self):
        rc, pos_int = self.player.query_position(Gst.Format.TIME)
        seek_ns = pos_int + 100 * 1000000000
        self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, seek_ns)


class Player:
    def __init__(self, scr, update, stations):
        self.player = None
        self.stop_tune = True
        self.screen = Screen(scr, update, stations)

    def stop(self):
        if self.player:
            self.player.stop()
        self.screen.slide_stop = True
        self.screen.akt = None
        self.screen.next = None
        self.stop_tune = True

    def tune(self, to):
        if self.screen.next or to == self.screen.akt:
            return
        self.screen.next = to
        self.player = GstPlayer(self.screen.stations[to], self.screen, self.player)
        self.stop_tune = False

    def pause(self):
        self.player.pause()

    def rewind(self):
        self.player.rewind()

    def forward(self):
        self.player.forward()

    def slide(self):
        if not self.screen.slide_stop:
            self.screen.slide_stop = True
        else:
            self.screen.slide_stop = False
            Thread(target=self.slide_run).start()

    def slide_run(self):
        for i in self.screen.stations:
            if self.screen.slide_stop:
                break
            self.tune(i)
            time = 0
            while self.screen.akt != i and time < 5:
                sleep(2)
                time += 1
            sleep(5)
        self.screen.slide_stop = True

    def pref(self):
        keys = self.screen.stations.keys()
        if self.screen.akt:
            self.tune(keys[(keys.index(self.screen.akt) - 1) % len(keys)])
        else:
            self.tune(keys[-1])

    def next(self):
        keys = self.screen.stations.keys()
        if self.screen.akt:
            self.tune(keys[(keys.index(self.screen.akt) + 1) % len(keys)])
        else:
            self.tune(keys[0])


class StationKeyError(Exception):
    pass


class ScreenSizeError(Exception):
    pass


def cur_main(screen, loop, stations, update=30, station=None):
    socket.setdefaulttimeout(5)
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    plr = Player(screen, update, stations)

    if station:
        if station in plr.screen.stations:
            plr.tune(station)
        else:
            raise StationKeyError('Station %s not found' % station)

    while True:
        key = screen.get_wch()
        if key == 'Q':
            screen.clear()
            loop.quit()
            break
        elif key == 'R':
            plr.screen.redraw()
        elif key == 'T':
            plr.slide()
        elif key == 'S':
            plr.stop()
        elif key == ' ':
            plr.pause()
        elif key in plr.screen.stations:
            plr.tune(key)
        elif key == curses.KEY_UP:
            plr.pref()
        elif key == curses.KEY_DOWN:
            plr.next()
        elif key == curses.KEY_LEFT:
            plr.rewind()
        elif key == curses.KEY_RIGHT:
            plr.forward()


def grab(station, update, stations):
    if station[0] == 'all':
        station = stations.keys()

    while True:
        try:
            for i in station:
                if i not in stations:
                    print('Station %s not found' % i)
                    exit(2)
                stations[i].update()
                print(stations[i].name + ': ' + stations[i].akt)
            sleep(update)
        except KeyboardInterrupt:
            break


def main(stations):
    parser = ArgumentParser()
    parser.add_argument('-g', '--grabber', metavar='stationkey[,..]',
                        help='mode to test grabber function of a station (all for all stations)')
    parser.add_argument('-s', '--station', metavar='stationkey',
                        help='Station to start with')
    parser.add_argument('-u', '--update', type=float, metavar='time',
                        help='update intervall for grabber function')
    options = parser.parse_args()

    if options.grabber:
        if not options.update:
            options.update = 2
        grab(options.grabber.split(','), options.update, stations)
    else:
        if not options.update:
            options.update = 30
        try:
            Gst.init(None)
            loop = GLib.MainLoop()
            Thread(target=curses.wrapper, args=(cur_main, loop, stations,
                                                options.update, options.station)).start()
            loop.run()
        except (ScreenSizeError, StationKeyError) as e:
            print(e)
            exit(2)
