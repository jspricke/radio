#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Web Radio Station Tuner
#  - seamless playing
#  - greps song names from the net
#
# dependencies:
# aptitude install python-gobject python-gst0.10 gstreamer0.10-plugins-good gstreamer0.10-plugins-bad gstreamer0.10-plugins-ugly
#
# http://jochen.sprickerhof.de/software/radio
#
# (c) 2008-03-17 Jochen Sprickerhof <jochen at sprickerhof.de>
# (c) 2008-2010 Jochen Sprickerhof <jochen at sprickerhof.de>

from optparse import OptionParser
import curses
from threading import Thread
from time import sleep
from urllib import urlopen
import socket
from sys import exit
from re import search, findall, sub
from unicodedata import normalize
import gobject
import pygst
pygst.require('0.10')
import gst

class Station(object):
  def __init__(self, name, url, title = None):
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
  def replaceDict(string, dict = htmlDict):
    for key in dict:
      string = string.replace(key, dict[key])
    return string

  @staticmethod
  def del_comma(string):
    string = string.replace(', ', ',')
    if ',' in string and not '&' in string and not ';' in string:
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
    string = sub('  +', ' ', string)
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
  def getsitere(url, reg = None):
    try:
      site = urlopen(url).read() # limit read(100)
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
    try:
      site = urlopen(self.url).read() # read(100)!
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

    def bbc(self):
      text = self.getsitere('http://www.bbc.co.uk/worldservice/', 'on-now"><[^>]*>([^<]*)<')
      if not text:
        return ''
      return text[0]

    def bremenvier(self):
      text = self.getsitere('http://www.radiobremen.de/bremenvier/includes/mediabox.inc.php?c=onair',
          '<sendung>(.*)</sendung>(?:.|\s)*<jetzt>(.*): (.*)</jetzt>')
      if not text:
        return ''
      return self.del_comma(text[1]) + ' - ' + text[2] + ' (' + text[0] + ')'

    def bytefm(self):
      text = self.getsitere('http://www.byte.fm/php/content/home/new.php', 'Aktueller Song:</b></td></tr><tr><td> <a[^>]*>([^<]*)</a>')
      if not text:
        return ''
      return text[0]

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

    def einslive_diggi(self):
      text = self.getsitere('http://www.einslive.de/multimedia/diggi/',
          'Die letzten 12 Titel(?:[^<]*<[^>]*>){15}([^<]*)</td><td>([^<]*)<')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def das_ding(self):
      text = self.getsitere('http://www.dasding.de/ext/playlist/titel_xml.php',
          '<name>(.*)</name>(?:.*\n)+.*<song>(.*)</song>(?:.*\n)+.*<artist>(.*)</artist>(?:.*\n)+.*</current>')
      if not text:
        return ''
      if not text[1]:
        return text[0]
      return self.del_comma(text[2]) + ' - ' + text[1] + ' (' + self.tunestring(text[0]) + ')'

    def deutschlandfunk(self):
      text = self.getsitere('http://www.dradio.de/jetztimradio/', 'DEUTSCHLANDFUNK.*(?:.*\n){7}(.*)\n(?:.*\n){4}(.*)\n')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def dradio(self):
      text = self.getsitere('http://www.dradio.de/jetztimradio/', 'DEUTSCHLANDRADIO KULTUR.*(?:.*\n){7}(.*)\n(?:.*\n){4}(.*)\n')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def fritz(self):
      text = self.getsitere('http://www.fritz.de/include/frz/nowonair/now_on_air.html', 'titelanzeige"><[^>]*>([^<]*)<')
      if not text:
        return ''
      return text[0]

    def funkhaus_europa(self):
      text = self.getsitere('http://www.funkhauseuropa.de/world_wide_music/playlists/index.phtml',
          '<!-- PLAYLIST (.*) -->(?:.*\n)*.*Uhr(.*)</td><td>(.*)</td><td>.*<span class="inv"> Minuten</span></td></tr>.*\n.*</table>.*\n.*<!-- //PLAYLIST  -->')
      if not text:
        return ''
      return text[1] + ' - ' + text[2] + ' (' + text[0] + ')'

    def groovefm(self):
      text = self.getsitere('http://www.groovefm.de/playlist', 'Aktueller Track.*\n([^<]*)<')
      if not text:
        return ''
      return text[0]

    def jazzradio(self):
      text = self.getsitere('http://jazz.radiohaus-berlin.de/jazzradio/playlist/nowplaying.php', '<b>CURRENT: </b><br>(.*) - (.*)')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def lounge_radio(self):
      text = self.getsitere('http://www.lounge-radio.com/code/pushed_files/now.html',
          'Artist:.*\n.*<div>(.*)</div>.*\n(?:.*\n){2}.*Track:.*\n.*<div>(.*)</div>')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def n_joy(self):
      text = self.getsitere('http://www.ndr.de/n-joy/onaircenter103-onaircenterpopup.html', 'webradio_song_now">(.*)</td>')
      if not text:
        return ''
      return text[0]

    def ndr_info(self):
      text = self.getsitere('http://www.ndrinfo.de/', 'NDR Info Radio-Box(?:.*\n){2}(.*)\n')
      if not text:
        return ''
      return text[0]

    def nordwestradio(self):
      text = self.getsitere('http://www.radiobremen.de/extranet/playlist/nowplaying_nwr.xml',
          '<strong>(.*)</strong>.*\n.*Titel: "(.*)"<br />\nVon: (.*)</p>|<strong>(.*)</strong>')
      if not text:
        return ''
      if text[0]:
        return text[1] + ' - ' + self.del_comma(text[2]) + ' (' + text[0] + ')'
      return text[3]

    def on3radio(self):
      text = self.getsitere('http://on3.de/tracklist/get_tracklist_data',
          'active.*?data-header=."([^\\\]*).*? data-title=."([^\\\]*)')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def radio_swiss_jazz(self):
      text = self.getsitere('http://www.radioswissjazz.ch/cgi-bin/pip/html.cgi?m=playlist&v=i&lang=de',
          '<tr class="on">(?:.*\n){5}.*>(.*)</strong><br />(.*)</a></td>\n')
      if not text:
        return ''
      return text[1] + ' - ' + text[0]

    def radio_swiss_pop(self):
      text = self.getsitere('http://www.radioswisspop.ch/cgi-bin/pip/html.cgi?m=playlist&v=i&lang=de',
          '<tr class="on">(?:.*\n){5}.*>(.*)</strong><br />(.*)</a></td>\n')
      if not text:
        return ''
      return text[1] + ' - ' + text[0]

    def swiss_groove(self):
      text = self.getsitere('http://www.swissgroove.ch/de/music/',
          'AKTUELL GESPIELT(?:.*\n){8}.*Künstler: &nbsp;(.*)<br />\n.*Lied: &nbsp;(.*)<br />')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def smooth_jazz(self):
      text = self.getsitere('http://smoothjazz.com/playlist/', 'ARTIST[^\r]*\r([^\r]*)\r(?:[^\r]*\r){7}([^\r]*)\r')
      if not text:
        return ''
      title = text[1].replace(' - HOT PICK', '')
      return text[0] + ' - ' + title

    def swiss_radio_jazz(self):
      text = self.getsitere('http://www.cogg.de/radiocrazy/cgi-bin/dsh_6092/scxml.php',
          'Current Song(?:.*\n){10}(.*)\n')
      if not text:
        return ''
      return text[0]

    def swr3(self):
      text = self.getsitere('http://www.swr3.de/-/id=66332/12w4f32/index.html',
          '<div class="doctypes_WR_ipretheadline">(.*)</div>\n<div class="doctypes_WR_titleheadline">(.*)</div>')
      if not text:
        return ''
      return text[0] + ' - ' + text[1]

    def tsf_jazz(self):
      text = self.getsitere('http://www.tsfjazz.com/getSongInformations.php')
      if not text:
        return ''
      text = text.replace('|', ' - ')
      return text

    def wdr5(self):
      text = self.getsitere('http://www.wdr5.de/programm.html', '<tr class="(?:even|odd) aktuell">(?:.*\n){5}(.*)\n')
      if not text:
        return ''
      title = text[0].replace('WDR 5', '')
      return title

    def tv_ndr(self):
      text = self.getsitere('http://www.ndr.de/home/index.html',
          'JETZT IM NDR FERNSEHEN(?:.*\n){,10}<h2>(.*)\n')
      if not text:
        return ''
      return text[0]

    self['a'] = Station('Byte.fm', 'http://www.byte.fm/stream/bytefm.m3u', bytefm)
    self['b'] = Station('Bremen 4', 'http://www.radiobremen.de/stream/live/bremenvier.m3u', bremenvier)
    self['c'] = Station('on3Radio', 'http://streams.br-online.de/jugend-radio_2.m3u', on3radio)
    self['d'] = Station('Deutschlandfunk', 'http://www.dradio.de/streaming/dlf_hq_ogg.m3u', deutschlandfunk)
    self['e'] = Station('1 Live', 'http://www.wdr.de/wdrlive/media/einslive.m3u', einslive)
    self['f'] = Station('Funkhaus Europa', 'http://gffstream.ic.llnwd.net/stream/gffstream_w20a.m3u', funkhaus_europa)
    self['g'] = Station('Das Ding', 'http://mp3-live.dasding.de/dasding_m.m3u', das_ding)
    self['h'] = Station('Fritz', 'http://www.fritz.de/live.m3u', fritz)
    self['i'] = Station('NDR Info', 'http://ndrstream.ic.llnwd.net/stream/ndrstream_ndrinfo_hi_mp3.m3u', ndr_info)
    self['j'] = Station('Jazzradio', 'http://www.jazzradio.net/docs/stream/jazzradio.pls', jazzradio)
    self['k'] = Station('Dradio Kultur', 'http://www.dradio.de/streaming/dkultur_hq_ogg.m3u', dradio)
    self['l'] = Station('1 Live diggi', 'http://www.einslive.de/multimedia/diggi/channel_einslivediggi.m3u', einslive_diggi)
    self['m'] = Station('Smooth Jazz', 'http://smoothjazz.com/streams/smoothjazz_128.pls', smooth_jazz)
    self['n'] = Station('Nordwestradio', 'http://gffstream.ic.llnwd.net/stream/gffstream_mp3_w50a.m3u', nordwestradio)
    self['o'] = Station('Groove FM', 'http://stream.groovefm.de:10028/listen.pls', groovefm)
    self['p'] = Station('Radio Swiss Pop', 'http://www.radioswisspop.ch/live/mp3.m3u', radio_swiss_pop)
    self['q'] = Station('Nordwestradio globale Dorfmusik', 'http://80.252.104.101:8000/globaledorfmusik.m3u')
    self['r'] = Station('Swiss Radio Jazz', 'http://www.swissradio.ch/streams/6092.m3u', swiss_radio_jazz)
    self['s'] = Station('SWR 3', 'http://www.swr3.de/wraps/swr3_mp3.m3u.php', swr3)
    self['t'] = Station('TSF Jazz', 'http://broadcast.infomaniak.ch/tsfjazz-high.mp3.pls', tsf_jazz)
    self['u'] = Station('BBC World Service', 'http://www.bbc.co.uk/worldservice/meta/tx/nb/live/eneuk.pls', bbc)
    self['v'] = Station('Lounge Radio', 'http://www.lounge-radio.com/listen128.m3u', lounge_radio)
    self['w'] = Station('WDR 5', 'http://www.wdr.de/wdrlive/media/wdr5.m3u', wdr5)
    self['x'] = Station('Swiss Groove', 'http://www.swissgroove.ch/listen128.pls', swiss_groove)
    self['y'] = Station('N-Joy', 'http://ndrstream.ic.llnwd.net/stream/ndrstream_n-joy_hi_mp3.m3u', n_joy)
    self['z'] = Station('Radio Swiss Jazz', 'http://www.radioswissjazz.ch/live/mp3.m3u', radio_swiss_jazz)
    self['za'] = Station('TV NDR', '', tv_ndr)

  def keys(self):
    return sorted(dict.keys(self))

  def __iter__(self):
    return iter(self.keys())

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
    thread = Thread(target = self.grabber)
    thread.setDaemon(True)
    thread.start()
    self.redraw()

  def grabber(self):
    while True:
      map(lambda x: x.update(), self.stations.values())
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
        print '\033]0;%s: %s\007' % (self.stations[i].name, self.stations[i].akt)
      elif i == self.next:
        color = 2
      else:
        color = 0
      self.screen.addstr(x, 0, i + ': ')
      self.screen.addstr(self.stations[i].name, curses.color_pair(color))
      self.screen.addstr(x, 21, self.stations[i].akt)
      x += 1
    if not self.akt:
      print '\033]0;Radio\007'
    x += 1
    self.screen.addstr(x, 0, 'R: redraw, T: ')
    if self.slide_stop:
      self.screen.addstr('slide')
    else:
      self.screen.addstr('slide', curses.color_pair(2))
    self.screen.addstr(', S: stop, Q: quit, up/down: next/prev')
    x += 1
    self.screen.addstr(x, 0, 'left/right: seek -/+ 10sec, shift-left/right: seek -/+ 2sec, space: pause')
    self.screen.refresh()
    
