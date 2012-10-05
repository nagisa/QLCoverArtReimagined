# -*- coding: utf-8 -*-
# Copyright 2012 Simonas Kazlauskas

# Same licence as Quodlibet (http://code.google.com/p/quodlibet/)

from quodlibet.plugins.events import EventPlugin
from quodlibet.player import playlist as player
from quodlibet import config, app
from os import path
from urllib2 import urlopen, URLError
from urllib import quote
from xml.dom.minidom import parseString
from threading import Thread
from random import randint
from urlparse import urljoin
import struct


debug = True
if debug:
    from sys import exc_info
    from traceback import print_exception


def debugger(message):
    print_d('[AutoAlbumArt] %s' % message)
    if debug:
        print_exception(*exc_info())


def fs_strip(s, replace=None):
    """
    Strips illegal filesystem characters from album.
    See issue http://code.google.com/p/quodlibet/issues/detail?id=784
    """
    replace = replace or " "
    illegals = '/?<>\:*|"^'  # ^ is illegal in FAT, only / is illegal in Unix.
    return reduce(lambda q, c: q.replace(c, replace), illegals, s)


def is_enabled(tag, default=True):
    """
    Checks if plugin is enabled, give it's tag as argument.

    Usage:
    is_enabled('MB') #Checks if MusicBrainz is enabled.
    """
    try:
        if config.get('plugins', 'cover_' + tag):
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
        if self.check_existing_cover():
            return True
        images = []
        for fetcher in self.order:
            image = fetcher(self.song).run()
            if is_enabled('get_biggest') and image:
                images.append(image)
            elif not is_enabled('get_biggest') and image and self.save(image):
                return True
        if images:
            return self.save(images)
        return False

    def reload_image(self):
        # Show image instantly!
        # Thanks to http://code.google.com/p/quodlibet/issues/detail?id=780#c22
        # Don't show image, if quodlibet's already playing another song.
        if player.song['~filename'] == self.song['~filename']:
            app.window.image.set_song(None, self.song)

    def biggest_image(self, images):
        tmp = []
        for url in images:
            try:
                h = -1
                w = -1
                data = urlopen(url).read(24)
                size = len(data)
                if (size >= 10) and data[:6] in ('GIF87a', 'GIF89a'):
                    w, h = struct.unpack("<HH", data[6:10])
                    tmp.append((url, int(w) * int(h)))
                    continue
                elif ((size >= 24) and data.startswith('\211PNG\r\n\032\n')
                    and (data[12:16] == 'IHDR')):
                    w, h = struct.unpack(">LL", data[16:24])
                    tmp.append((url, int(w) * int(h)))
                    continue
                elif (size >= 16) and data.startswith('\211PNG\r\n\032\n'):
                    w, h = struct.unpack(">LL", data[8:16])
                    tmp.append((url, int(w) * int(h)))
                    continue
                #JPEG suks :D
                image = urlopen(url)
                data = str(image.read(2))
                if data.startswith('\377\330'):
                    b = image.read(1)
                    try:
                        while (b and ord(b) != 0xDA):
                            while (ord(b) != 0xFF):
                                b = image.read(1)
                            while (ord(b) == 0xFF):
                                b = image.read(1)
                            if (ord(b) >= 0xC0 and ord(b) <= 0xC3):
                                image.read(3)
                                h, w = struct.unpack(">HH", image.read(4))
                                break
                            else:
                                image.read(int(
                                    struct.unpack(">H", image.read(2))[0]) - 2)
                            b = image.read(1)
                        tmp.append((url, int(w) * int(h)))
                        continue
                    except struct.error:
                        pass
                    except ValueError:
                        pass
            except URLError:
                debugger("Failed to open image at %s" % url)
            except:
                debugger("Failed to get image size of %s" % url)
                tmp.append((url, 0))
                continue
        return max(tmp, key=lambda x: x[1])

    def save(self, images):
        directory = path.dirname(self.song['~filename'])
        try:
            link = "" + images
        except TypeError:
            link = self.biggest_image(images)[0]
        #May have album name, labelid, and so on as name...
        if is_enabled('cover_names', False):
            image_name = "%s cover" + path.splitext(str(link))[1]
        else:
            image_name = "%s" + path.splitext(str(link))[1]
        if is_enabled('labelid_names') and self.song.get('labelid', False):
            image_name = image_name % self.song['labelid']
        elif self.song.get('album', False):
            image_name = image_name % fs_strip(self.song['album'])
        else:
            #Could not construct name for image
            return False
        image_path = path.join(directory, image_name)
        try:
            image_file = open(image_path, "w+")
            image_file.write(urlopen(link).read())
            image_file.close()
            self.reload_image()
            return True
        except:
            debugger('Failed to save image from %s to %s' % (link, image_path))
        return False

    def check_existing_cover(self):
        """
        Checks if cover art already exists.
        Uses quodlibet cover matching algorithm.
        """
        if is_enabled('reload'):
            return False
        if not self.song.find_cover() == None:
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
        self.album = song.get('album', '').encode('utf-8')
        self.artist = song.get('artist', '').encode('utf-8')
        url = "%s?method=album.getinfo&api_key=%s&artist=%s&album=%s"
        self.url = url % (api, apikey, quote(self.artist), quote(self.album))

    def passes(self):
        if not self.album or not self.artist:
            return False
        else:
            return True

    def run(self):
        if not self.passes() or not is_enabled('LFM'):
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
                return image_url
        except URLError, e:
            #Last.fm produces 400 error if artist/album not found.
            #It's expected error, and should produce no message.
            if not int(e.code) == 400:
                debugger('Failed to open %s' % self.url)
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
        specials = ['\\', '+', '-', '&&', '||', '!', '(', ')', '{', '}', '[',
                    ']', '^', '"', '~', '*', '?', ':']
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

        #MBID url
        if song.get('musicbrainz_albumid', False):
            mbid = song['musicbrainz_albumid']
            self.mbid_url = 'http://musicbrainz.org/ws/2/release/%s' % mbid

        #Artist - Album url
        url = 'http://musicbrainz.org/ws/2/release?limit=4&query=%s'
        query = quote(self.escape_query(self.album))
        if artist:
            #If we have artist, we can make more accurate search
            query += quote(' AND artist:%s' % self.escape_query(artist))
        self.url = url % query

        #Amazon image url pattern.
        self.img = 'http://ec%d.images-amazon.com/images/P/%s.%02d.LZZZZZZ.jpg'
        self.img = self.img % (randint(1, 3), '%s', randint(1, 9))

    def passes(self, mbid=False):
        if mbid:
            return hasattr(self, 'mbid_url')
        else:
            return bool(self.url) and bool(self.album)

    def run(self):
        #Run search with MBID, if possible.
        if is_enabled('MB'):
            if self.passes(mbid=True):
                try:
                    xml = parseString(urlopen(self.mbid_url).read())
                    if not len(xml.getElementsByTagName('asin')) == 0:
                        asin = xml.getElementsByTagName('asin')[0]
                        asin = asin.childNodes[0].toxml()
                        return self.make_image_url(asin)
                except URLError:
                    debugger('Failet to open %s' % self.mbid_url)
                except:
                    debugger('MB - unexpected error')
            if self.passes():
                try:
                    xml = parseString(urlopen(self.url).read())
                    release_list = xml.getElementsByTagName('release-list')[0]
                    if int(release_list.getAttribute('count')) == 0:
                        return False
                    albums = release_list.getElementsByTagName('release')
                    for album in albums:
                        if int(album.getAttribute('ext:score')) < self.treshold:
                            break
                        if len(album.getElementsByTagName('asin')) == 0:
                            continue
                        else:
                            asin = album.getElementsByTagName('asin')[0]
                            asin = asin.childNodes[0].toxml()
                            return self.make_image_url(asin)
                except URLError:
                    debugger('Failet to open %s' % self.url)
                except:
                    debugger('MB - unexpected error')
            else:
                return False
        return False

    def make_image_url(self, asin):
        url = self.img % asin
        #We need to check, if image is not 1x1 empty gif.
        try:
            image = urlopen(url)
            #500 bytes treshold is pretty reasonable for this check.
            if image.headers['content-length'] < 500:
                return False
            else:
                image.close()
        except:
            debugger('Failed to open image %s' % url)
        return url


