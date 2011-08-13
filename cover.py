# -*- coding: utf-8 -*-
# Copyright 2011 Simonas Kazlauskas
# Contact: http://kazlauskas.me/mail

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from quodlibet.plugins.events import EventPlugin
from quodlibet.player import playlist as player
from quodlibet import config, util
from os import path
from urllib2 import urlopen
from urllib import quote
from xml.dom.minidom import parseString
from threading import Thread
from random import randint
from BeautifulSoup import BeautifulSoup
from urlparse import urljoin

def save(url, directory, album, ext):
    """
    Downloads and saves album art image.
    
    Arguments:
    url - link to image on WWW.
    directory - where to save image.
    album - album name.
    ext - image extension.
    Usage:
    save("http://...LZZZZ.jpg", "/home/.../music", "Abbey Road", "jpg")
    """
    try:
        album = util.fs_illegal_strip(album)
    except:
        pass
    image_path = path.join(directory, album + ext)
    try:
        image_file = open(image_path, "w+")
        image_file.write(urlopen(url).read())
        image_file.close()
        return True
    except:
        print_e(_("[Automatic Album Art] Could not write album art image to %s") % image_path)
        return False


def check_existing_cover(album, file_path):
    """
    Checks if cover art already exists.
    
    Arguments:
    album - album name.
    file_path - full path to song, including filename.
    Usage:
    check_existing_cover('Abbey Road', '/home.../music/song.mp3')
    """
    if is_enabled('reload'):
        #Force redownload of all covers option.
        return False
    extensions = ['.png', '.jpg', '.jpeg', '.gif']
    try:
        album = util.fs_illegal_strip(album)
    except:
        pass
    directory = path.dirname(file_path)
    for extension in extensions:
        if path.exists(path.join(directory, album+extension)):
            message = "[Automatic Album Art] Album art for %s already exists."
            print_d(_(message % album))
            return True
    return False
    
    
def is_enabled(tag, default = True):
    """
    Checks if plugin is enabled, give it's tag as argument.
    
    Usage:
    is_enabled('MB') #Checks if MusicBrainz is enabled.
    """
    try:
        if config.get('plugins', 'cover_'+tag) == 'True':
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
        self.order = [MusicBrainzCover, LastFMCover, AmazonCover, VGMdbCover]
        
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
        self.passed = True
        #Last.fm API requires key.
        api = 'http://ws.audioscrobbler.com/2.0/'
        apikey = '2dd4db6614e0f314b4401a92dce5e04a'
        try:
            self.path = path.dirname(song['~filename'])
            self.album = song['album'].encode('utf-8')
            self.artist = song['artist'].encode('utf-8')
        except:
            #Indicates, that we didn't get required... variables(?)
            self.passed = False
        if not self.album or not self.artist:
            self.passed = False
            
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
        except:
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
            return 70

    def __init__(self, song):
        self.passed = True
        try:
            self.album = song['album']
            self.treshold = self.get_treshold()
            self.path = path.dirname(song['~filename'])
            if not self.album:
                self.passed = False
        except:
            self.passed = False
            
        try:
            #can search for mbid if we have one
            self.mbid = song['musicbrainz_albumid']
            self.have_mbid = True
            if not self.mbid:
                self.have_mbid = False
        except:
            self.have_mbid = False
            
        artist = song.get('artist', False)
        url = 'http://musicbrainz.org/ws/2/release?limit=4&query=%s'
        query = quote(self.escape_query(self.album).encode('utf-8'))
        if artist:
            #If we have artist, we make more accurate search
            artist = self.escape_query(artist).encode('utf-8')
            query += quote(' AND artist:%s' % artist)
        self.url = url % query
        self.img = 'http://ec%d.images-amazon.com/images/P/%s.%02d.LZZZZZZZ.jpg'
        self.img = self.img % (randint(1,3), '%s', randint(1, 9))
        
    def run_mbid(self):
        url = 'http://musicbrainz.org/ws/2/release/'+self.mbid
        try:
            xml = parseString(urlopen(url).read())
            if not len(xml.getElementsByTagName('asin')) == 0:
                    asin = xml.getElementsByTagName('asin')[0]
                    asin = asin.childNodes[0].toxml()
                    return self.download_image(asin)
        except:
            return False
        return False
        
    def run(self):
        if self.have_mbid and is_enabled('MB') and self.run_mbid():
            #run mbid search, if possible.
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
        except:
            return False
        return False
            
    def download_image(self, asin):
        url = self.img % asin
        try:
            #We need to check, if image is not 1x1 empty gif.
            image = urlopen(url)
            #I think 500 bytes is pretty reasonable size for this check.
            if image.headers['content-length'] < 500:
                return False
            else:
                image.close()
        except:
            return False
        return save(url, self.path, self.album, '.jpg')
        