class GstPlayer(object):
  def __init__(self, station, screen, oldPlayer = None):
    self.station = station
    self.screen = screen
    self.oldPlayer = oldPlayer

    self.player = gst.element_factory_make('playbin')
    bus = self.player.get_bus()
    bus.add_signal_watch()
    bus.connect('message', self.on_message)

    url = self.station.get_url()
    if url:
      self.player.set_property('uri', url)
      self.player.set_state(gst.STATE_PLAYING)

  def on_message(self, bus, message):
    t = message.type
    if t == gst.MESSAGE_EOS:
      self.player.set_state(gst.STATE_NULL)
    elif t == gst.MESSAGE_ERROR:
      self.player.set_state(gst.STATE_NULL)
      (err, debug) = message.parse_error()
      print 'Error: %s' % err
    elif t == gst.MESSAGE_BUFFERING:
      percent = message.parse_buffering()
      #print percent
    elif t == gst.MESSAGE_STATE_CHANGED:
      old, new, pending = message.parse_state_changed() 
      if message.src == self.player and new == gst.STATE_PLAYING:
        self.screen.akt = self.screen.next
        self.screen.next = None
        if self.oldPlayer:
          self.oldPlayer.stop()
    elif t == gst.MESSAGE_TAG:
      taglist = message.parse_tag()
      if 'title' in taglist:
        self.station.akt = normalize('NFKD', unicode(taglist['title'])).encode('ASCII', 'ignore')[:100] #TODO: changes stream with jazzradio wtf

  def stop(self):
    if(self.oldPlayer):
      self.oldPlayer.stop()
    self.player.set_state(gst.STATE_NULL)

  def pause(self):
    if self.player.get_state()[1] == gst.STATE_PLAYING:
      self.player.set_state(gst.STATE_PAUSED)
    else:
      self.player.set_state(gst.STATE_PLAYING)

  def seek(self, val):
    pos_int = self.player.query_position(self.time_format, None)[0]
    seek_ns = pos_int - (val * 1000000000)
    self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH, seek_ns)

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

  def seek(self, val):
    self.player.seek(val)

  def slide(self):
    if not self.screen.slide_stop:
      self.screen.slide_stop = True
    else:
      self.screen.slide_stop = False
      Thread(target = self.slide_run).start()

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

def cur_main(screen, loop, update = 30, station = None):
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
    key = screen.getch()
    if 0 < key < 256:
      key = chr(key)
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
      plr.seek(-10)
    elif key == curses.KEY_RIGHT:
      plr.seek(10)
    elif key == curses.KEY_SLEFT:
      plr.seek(-2)
    elif key == curses.KEY_SRIGHT:
      plr.seek(2)

def grab(station, update):
  stations = Stations()
  if station[0] == 'all':
    station = stations.keys()

  while True:
    try:
      for i in station:
        if i not in stations:
          print 'Station %s not found' % i
          exit(2)
        stations[i].update()
        print stations[i].name + ': ' + stations[i].akt
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
      gobject.threads_init()
      loop = gobject.MainLoop()
      Thread(target = curses.wrapper, args = (cur_main, loop, options.update, options.station)).start()
      loop.run()
    except (ScreenSizeError, StationKeyError), e:
      print e
      exit(2)

if __name__ == '__main__':
  main()