class AmazonCover(object):
    """
    Searches and downloads cover art from Amazon.

    Usage:
    AmazonCover(quodlibet.player.playlist.song).run()
    """
    def __init__(self, song):
        try:
            import bottlenose
            self.bottlenose = True
        except:
            debugger('No bottlenose package!')
            self.bottlenose = False
            return None
        key = 'AKIAIMIN4TM6PFNAFHLQ'
        sec = 'pq5/QktQyrBqYeH0ikaymv3vV6ngyF8OV+zi+nMk'
        tag = 'musplaplu-20'
        self.amazons = {}
        regions = ['CA', 'CN', 'DE', 'FR', 'IT', 'JP', 'UK', 'US']
        for region in regions:
            self.amazons[region] = bottlenose.Amazon(key, sec, tag,
                                                     Region=region)
        self.artist = song.get('artist', '').decode('utf-8')
        self.album = song.get('album', '').decode('utf-8')

    def passes(self):
        if not self.bottlenose or not self.album or not self.artist:
            return False
        else:
            return True

    def run(self):
        if not self.passes() or not is_enabled('A'):
            return False
        for region, amazon in self.amazons.items():
            try:
                xml = parseString(amazon.ItemSearch(SearchIndex='Music',
                                                    ResponseGroup='Images',
                                                    Title=self.album,
                                                    Artist=self.artist))
                result_count = xml.getElementsByTagName('TotalResults')[0]
                result_count = int(result_count.childNodes[0].toxml())
                if result_count == 0 or result_count > 5:
                    continue
                image = xml.getElementsByTagName('LargeImage')[0]
                image = image.getElementsByTagName('URL')[0]
                image = image.childNodes[0].toxml()
                return image
            except:
                debugger('amazon.%s - Unexpected error' % region)
                continue
        return False