class AmazonCover(object):
    """
    Searches and downloads cover art from Amazon.
    
    Usage:
    AmazonCover(quodlibet.player.playlist.song).run()
    """
    def __init__(self, song):
        self.passed = True
        key = 'AKIAJVYURRT3Y62RJNEA'
        sec = 'JMh0Rk3ZvRjsvPxTppJWkHe/gMVd7Ws4XsSIZW/0'
        self.amz = {}
        amzns = ['CA', 'DE', 'FR', 'JP', 'US', 'UK']
        try:
            import bottlenose
            for amzn in amzns:
                self.amz[amzn] = bottlenose.Amazon(key, sec, Region = amzn)
        except:
            self.passed = False
            print_w(_('[Automatic Album Art] bottlenose package is missing. Amazon search disabled.'))  
        try:
            self.artist = song['artist'].decode('utf-8')
            self.album = song['album'].decode('utf-8')
            self.path = path.dirname(song['~filename'])
            if not self.artist or not self.album:
                self.passed = False
        except:
            self.passed = False

    def run(self):
        if len(self.amz) == 0 or not self.passed or not is_enabled('A'):
            return False
        for amazon in self.amz:
            amazon = self.amz[amazon]
            try:
                arg = {'SearchIndex': 'Music', 'ResponseGroup': 'Images',
                        'Title':self.album, 'Artist': self.artist}
                xml = parseString(amazon.ItemSearch(**arg))
                result_count = xml.getElementsByTagName('TotalResults')[0]
                result_count = int(result_count.childNodes[0].toxml())
                if result_count == 0 or result_count > 5:
                    continue
                try:
                    image = xml.getElementsByTagName('LargeImage')[0]
                    image = image.getElementsByTagName('URL')[0]
                    image = image.childNodes[0].toxml()
                except:
                    continue
                extension = path.splitext(image)[1]
                return save(image, self.path, self.album, extension)
            except:
                continue
        return False
        

class VGMdbCover(object):
    """
    Searches and downloads cover art from VGMdb.
    
    Usage:
    VGMdbCover(quodlibet.player.playlist.song).run()
    """
    
    def __init__(self, song):
        self.passed = True
        self.second_run = False
        try:
            self.path = path.dirname(song['~filename'])
            self.album = song['album'].encode('utf-8')
            self.artist = song['artist'].encode('utf-8')
        except:
            self.passed = False
        if not self.album or not self.artist:
            self.passed = False

        url = 'http://vgmdb.net/search?q=%%22%s%%22%%20%%22%s%%22'
        self.url = url % (quote(self.artist), quote(self.album))
        
        try:
            keys = ['labelid', 'catalog', 'catalog#']
            self.label = [song[key] for key in keys if song.get(key, False)][0]
            self.has_label = True
            if not self.label:
                self.has_label = False
        except:
            self.has_label = False
            
    def run_label(self):
        url = 'http://vgmdb.net/search?q=%s' % quote(self.label)
        try:
            xml = urlopen(url)
            if 'http://vgmdb.net/album/' in xml.url:
                xml = BeautifulSoup(xml.read())
                c = urljoin(self.url, xml.find('img', {'id':'coverart'})['src'])
                extension = path.splitext(c)[1]
                return save(c, self.path, self.album, extension)
        except:
            return False
        
    def run(self):
        if self.has_label and is_enabled('VGM') and self.run_label():
            return True
        if not self.passed and not is_enabled('VGM'):
            return False
        try:
            xml = urlopen(self.url)
            if 'http://vgmdb.net/album/' in xml.url:
                xml = BeautifulSoup(xml.read())
                c = urljoin(self.url, xml.find('img', {'id':'coverart'})['src'])
                extension = path.splitext(c)[1]
                return save(c, self.path, self.album, extension)
            else:
                if self.second_run:
                    return False
                #Search without artist
                url = 'http://vgmdb.net/search?q=%%22%s%%22'
                self.second_run = True
                self.url = url % quote(self.album)
                return self.run()
        except:
            return False

class CoverFetcher(EventPlugin):
    PLUGIN_ID = "CoverFetcher"
    PLUGIN_NAME = _("Automatic Album Art")
    PLUGIN_DESC = _("Automatically downloads and saves album art for currently playing album.")
    PLUGIN_VERSION = "0.8"
    

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
        tip = _('How much search results should be tolerated?'+
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
    
    def enabled(self):
        self.plugin_on_song_started(player.song)
