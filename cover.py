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
import re


def save(url, directory, album, ext):
    """Saves cover. First argument is URL to remote image.
    Second - directory, where image should be saved.
    Third - album name. Used for cover username.
    Last - image extension.
    
    Usage:
    save("http://...LZZZZ.jpg", "/home/.../music", "Abbey Road", "jpg")"""
    try:
        #I hope, that my patch @
        #http://code.google.com/p/quodlibet/issues/detail?id=784 passed
        #Also would fix issue number 1.
        album = util.fs_illegal_strip(album)
    except:
        pass
    image_path = path.join(directory, album + ext)
    try:
        image_file = open(image_path, "w+")
        image_file.write(urlopen(url).read())
    except:
        return False
    finally:
        try:
            #If opening image failed, then image_file has no .close() method.
            image_file.close()
        except:
            pass
    #No returns happened? We saved it correctly then.
    return True
    
def check_existing_cover(album, file_path):
    extensions = ['.png', '.jpg', '.jpeg']
    try:
        #I hope, that my patch @
        #http://code.google.com/p/quodlibet/issues/detail?id=784 passed
        #Also would fix issue number 1.
        album = util.fs_illegal_strip(album)
    except:
        pass
    
    directory = path.dirname(file_path)
    for extension in extensions:
        if path.exists(path.join(directory, album+extension)):
            return True
    return False

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
        self.order = kw.get('order', ['MB', 'LFM', 'A'])
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
            if order == "A":
                if self.album and self.artist:
                    self.order[key] = (AmazonCover(self.artist,
                                                        self.album,
                                                        self.path), True,)
                else:
                    self.order[key] = (None, False,)
        
    def run(self):
        if check_existing_cover(self.album, self.path):
            return False
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
                return save(image, direc, self.album, extension)
            except:
                return False
            
            
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
    
        self.search = 'http://musicbrainz.org/ws/2/release?limit=4&query='
        #If album name has ! in it, then search is broken. It needs to be esc.
        query = quote(album.replace('!', '\!').replace('-', '\-')
                                                               .encode('utf-8'))
        #If we have artist, we can make more accurate search
        if artist:
            query += quote(' AND artist:%s'%artist.replace('!', '\!')
                                           .replace('-', '\-').encode('utf-8'))
        self.search += query

        from random import randint
        self.img = 'http://ec%d.images-amazon.com/images/P/%s.%02d.LZZZZZZZ.jpg'
        self.img = self.img % (randint(1,3), '%s', randint(1, 9))
        
    def search_album(self):
        try:
            xml = parseString(urlopen(self.search).read())

            release_list = xml.getElementsByTagName('release-list')[0]
            if release_list.getAttribute('count') == 0:
                return False
                
            albums = release_list.getElementsByTagName('release')
            for album in albums:
                if album.getAttribute('ext:score') < self.treshold:
                    continue
                if len(album.getElementsByTagName('asin')) == 0:
                    continue
                else:
                    asin = album.getElementsByTagName('asin')[0]
                    asin = asin.childNodes[0].toxml()
                    return self.download_image(asin)
            return False
        except:
            return False
            
    def download_image(self, asin):
        if not asin:
            #Just to be safe.
            return False
        url = self.img % asin
        #WWe need to check, if image is not 1x1 empty gif.
        image = urlopen(url)
        #I think 500 bytes is pretty reasonable size.
        if image.headers['content-length'] < 500:
            return False
        else:
            image.close()
            directory = path.dirname(self.path)
            try:
                return save(url, directory, self.album, '.jpg')
            except:
                return False

    def run(self):
        return self.search_album()
        
        