class VGMdbCover(object):
    """
    Searches and downloads cover art from VGMdb.

    Usage:
    VGMdbCover(quodlibet.player.playlist.song).run()
    """
    def __init__(self, song):
        self.album = song.get('album', '').encode('utf-8')
        self.artist = song.get('artist', '').encode('utf-8')
        url = 'http://vgmdb.net/search?q=%%22%s%%22%%20%%22%s%%22'
        self.url = url % (quote(self.artist), quote(self.album))

        if song.get('labelid', False):
            label = quote(song['labelid'])
            self.label_url = 'http://vgmdb.net/search?q=%s' % label
        else:
            self.label_url = False

    def passes(self):
        if not self.album or not self.artist:
            return False
        else:
            return True

    def parse_url(self, url):
        replaceables = ['/assets/covers-medium/', '/assets/covers-thumb/']
        replacement = '/assets/covers/'
        url = reduce(lambda q, c: q.replace(c, replacement), replaceables, url)
        return urljoin('http://vgmdb.net/', url)

    def run(self):
        try:
            from BeautifulSoup import BeautifulSoup
        except ImportError:
            debugger('No BeautifulSoup package!')
            return False
        if not is_enabled('VGM') or not self.passes():
            return False
        try:
            if self.label_url:  # Search by label
                site = urlopen(self.label_url)
                if 'http://vgmdb.net/album/' in site.url:
                    xml = BeautifulSoup(site.read())
                    image = xml.find('img', {'id': 'coverart'})['src']
                    return self.parse_url(image)
            else:  # Search by artist - album.
                site = urlopen(self.url)
                if 'http://vgmdb.net/album/' in site.url:
                    xml = BeautifulSoup(site.read())
                    image = xml.find('img', {'id': 'coverart'})['src']
                    return self.parse_url(image)
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
    PLUGIN_VERSION = "0.9"

    def PluginPreferences(self, parent):
        import gtk

        #Inner functions, mostly callbacks.
        def cb_toggled(cb):
            if cb.get_active():
                config.set('plugins', 'cover_' + cb.tag, 'True')
            else:
                config.set('plugins', 'cover_' + cb.tag, '')

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
        warnings = []
        vb = gtk.VBox(spacing=5)

        #General settings tab
        label = gtk.Label(_('General'))
        settings = gtk.VBox(spacing=5)
        rld = gtk.CheckButton(_('Redownload image, even if it already exists'))
        tip = _('Helps to keep cover up to date')
        tooltip.set_tip(rld, tip)
        rld.tag = 'reload'
        rld.connect('toggled', cb_toggled)
        rld.set_active(is_enabled(rld.tag, False))
        #Use programmatic tags for image names?
        labelid = gtk.CheckButton(_('Use Record Label ID for image names'))
        tip = _('Your image name will look like "PCS-7088.jpg". '
                'Will fallback to another options if there\'s no labelid set.')
        tooltip.set_tip(labelid, tip)
        labelid.tag = 'labelid_names'
        labelid.connect('toggled', cb_toggled)
        labelid.set_active(is_enabled(labelid.tag, True))
        #Look for biggest possible image?
        biggest = gtk.CheckButton(_('Look for biggest possible image'))
        tip = _('This will probably find biggest possible art. '
                'Uses more bandwidth.')
        tooltip.set_tip(biggest, tip)
        biggest.tag = 'get_biggest'
        biggest.connect('toggled', cb_toggled)
        biggest.set_active(is_enabled(biggest.tag, True))
        #Add " cover" to image name?
        cover = gtk.CheckButton(_('Add "cover" to filename.'
                                 ' May cause unexpected behavior.'))
        tip = _('Don\'t do this, unless you really want to see cover on every'
                ' song.')
        tooltip.set_tip(cover, tip)
        cover.tag = 'cover_names'
        cover.connect('toggled', cb_toggled)
        cover.set_active(is_enabled(cover.tag, False))
        settings.pack_start(rld)
        settings.pack_start(labelid)
        settings.pack_start(biggest)
        settings.pack_start(cover)
        notebook.append_page(settings, label)

        #MusicBrainz settings tab
        label = gtk.Label(_('MusicBrainz'))
        settings = gtk.VBox(spacing=5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'MB'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        treshold = gtk.HBox(spacing=10)
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
        settings = gtk.VBox(spacing=5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'LFM'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        notebook.append_page(settings, label)

        #Amazon settings tab
        label = gtk.Label(_('Amazon'))
        try:
            import bottlenose
        except ImportError:
            label.set_markup('<b><span foreground="red">%s</span></b>' % _('Amazon'))
            warnings.append(gtk.Label(_('Amazon: Amazon cover search '
                                        'requires Python bottlenose package!')))

        settings = gtk.VBox(spacing=5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'A'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        notebook.append_page(settings, label)

        #VGMdb settings tab
        label = gtk.Label(_('VGMdb'))
        try:
            import BeautifulSoup
        except ImportError:
            label.set_markup('<b><span foreground="red">%s</span></b>' % _('VGMdb'))
            warnings.append(gtk.Label(_('VGMdb: VGMdb cover search requires'
                                        ' Python BeautifulSoup package!')))
        settings = gtk.VBox(spacing=5)

        enabled = gtk.CheckButton('Enabled')
        enabled.tag = 'VGM'
        enabled.connect('toggled', cb_toggled)
        enabled.set_active(is_enabled(enabled.tag))
        settings.pack_start(enabled)

        notebook.append_page(settings, label)

        vb.pack_start(notebook, True, True)

        #Warnings from fetchers
        for warning in warnings:
            text = warning.get_text()
            warning.set_markup('<span foreground="red">%s</span>' % text)
            vb.pack_start(warning, True, True)

        return vb

    def plugin_on_song_started(self, song):
        #Sometimes song is None, then Thread initiated without real reason
        #and just produces error.
        if not song == None:
            Cover(song).start()
        else:
            return
