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
from urllib2 import urlopen
from urllib import quote
from xml.dom.minidom import parseString
from threading import Thread
import re


class Cover(Thread):
    """Threaded object, that downloads all covers.
    At least album and path arguments should be passed for atleast one
    cover engine to work.
    
    Available engines:
    MB - stands for MusicBrainz.
    LFM - stands for last.fm
    Excecuting order and used engines must be specified as list and passed as
    order argument.
    
    Usage example:
    Cover(artist = 'The Beatles', album = 'Abbey Road',
          path = '/home/music/Beatles/song.mp3', order = ['MB', 'LFM']).start()
    """
    def __init__(self, **kw):
        Thread.__init__(self)
        self.artist = kw.get('artist', None)
        self.album = kw.get('album')
        self.path = kw.get('path')
        self.order = kw.get('order', ['MB', 'LFM'])
        self.treshold = kw.get('treshold', 70)
        
        #Checking, if we can perform searches with given arguments.
        #Also creating objects.
        for key, order in enumerate(self.order):
            if order == "LFM":
                if self.artist and self.album:
                    self.order[key] = (LastFMCover(self.artist,
                                                   self.album,
                                                   self.path), True,)
                else:
                    self.order[key] = (None, False,)
            if order == "MB":
                if self.album:
                    self.order[key] = (MusicBrainzCover(self.album,
                                                        self.path,
                                                        self.artist,
                                                        self.treshold), True,)
                else:
                    self.order[key] = (None, False,)
        
    def run(self):
        for order in self.order:
            if not order[1]:
                continue
            #Modules may return unexcepted errors, so making python stop it's
            #work before all modules got to do it's thing.    
            try:
                run = order[0].run()
            except:
                run = False
            if run:
                #We got the cover! We can return.
                return True
        #If at this point no returns happened, then we failed.
        return False
            

class LastFMCover(object):
    """Fetches cover from Last.fm.
    Arguments - artist, album and path. All required.
    Cover is saved in same directory as song. Image name equals to album name.
    Usage example:
    LastFMCover('The Beatles', 'Abbey Road', 
                '/home/music/The Beatles/song.mp3').run()"""
    #Threading needed so UI wouldn't be blocked on each song change.
    #Not sure, if they are killed correctly.
    def __init__(self, artist, album, path):
        #Last.fm API requires key.
        api = 'http://ws.audioscrobbler.com/2.0/'
        apikey = '2dd4db6614e0f314b4401a92dce5e04a'
        #Initiate class specific variables.
        #Escaping is done, because urllib.quode cannot handle utf-8.
        self.path = path.encode('utf-8')
        self.album = album.encode('utf-8')
        self.artist = artist.encode('utf-8')
        self.content = None
        #Make escaped url to do request with urllib2.
        #Someone said something about 80 characters?
        self.url = api
        self.url += "?method=album.getinfo"
        self.url += "&api_key=" + apikey
        self.url += "&artist=" + quote(self.artist)
        self.url += "&album="+quote(self.album)
        
    def run(self):
        #Doing things. run is name required by Thread.
        return self.save_image(self.get_image_url())
   
    def get_image_url(self):
        "Get image url, select biggest possible"
        try:
            self.content = parseString(urlopen(self.url).read())
            parent = self.content.getElementsByTagName('lfm')[0]
            if parent.getAttribute('status') == "failed":
                return False
            album = parent.getElementsByTagName('album')[0]
            images = album.getElementsByTagName('image')
            for image in reversed(images):
                if len(image.childNodes) == 0:
                    continue
                return image.childNodes[0].toxml()
        except:
            return False
        return False

    def save_image(self, image):
        #save_image may not get image variable from get_image_url. 
        if not image:
            return False
        else:
            #We need to put image in same directory, as music.
            #And image has to have same extensions.
            direc = path.dirname(self.path)
            extension = path.splitext(image)[1]
            try:
                #We only do that, if we dont already have image
                image_path = path.join(direc, self.album+extension)
                if not path.exists(image_path):
                    with open(image_path, "w+") as image_file:
                        #urlopen could fail so it's wrapped in try.
                        image_file.write(urlopen(image).read())
                        image_file.close()
            except:
                return False
            return True
            
            
class MusicBrainzCover(object):
    """Fetches cover from MusicBrainz.
    Cover is saved in same directory as song. Image name equals to album name.
    
    Utilizes 4 arguments. Album, Path, Artist and Treshold.
    Album, Path and Treshold are required.
    Artist string can be empty. It gives more accurate searches.
    !Miswroten Artist may result in no search results(and so - covers).
    
    Usage example:
    MusicBrainzCover('Abbey Road', '/home/music/The Beatles/song.mp3',
                      '', 70).run()
                      
    OR
    
    MusicBrainzCover('Abbey Road', '/home/music/The Beatles/song.mp3',
                      'The Beatles', 70).run()"""
    def __init__(self, album, path, artist, treshold):
        self.treshold = treshold
        self.path = path
        self.album = album
    
        self.search = 'http://musicbrainz.org/ws/2/release?limit=1&query='
        query = quote(album.encode('utf-8'))
        #If we have artist, we can make more accurate search
        if artist:
            query += quote(' AND artist:%s'%artist.encode('utf-8'))
        self.search += query
        #OK we made API search url.
        
        self.imageurl = 'http://musicbrainz.org/release/%s'
        #This is link, where we could find image.
        
        #Only thing I'm sure about image is in this regex.
        #Images are taken from Amazon by the way.
        self.imagereg = r'http\:\/\/(.+)?\.LZ+\.(jpg|png|jpeg)'
        
        
    def search_album(self):
        try:
            #We do a search for mbid which is needed to acces actual desctiption
            #of album.
            xml = parseString(urlopen(self.search).read())
            release_list = xml.getElementsByTagName('release-list')[0]
            if release_list.getAttribute('count') == 0:
                return False
            album = release_list.getElementsByTagName('release')[0]
            if album.getAttribute('ext:score') < self.treshold:
                return False
            return self.download_image(album.getAttribute('id'))
        except:
            return False
            
    def download_image(self, mbid):
        try:
            #We look at album's description.
            #Most of the time it contains images from Amazon.
            findings = urlopen(self.imageurl%mbid).read()
            findings = re.search(self.imagereg, findings).group()
        except:
            #Couldn't download
            return False
        if not findings:
            #No image was available
            return False
        else:
            #Do saving routine.
            direc = path.dirname(self.path)
            extension = path.splitext(findings)[1]
            try:
                image_path = path.join(direc, self.album+extension)
                if not path.exists(image_path):
                    with open(image_path, "w+") as f:
                        #urlopen could fail so it's wrapped in try.
                        f.write(urlopen(findings).read())
                        f.close()
            except:
                return False
            return True
        
    def run(self):
        return self.search_album()

         