class AmazonCover(object):
    """Searches all amazons for cover.
    Arguments - artist, album and path. All required.
    Cover is saved in same directory as song. Image name equals to album name.
    Usage example:
    LastFMCover('The Beatles', 'Abbey Road', 
                '/home/music/The Beatles/song.mp3').run()"""
    def __init__(self, artist, album, path):
        KEY = 'AKIAJVYURRT3Y62RJNEA'
        SEC = 'JMh0Rk3ZvRjsvPxTppJWkHe/gMVd7Ws4XsSIZW/0'
        self.amz = {}
        amzns = ['CA', 'DE', 'FR', 'JP', 'US', 'UK']
        try:
            #We could miss bottlenose package
            import bottlenose
        except:
            #We cannot return there. But at we have len(self.amz) == 0
            print_e('bottlenose package is missing. No amazon search '+
                    'functionality.')
        try:
            for amzn in amzns:
                self.amz[amzn] = bottlenose.Amazon(KEY, SEC , Region = amzn)
        except:
            pass
        self.artist = artist.decode('utf-8')
        self.album = album.decode('utf-8')
        self.path = path
        
    def image_link(self):
        #We could not initalize amazon apis.
        if len(self.amz) == 0:
            return False
        #We will perform search in all possible amazons.
        for amazon in self.amz:
            amazon = self.amz[amazon]
            #Connecting to amazon
            response = amazon.ItemSearch(SearchIndex = "Music",
            ResponseGroup = "Images", Title = self.album, Artist = self.artist)
            xml = parseString(response)
            result_count = xml.getElementsByTagName('TotalResults')[0]
            if result_count.childNodes[0].toxml() == '0':
                continue
            if result_count.childNodes[0].toxml() > '3':
                #Too unaccurate!
                #There may be 2 or 3 versions. But not more.
                continue
            try:
                #There may be no LargeImages
                image = xml.getElementsByTagName('LargeImage')[0]
            except:
                continue
            #Returning image url.
            return image.getElementsByTagName('URL')[0].childNodes[0].toxml()
        #Still no image returned, we failed.
        return False
            
    def download_image(self, link):
        if not link:
            #We didn't got image link.
            return False
        direc = path.dirname(self.path)
        extension = path.splitext(link)[1]
        try:
            return save(link, direc, self.album, extension)
        except:
            return False
             
    def run(self):
        return self.download_image(self.image_link())
            

class CoverFetcher(EventPlugin):
    PLUGIN_ID = "CoverFetcher"
    PLUGIN_NAME = _("Automatic Album Art")
    PLUGIN_DESC = _("Automatically downloads and saves album art for currently"+
            " playing album.")
    PLUGIN_VERSION = "0.7"

    def PluginPreferences(self, parent):
        #import gobject
        import gtk
        
        def _cb_toggled(cb):
            if cb.get_active():
                config.set('plugins', 'cover_'+cb.tag, 'True')
            else:
                config.set('plugins', 'cover_'+cb.tag, '')
        
        #First label
        orde = gtk.Label('')
        orde.set_markup('<b>Services</b>\n'
                        +'<i>Which services should be searched for cover?</i>')
        hb = gtk.HBox(spacing = 12)
        hb.pack_start(orde, expand = False)
        
        vb1 = gtk.VBox(spacing = 6)
        services = [('Amazon', 'A'), ('Last.fm', 'LFM'), ('MusicBrainz', 'MB')]
        for k, s in enumerate(services):
            cb = gtk.CheckButton(s[0])
            cb.tag = s[1]
            cb.connect('toggled', _cb_toggled)
            try:
                if config.get('plugins', 'cover_'+cb.tag) == 'True':
                    cb.set_active(True)
            except:
                cb.set_active(True)
            vb1.pack_start(cb, expand = True)
        
        #Treshold label
        tresh = gtk.Label('')
        tresh.set_markup('<b>Treshold</b> (for MB, max - 100)\n'
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
        vb.pack_start(vb1, expand = False)
        vb.pack_start(hb4, expand = False)
        vb.pack_start(hb5, expand = False)
        return vb
            
    
    def plugin_on_song_started(self, song):
        artist = song.get('artist','')
        album = song.get('album', '')
        path = song.get('~filename', '')
        #This also can be buggy. You see, it's hard to check this kind of thing.
        order = []
        for service in ['MB', 'LFM', 'A']:
            try:
                if config.get('plugins', 'cover_'+service):
                    order.append(service)
            except:
                order.append(service)
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
