# -*- coding: utf-8 -*-
# Copyright 2011 Simonas Kazlauskas
# Contact: http://kazlauskas.me/mail

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from quodlibet.plugins.events import EventPlugin
from quodlibet.player import playlist as player
from quodlibet import config
from os import path
from urllib2 import urlopen, URLError
from urllib import quote
from xml.dom.minidom import parseString
from threading import Thread
from random import randint
from urlparse import urljoin
from BeautifulSoup import BeautifulSoup
import bottlenose

debug = True
if debug:
    from sys import exc_info
    from traceback import print_exception

def debugger(message):
    print_w('[AutoAlbumArt] %s' % message)
    if debug:
        print_exception(*exc_info())

def fs_strip(s, replace=None):
    """
    Strips illegal filesystem characters from album.
    See issue http://code.google.com/p/quodlibet/issues/detail?id=784
    """
    replace = replace or " "
    illegals = '/?<>\:*|"^' #^ is illegal in FAT, only / is illegal in Unix.
    return reduce(lambda q, c: q.replace(c, replace), illegals, s)

def save(url, directory, album, ext):
    """
    Downloads and saves album art image.

    Arguments:
    url -- link to image on WWW.
    directory -- where to save image.
    album -- album name.
    ext -- image extension.
    Usage:
    save("http://...LZZZZ.jpg", "/home/.../music", "Abbey Road", "jpg")
    """
    image_path = path.join(directory, fs_strip(album) + ext)
    try:
        image_file = open(image_path, "w+")
        image_file.write(urlopen(url).read())
        image_file.close()
        return True
    except:
        debugger('Failed to save image from %s to %s' %(url, image_path))
    return False

def check_existing_cover(album, file_path):
    """
    Checks if cover art already exists.

    Arguments:
    album -- album name.
    file_path -- full path to song, including filename.
    Usage:
    check_existing_cover('Abbey Road', '/home.../music/song.mp3')
    """
    #Force redownload of all covers option.
    if is_enabled('reload'):
        return False
    directory = path.dirname(file_path)
    for ext in ['.png', '.jpg', '.jpeg', '.gif']:
        if path.exists(path.join(directory, fs_strip(album) + extension)):
            return True
    return False

def is_enabled(tag, default=True):
    """
    Checks if plugin is enabled, give it's tag as argument.

    Usage:
    is_enabled('MB') #Checks if MusicBrainz is enabled.
    """
    try:
        if config.get('plugins', 'cover_'+tag):
            return True
        else:
            return False
    except:
        return default


class Cover(Thread):
    def __init__(self, song):
        Thread.__init__(self)
        self.song = song
        #Add new engines here!
        self.order = [MusicBrainzCover,
                      LastFMCover,
                      AmazonCover,
                      VGMdbCover]

    def run(self):
        if check_existing_cover(self.song['album'], self.song['~filename']):
            return True
        for fetcher in self.order:
            if fetcher(self.song).run():
                return True
        return False


class LastFMCover(object):
    """
    Searches and downloads cover art from LastFM.

    Usage:
    LastFMCover(quodlibet.player.playlist.song).run()
    """
    def __init__(self, song):
        api = 'http://ws.audioscrobbler.com/2.0/'
        apikey = '2dd4db6614e0f314b4401a92dce5e04a'
        self.path = path.dirname(song['~filename'])
        self.album = song.get('album', '').encode('utf-8')
        self.artist = song.get('artist', '').encode('utf-8')
        if not self.album or not self.artist:
            self.passed = False
        else:
            self.passed = True
        url = "%s?method=album.getinfo&api_key=%s&artist=%s&album=%s"
        self.url = url % (api, apikey, quote(self.artist), quote(self.album))

    def run(self):
        if not self.passed or not is_enabled('LFM'):
            return False

        try:
            content = parseString(urlopen(self.url).read())
            parent = content.getElementsByTagName('lfm')[0]
            if parent.getAttribute('status') == "failed":
                return False
            album = parent.getElementsByTagName('album')[0]
            images = album.getElementsByTagName('image')
            for image in reversed(images):
                if len(image.childNodes) == 0:
                    continue
                image_url = image.childNodes[0].toxml()
                extension = path.splitext(image_url)[1]
                return save(image_url, self.path, self.album, extension)
        except URLError:
            debugger('Failed to open %s'%self.url)
            return False
        except:
            debugger('LFM - unexpected error')
            return False