class CoverFetcher(EventPlugin):
    PLUGIN_ID = "CoverFetcher"
    PLUGIN_NAME = _("Album art fetcher")
    PLUGIN_DESC = _("Automatically downloads and saves album art for current"+
            " playing album.\nMakes use of Last.fm and Musicbrainz services.")
    PLUGIN_VERSION = "0.6"
    
    def PluginPreferences(self, parent):
        #import gobject
        import gtk
        #First label
        orde = gtk.Label('')
        orde.set_markup('<b>Order of services</b>\n'
                        +'<i>Recommended: MB=1 LFM=2:</i>')
        hb = gtk.HBox(spacing = 12)
        hb.pack_start(orde, expand = False)
        
        #First entry:
        def changed_mb(field):
            config.set('plugins', 'cover_order_mb', int(field.get_text() or 1))
        def changed_lfm(field):
            config.set('plugins', 'cover_order_lfm', int(field.get_text() or 2))
            
        try:
            mb_text = str(config.get('plugins', 'cover_order_mb'))
        except:
            mb_text = '1'
        try:
            lfm_text = str(config.get('plugins', 'cover_order_lfm'))
        except:
            lfm_text = '2'
        lab_mb = gtk.Label('MusicBrainz')
        entry_mb = gtk.Entry()
        entry_mb.set_text(mb_text)
        entry_mb.connect("changed", changed_mb)
        entry_mb.set_width_chars(1)
        lab_lfm = gtk.Label('Last.FM')
        entry_lfm = gtk.Entry()
        entry_lfm.set_text(lfm_text)
        entry_lfm.connect("changed", changed_lfm)
        entry_lfm.set_width_chars(1)
        hb2 = gtk.HBox(spacing = 12)
        hb2.pack_start(lab_mb, expand = False)
        hb2.pack_start(entry_mb, expand = True)
        hb2.pack_start(lab_lfm, expand = False)
        hb2.pack_start(entry_lfm, expand = True)
        
        
        #Explanation on MB and LFM
        expl_mb = gtk.Label('')
        expl_mb.set_markup('<b>MusicBrainz</b>\nBetter quality.\n'
                            +'Higher chance of finding image.')   
        expl_lfm = gtk.Label('')
        expl_lfm.set_markup('<b>last.fm</b>\nFaster.\nSmaller images.')
        hb3 = gtk.HBox()
        hb3.pack_start(expl_mb, expand=True)
        hb3.pack_start(expl_lfm, expand=True)
        
        #Treshold label
        tresh = gtk.Label('')
        tresh.set_markup('<b>Treshold</b> (for MB, max - 100, min - 20)\n'
        +'<i>How much search results should be tolerated to accept image.</i>')
        hb4 = gtk.HBox(spacing = 12)
        hb4.pack_start(tresh, expand = False)
        
        #Treshold entry
        def changed_tresh(field):
            config.set('plugins', 'cover_tresh', int(field.get_text() or 70))
            
        try:
            tresh_text = config.get('plugins', 'cover_tresh')
        except:
            tresh_text = '70'
        entryt = gtk.Entry()
        entryt.set_text(tresh_text)
        entryt.connect("changed", changed_tresh)
        hb5 = gtk.HBox()
        hb5.pack_start(entryt, expand = True)
        
        #Packing everything.
        vb = gtk.VBox(spacing = 5)
        vb.pack_start(hb, expand = False)
        vb.pack_start(hb2, expand = False)
        vb.pack_start(hb3, expand = False)
        vb.pack_start(hb4, expand = False)
        vb.pack_start(hb5, expand = False)
        return vb
            
    
    def plugin_on_song_started(self, song):
        artist = song.get('artist','')
        album = song.get('album', '')
        path = song.get('~filename', '')
        #This also can be buggy. You see, it's hard to check this kind of thing.
        try:
            mb = int(config.get('plugins', 'cover_order_mb'))
        except:
            mb = 1
        try:
            lfm = int(config.get('plugins', 'cover_order_lfm'))
        except:
            lfm = 2
        if mb < lfm:
            order = ['MB', 'LFM']
        else:
            order = ['LFM', 'MB']
        try:
            treshold = int(config.get('plugins', 'cover_tresh'))
        except:
            treshold = 70
        #We pass all job to threaded class. Let player keep responsive.
        Cover(artist = artist,
              album = album,
              path = path,
              order = order,
              treshold = treshold).start()
    
    def enabled(self):
        self.plugin_on_song_started(player.song)
