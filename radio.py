#!/usr/bin/python3
#
# Web Radio Station Tuner
# - seamless playing
# - greps song names from the net
#
# dependencies:
# aptitude install python3-gi gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-alsa
#
# http://jochen.sprickerhof.de/software/radio
#
# (c) 2008-03-17 Jochen Sprickerhof <jochen at sprickerhof.de>
# (c) 2008-2018 Jochen Sprickerhof <jochen at sprickerhof.de>

from optparse import OptionParser
import curses
from threading import Thread
from time import sleep
from urllib.request import urlopen
import socket
from sys import exit
from re import search, findall, sub
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst


class Station(object):
    def __init__(self, name, url, title=None):
        self.name = name
        self.url = url
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

    def update(self):
        if self.title:
            self.akt = self.tunestring(self.title(self))

    def get_url(self):
        """ workaround for playlists"""
        if self.url.endswith('mp3'):
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
    def __init__(self):
        dict.__init__(self)

        def bremenvier(self):
            text = self.getsitere('http://www.radiobremen.de/bremenvier/includes/mediabox.inc.php?c=onair',
                                  r'<sendung>(.*)</sendung>(?:.|\s)*<jetzt>(.*): (.*)</jetzt>')
            if not text:
                return ''
            return self.del_comma(text[1]) + ' - ' + text[2] + ' (' + text[0] + ')'

        def einslive(self):
            text = self.getsitere('http://www.einslive.de/radiotext/RADIOTXT.TXT')
            if not text:
                return ''
            einsliveDict = {
                'Ihr hoert': '',
                'mit 1LIVE': '',
                '1LIVE': '',
                '1live': '',
                '&#x0022;': '"',
                ':': '-',
                '*': '',
                'mit': '-',
            }
            text = self.replaceDict(text, einsliveDict)
            if text.count('"') == 1:
                text = text.replace('- "', ' - ')
                text = text.replace('"', '')
            elif text.count('"') > 1:
                title = text[text.find('"') + 1:text.rfind('"')]
                interpret = text[:text.find('"')] + text[text.rfind('"') + 1:]
                interpret = interpret.replace('-', '')
                text = interpret + ' - ' + title
            return text

        def deutschlandfunk(self):
            text = self.getsitere('http://www.deutschlandradio.de/jetzt-im-radio.261.de.html', r'Deutschlandfunk.*(?:<[^>]*>){7}[^<]*(?:<[^>]*>){5}([^<]*)(?:<[^>]*>){5}([^<]*)')
            if not text:
                return ''
            return text[0] + ' - ' + text[1]

        def dradio(self):
            text = self.getsitere('http://www.deutschlandradio.de/jetzt-im-radio.261.de.html', r'Deutschlandfunk Kultur.*(?:<[^>]*>){7}[^<]*(?:<[^>]*>){5}([^<]*)(?:<[^>]*>){5}([^<]*)')
            if not text:
                return ''
            return text[0] + ' - ' + text[1]

        def lounge_radio(self):
            text = self.getsitere('http://www.lounge-radio.com/code/pushed_files/now.html',
                                  r'Artist:.*\n.*<div>(.*)</div>.*\n(?:.*\n){2}.*Track:.*\n.*<div>(.*)</div>')
            if not text:
                return ''
            return text[0] + ' - ' + text[1]

        def bremenzwei(self):
            text = self.getsitere('http://www.radiobremen.de/extranet/playlist/nowplaying_nwr.xml',
                                  r'<strong>(.*)</strong>.*\n.*Titel: "(.*)"<br />\nVon: (.*)</p>|<strong>(.*)</strong>')
            if not text:
                return ''
            if text[0]:
                return text[1] + ' - ' + self.del_comma(text[2]) + ' (' + text[0] + ')'
            return text[3]

        def tsf_jazz(self):
            text = self.getsitere('http://www.tsfjazz.com/getSongInformations.php')
            if not text:
                return ''
            text = text.replace('|', ' - ')
            return text

        self['a'] = Station('Byte.fm', 'http://www.byte.fm/stream/bytefm.m3u')
        self['b'] = Station('Bremen 4', 'http://httpmedia.radiobremen.de/bremenvier.m3u', bremenvier)
        self['c'] = Station('Cosmo', 'https://wdr-cosmo-live.icecastssl.wdr.de/wdr/cosmo/live/mp3/128/stream.mp3')
        self['d'] = Station('Deutschlandfunk', 'http://www.dradio.de/streaming/dlf_hq_ogg.m3u', deutschlandfunk)
        self['e'] = Station('1 Live', 'http://www.wdr.de/wdrlive/media/einslive.m3u', einslive)
        self['f'] = Station('Dfunk Nova', 'http://st03.dlf.de/dlf/03/128/mp3/stream.mp3')
        self['g'] = Station('Das Ding', 'http://mp3-live.dasding.de/dasding_m.m3u')
        self['h'] = Station('Fritz', 'https://rbb-fritz-live.sslcast.addradio.de/rbb/fritz/live/mp3/128/stream.mp3')
        self['i'] = Station('NDR Info', 'http://www.ndr.de/resources/metadaten/audio/m3u/ndrinfo.m3u')
        self['j'] = Station('Jazzradio', 'https://streaming.radio.co/s774887f7b/listen')
        self['k'] = Station('Dradio Kultur', 'http://www.dradio.de/streaming/dkultur_hq_ogg.m3u', dradio)
        self['l'] = Station('1 Live diggi', 'http://www.wdr.de/wdrlive/media/einslivedigi.m3u')
        self['m'] = Station('Smooth Jazz', 'http://smoothjazz.com/streams/smoothjazz_128.pls')
        self['n'] = Station('Bremen Zwei', 'http://dl-ondemand.radiobremen.de/bremenzwei.m3u', bremenzwei)
        self['o'] = Station('Groove FM', 'http://stream.groovefm.de:10028/listen.pls')
        self['p'] = Station('Radio Swiss Pop', 'http://www.radioswisspop.ch/live/mp3.m3u')
        self['q'] = Station('Bremen Zwei Sounds', 'http://webchannel.radiobremen.de:8000/bremenzwei-sounds.m3u')
        self['r'] = Station('Swiss Radio Jazz', 'http://relay.publicdomainproject.org/modern_jazz.aac.m3u')
        self['s'] = Station('NDR Blue', 'http://www.ndr.de/resources/metadaten/audio/m3u/ndrblue.m3u')
        self['t'] = Station('TSF Jazz', 'http://statslive.infomaniak.ch/playlist/tsfjazz/tsfjazz-high.mp3/playlist.pls', tsf_jazz)
        self['u'] = Station('BBC World Service', 'http://bbcwssc.ic.llnwd.net/stream/bbcwssc_mp1_ws-einws')
        self['v'] = Station('Lounge Radio', 'http://www.lounge-radio.com/listen128.m3u', lounge_radio)
        self['w'] = Station('WDR 5', 'http://www.wdr.de/wdrlive/media/wdr5.m3u')
        self['x'] = Station('Swiss Groove', 'http://swissgroove.com/listen.php?player=pls')
        self['y'] = Station('N-Joy', 'https://ndr-njoy-live.sslcast.addradio.de/ndr/njoy/live/mp3/128/stream.mp3')
        self['z'] = Station('Radio Swiss Jazz', 'http://www.radioswissjazz.ch/live/mp3.m3u')

    def keys(self):
        return sorted(dict.keys(self))