class MusicBrainzCover(object):
    """
    Searches for art at MusicBrainz. Images are downloaded from Amazon.

    Usage:
    MusicBrainzCover(quodlibet.player.playlist.song).run()
    """
    def escape_query(self, query):
        specials =  ['\\','+','-','&&','||','!','(',')','{','}','[',']',
                         '^','"','~','*','?',':']
        return reduce(lambda q, c: q.replace(c, '\\%s' % c), specials, query)

    def get_treshold(self):
        try:
            return int(config.get('plugins', 'cover_treshold'))
        except:
            debugger('Could not get treshold. Using 70.')
            return 70

    def __init__(self, song):
        self.album = song.get('album', '').encode('utf-8')
        artist = song.get('artist', '').encode('utf-8')
        self.treshold = self.get_treshold()
        self.path = path.dirname(song['~filename'])
        self.mbid = song.get('musicbrainz_albumid', False)
        if not self.album:
            self.passed = False
        else:
            self.passed = True
        url = 'http://musicbrainz.org/ws/2/release?limit=4&query=%s'
        query = quote(self.escape_query(self.album))
        if artist:
            #If we have artist, we can make more accurate search
            query += quote(' AND artist:%s' % self.escape_query(artist))
        self.url = url % query
        #Amazon image url pattern.
        self.img = 'http://ec%d.images-amazon.com/images/P/%s.%02d.LZZZZZZ.jpg'
        self.img = self.img % (randint(1,3), '%s', randint(1, 9))

    def run_with_mbid(self):
        url = 'http://musicbrainz.org/ws/2/release/'+self.mbid
        try:
            xml = parseString(urlopen(url).read())
            if not len(xml.getElementsByTagName('asin')) == 0:
                    asin = xml.getElementsByTagName('asin')[0]
                    asin = asin.childNodes[0].toxml()
                    return self.download_image(asin)
        except URLError:
            debugger('Failed to open %s'%url)
        except:
            debugger('Unexpected error in MB')
        return False

    def run(self):
        #Run search with MBID, if possible.
        if self.mbid and is_enabled('MB') and self.run_with_mbid():
            return True
        if not self.passed or not is_enabled('MB'):
            return False

        try:
            xml = parseString(urlopen(self.url).read())
            release_list = xml.getElementsByTagName('release-list')[0]
            if int(release_list.getAttribute('count')) == 0:
                return False
            albums = release_list.getElementsByTagName('release')
            for album in albums:
                if int(album.getAttribute('ext:score')) < self.treshold:
                    #Albums are ordered by score, so looping through everything
                    #is useless...
                    break
                if len(album.getElementsByTagName('asin')) == 0:
                    #TODO: Images that are not from amazon
                    continue
                else:
                    asin = album.getElementsByTagName('asin')[0]
                    asin = asin.childNodes[0].toxml()
                    return self.download_image(asin)
        except URLError:
            debugger('Failet to open %s'%self.url)
        except:
            debugger('MB - unexpected error')
        return False

    def download_image(self, asin):
        url = self.img % asin
        #We need to check, if image is not 1x1 empty gif.
        try:
            image = urlopen(url)
            #I think 500 bytes is pretty reasonable size for this check.
            if image.headers['content-length'] < 500:
                return False
            else:
                image.close()
        except:
            debugger('Failed to open %s'%url)
        return save(url, self.path, self.album, '.jpg')


class AmazonCover(object):
    """
    Searches and downloads cover art from Amazon.

    Usage:
    AmazonCover(quodlibet.player.playlist.song).run()
    """
    def __init__(self, song):
        key = 'AKIAJVYURRT3Y62RJNEA'
        sec = 'JMh0Rk3ZvRjsvPxTppJWkHe/gMVd7Ws4XsSIZW/0'
        #Initiate Amazon API
        self.amazons = {}
        regions = ['CA', 'DE', 'FR', 'JP', 'US', 'UK']
        for region in regions:
            self.amazons[region] = bottlenose.Amazon(key, sec, Region = region)

        self.artist = song.get('artist', '').decode('utf-8')
        self.album = song.get('album', '').decode('utf-8')
        self.path = path.dirname(song['~filename'])
        if not self.artist or not self.album:
            self.passed = False
        else:
            self.passed = True

    def run(self):
        if not self.passed or not is_enabled('A'):
            return False
        for region, amazon in self.amazons.items():
            try:
                xml = parseString(amazon.ItemSearch(SearchIndex = 'Music',
                                                    ResponseGroup = 'Images',
                                                    Title = self.album,
                                                    Artist = self.artist))
                result_count = xml.getElementsByTagName('TotalResults')[0]
                result_count = int(result_count.childNodes[0].toxml())
                if result_count == 0 or result_count > 5:
                    continue
                image = xml.getElementsByTagName('LargeImage')[0]
                image = image.getElementsByTagName('URL')[0]
                image = image.childNodes[0].toxml()
                extension = path.splitext(image)[1]
                return save(image, self.path, self.album, extension)
            except:
                debugger('amazon.%s - Unexpected error'%region)
                continue
        return False