class Screen(object):
    __akt = None
    __next = None
    __slide_stop = True
    stations = Stations()

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

    def __init__(self, screen, update):
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
        self.screen.addstr(x, 16, ' _', curses.color_pair(3))
        x += 1
        self.screen.addstr(x, 16, '|_)  _   _| o  _', curses.color_pair(3))
        x += 1
        self.screen.addstr(x, 16, '| \ (_| (_| | (_)', curses.color_pair(3))
        x += 2
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
            self.screen.addstr(x, 21, self.stations[i].akt[:100])
            x += 1
        if not self.akt:
            print('\033]0;Radio\007')
        x += 1
        self.screen.addstr(x, 0, 'R: redraw, T: ')
        if self.slide_stop:
            self.screen.addstr('slide')
        else:
            self.screen.addstr('slide', curses.color_pair(2))
        self.screen.addstr(', S: stop, space: pause, Q: quit, up/down: next/prev')
        self.screen.refresh()


class GstPlayer(object):
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


class Player(object):
    player = None
    stop_tune = True

    def __init__(self, scr, update):
        self.screen = Screen(scr, update)

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


def cur_main(screen, loop, update=30, station=None):
    socket.setdefaulttimeout(5)
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    plr = Player(screen, update)

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


def grab(station, update):
    stations = Stations()
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


def main():
    parser = OptionParser()
    parser.add_option('-g', '--grabber', metavar='stationkey[,..]', help='mode to test grabber function of a station (all for all stations)')
    parser.add_option('-s', '--station', metavar='stationkey', help='Station to start with')
    parser.add_option('-u', '--update', type='float', metavar='time', help='update intervall for grabber function')
    (options, args) = parser.parse_args()

    if options.grabber:
        if not options.update:
            options.update = 2
        grab(options.grabber.split(','), options.update)
    else:
        if not options.update:
            options.update = 30
        try:
            Gst.init(None)
            loop = GLib.MainLoop()
            Thread(target=curses.wrapper, args=(cur_main, loop, options.update, options.station)).start()
            loop.run()
        except (ScreenSizeError, StationKeyError) as e:
            print(e)
            exit(2)


if __name__ == '__main__':
    main()