class VGMdbCover(object):
    """
    Searches and downloads cover art from VGMdb.

    Usage:
    VGMdbCover(quodlibet.player.playlist.song).run()
    """

    def __init__(self, song):
        self.path = path.dirname(song['~filename'])
        self.album = song.get('album','').encode('utf-8')
        self.artist = song.get('artist', '').encode('utf-8')
        if not self.album or not self.artist:
            self.passed = False
        else:
            self.passed = True

        url = 'http://vgmdb.net/search?q=%%22%s%%22%%20%%22%s%%22'
        self.url = url % (quote(self.artist), quote(self.album))

        keys = ['labelid', 'catalog', 'catalog#']
        self.label = [song[key] for key in keys if song.get(key, False)]
        if self.label:
            self.label = self.label[0]

    def run_with_label(self):
        url = 'http://vgmdb.net/search?q=%s' % quote(self.label)
        try:
            site = urlopen(url)
            if 'http://vgmdb.net/album/' in site.url:
                xml = BeautifulSoup(site.read())
                c = urljoin(self.url,
                            xml.find('img', {'id':'coverart'})['src'])
                extension = path.splitext(c)[1]
                return save(c, self.path, self.album, extension)
        except URLError:
            debugger('Failed to open %s'%url)
        except IndexError:
            #If theres no image in page, xml.find will raise index error
            pass
        except:
            debugger('VGMdb - Unexpected error')
        return False

    def run(self):
        #Run search with label first
        if self.label and is_enabled('VGM') and self.run_label():
            return True
        if not self.passed and not is_enabled('VGM'):
            return False
        try:
            site = urlopen(self.url)
            if 'http://vgmdb.net/album/' in site.url:
                xml = BeautifulSoup(site.read())
                c = urljoin(self.url,
                            xml.find('img', {'id':'coverart'})['src'])
                extension = path.splitext(c)[1]
                return save(c, self.path, self.album, extension)
            else:
                if getattr(self, 'second_run', False):
                    return False
                self.second_run = True
                url = 'http://vgmdb.net/search?q=%%22%s%%22'
                self.url = url % quote(self.album)
                return self.run()
        except URLError:
            debugger('Failed to open %s' % self.url)
        except:
            debugger('VGMdb - Unexpected error')
        return False


class CoverFetcher(EventPlugin):
    PLUGIN_ID = "CoverFetcher"
    PLUGIN_NAME = _("Automatic Album Art")
    PLUGIN_DESC = _("Automatically downloads and saves album art for currently"
                    " playing album.")
    PLUGIN_VERSION = "0.85"


    def PluginPreferences(self, parent):
        import gtk

        #Inner functions, mostly callbacks.
        def cb_toggled(cb):
            if cb.get_active():
                config.set('plugins', 'cover_'+cb.tag, 'True')
            else:
                config.set('plugins', 'cover_'+cb.tag, '')

        def get_treshold():
            try:
                return int(config.get('plugins', 'cover_treshold'))
            except:
                return 70

        def set_treshold(spin):
            value = str(spin.get_value_as_int())
            config.set('plugins', 'cover_treshold', value)

        #Another things to be used though whole function
        tooltip = gtk.Tooltips()
        notebook = gtk.Notebook()
        vb = gtk.VBox(spacing = 5)

        #General settings tab
        label = gtk.Label(_('General'))
        settings = gtk.VBox(spacing = 5)
        rld = gtk.CheckButton(_('Redownload image, even if it already exists'))
        tip = _('Helps to keep cover up to date')
        tooltip.set_tip(rld, tip)
        rld.tag = 'reload'
        rld.connect('toggled', cb_toggled)
        rld.set_active(is_enabled(rld.tag, False))
        settings.pack_start(rld)
        notebook.append_page(settings, label)

        #MusicBrainz settings tab
        label = gtk.Label(_('MusicBrainz'))
        settings = gtk.VBox(spacing = 5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'MB'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        treshold = gtk.HBox(spacing = 10)
        tip = _('How much search results should be tolerated?'
                '\nBigger value = More accurate.')
        tooltip.set_tip(treshold, tip)
        treshold_label = gtk.Label('Treshold')
        adjust = gtk.Adjustment(get_treshold(), 40, 100, 5)
        treshold_entry = gtk.SpinButton(adjust)
        treshold_entry.connect('value-changed', set_treshold)
        treshold.pack_start(treshold_label, False)
        treshold.pack_start(treshold_entry, False)
        settings.pack_start(treshold)

        notebook.append_page(settings, label)

        #Last.fm settings tab
        label = gtk.Label(_('Last.fm'))
        settings = gtk.VBox(spacing = 5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'LFM'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        notebook.append_page(settings, label)

        #Amazon settings tab
        label = gtk.Label(_('Amazon'))
        settings = gtk.VBox(spacing = 5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'A'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        notebook.append_page(settings, label)

        #VGMdb settings tab
        label = gtk.Label(_('VGMdb'))
        settings = gtk.VBox(spacing = 5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'VGM'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        notebook.append_page(settings, label)

        vb.pack_start(notebook, True, True)
        return vb

    def plugin_on_song_started(self, song):
        Cover(song).start()
