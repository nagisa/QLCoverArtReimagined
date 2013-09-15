from os import path
from gi.repository import Gio, GLib, Gtk, Soup, GObject
import json
from functools import partial
from hashlib import sha256

from quodlibet.plugins.events import EventPlugin
from quodlibet.plugins.songsmenu import SongsMenuPlugin
from quodlibet.qltk.ccb import ConfigCheckButton
from quodlibet.qltk.cover import CoverImage
from quodlibet import app, config
from quodlibet.formats._audio import AudioFile

session = Soup.Session.new()
session.set_properties(user_agent="Quodlibet Cover Art Reimagined/1.0")


class CoverSource(GObject.Object):
    __gsignals__ = {
        'cover-found': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'failed': (GObject.SignalFlags.RUN_LAST, None, (str,))
    }

    def __init__(self, song, cancellable=None):
        self.song = song
        self.cancellable = cancellable
        super(CoverSource, self).__init__()

    @staticmethod
    def priority():
        return 0.0

    @property
    def cover_path(self):
        """
        Returns where the cover would be stored for this song, however
        it doesn't neccessarily mean the cover is actually at the returned
        location neither that it will be stored there.

        Can return None meaning this cover provider wouldn't be able
        to store this cover due to the lack of information.
        """
        return None

    @property
    def cover(self):
        """
        Method to get cover from cover provider for that specific song.
        Should always return a file-like object opened as read-only if any
        and None otherwise.
        """
        cp = self.cover_path
        return open(cp, 'rb') if cp and path.isfile(cp) else None

    def fetch_cover(self):
        """ Entry method for downloading the cover """
        self.emit('failed', 'This source is incapable of fetching covers')


class EmbedCover(CoverSource):
    @staticmethod
    def priority():
        if config.getboolean("albumart", "prefer_embedded", False):
            return 0.99
        else:
            return 0.01

    @property
    def cover(self):
        if "~picture" in self.song:
            return self.song.get_format_cover()


class FallbackCover(CoverSource):
    """ This cover source fallbacks to quodlibet code for finding covers """
    @staticmethod
    def priority():
        return 0.05

    @property
    def cover(self):
        return self.song.find_cover()


class SoupDownloaderMixin:
    tried_urls = {}

    def should_download(self, url):
        hour_us = 3600000000
        return GLib.get_real_time() - self.tried_urls.get(url, 0) > hour_us

    def cover_fetched(self, session, message, data):
        if self.cancellable and self.cancellable.is_cancelled():
            return self.emit('failed', _('Plugin was disabled while the ' +
                                         'cover was being downloaded'))

        if 200 <= message.get_property('status-code') < 400:
            data['body'] = message.get_property('response-body')
            data['file'] = Gio.file_new_for_path(self.cover_path)
            data['file'].replace_async(None, False, Gio.FileCreateFlags.NONE,
                                       GLib.PRIORITY_DEFAULT, self.cancellable,
                                       self.cover_file_opened, data)
        elif 100 <= message.get_property('status-code'):
            # Status codes less than 100 usually mean a failure on our side
            # (e.g. no internet connection)
            self.emit('failed', _('Could not download cover, failure on ' +
                                   'our side'))
        else:
            self.tried_urls[self.url] = GLib.get_real_time()
            self.emit('failed', _('Server did not return a cover'))

    def cover_file_opened(self, cover_file, result, data):
        out_stream = cover_file.replace_finish(result)
        out_stream.write_bytes_async(data['body'].flatten().get_as_bytes(),
                                     GLib.PRIORITY_DEFAULT, self.cancellable,
                                     self.cover_written, data)

    def cover_written(self, stream, result, data):
        stream.write_bytes_finish(result)
        stream.close(None)  # Operation is cheap enough to not care about async
        self.tried_urls[self.url] = GLib.get_real_time()
        self.emit('cover-found', self.cover)


class MusicBrainzCover(CoverSource, SoupDownloaderMixin):
    @staticmethod
    def priority():
        return 0.90 # pretty accurate

    @property
    def cover_path(self):
        if config.getboolean('albumart', 'prefer_song_dir', False):
            base = path.dirname(self.song['~filename'])
        else:
            base = path.join(GLib.get_user_cache_dir(), 'quodlibet', 'covers')
        return path.join(base, self.mbid) if self.mbid else None

    @property
    def mbid(self):
        return self.song.get('musicbrainz_albumid', None)

    @property
    def url(self):
        if not self.mbid: return None
        mbid = Soup.URI.encode(self.mbid, None)
        return 'http://coverartarchive.org/release/{0}/front'.format(mbid)

    def fetch_cover(self):
        if not self.mbid:
            return self.emit('failed',
                            _('MBID is required to fetch the cover, stopping'))
        if not self.should_download(self.url):
            return self.emit('failed',
                             _('Decided against downloading cover from MB'))
        msg = Soup.Message.new('GET', self.url)
        session.queue_message(msg, self.cover_fetched, {})


class LastFMCover(CoverSource, SoupDownloaderMixin):
    @staticmethod
    def priority():
        return 0.33 # pretty horrible quality of average cover

    @property
    def cover_path(self):
        if config.getboolean('albumart', 'prefer_song_dir', False):
            base = path.dirname(self.song['~filename'])
        else:
            base = path.join(GLib.get_user_cache_dir(), 'quodlibet', 'covers')
        return path.join(base, self.key) if self.key else None

    @property
    def key(self):
        mbid = self.song.get('musicbrainz_albumid', None)
        artist = self.song.get('artist', None)
        album = self.song.get('album', None)
        if mbid: return mbid
        elif album and artist:
            key = sha256()
            key.update(artist.encode('utf-8'))
            key.update(album.encode('utf-8'))
            return key.hexdigest()
        else: return None

    @property
    def url(self):
        _url = 'http://ws.audioscrobbler.com/2.0?method=album.getinfo&' + \
               'api_key=2dd4db6614e0f314b4401a92dce5e04a&format=json&' +\
               '&artist={artist}&album={album}&mbid={mbid}'
        artist = Soup.URI.encode(self.song.get('artist', ''), None)
        album = Soup.URI.encode(self.song.get('album', ''), None)
        mbid = Soup.URI.encode(self.song.get('musicbrainz_albumid', ''), None)
        if artist and album or mbid:
            return _url.format(artist=artist, album=album, mbid=mbid)
        else:
            return None  # Not enough data

    def fetch_cover(self):
        if not self.url:
            self.emit('failed', _('Not enough data to get cover from LastFM'))
            return
        if not self.should_download(self.url):
            self.emit('failed', _('Decided against downloading from LastFM'))
            return
        msg = Soup.Message.new('GET', self.url)
        session.queue_message(msg, self.json_fetched, {})

    def json_fetched(self, session, message, data):
        if self.cancellable.is_cancelled():
            return self.emit('failed', _('Plugin was disabled while the ' +
                                         'cover was being downloaded'))

        # LastFM always return code 200, but we might still get
        # something else in who knows what cases.
        if 200 <= message.get_property('status-code') < 400:
            r = message.get_property('response-body').flatten().get_data()
            rjson = json.loads(r)
            album = rjson.get('album', {})
            if album:
                covers = dict((img['size'], img['#text'])
                              for img in album['image'])
                cover = covers.get('mega', covers.get('extralarge', None))
                if cover:
                    msg = Soup.Message.new('GET', cover)
                    session.queue_message(msg, self.cover_fetched, data)
                else:
                    self.emit('failed', _("Didn't found satisfactory cover"))
                return
        elif 100 <= message.get_property('status-code'):
            # Status codes less than 100 usually mean a failure on our side
            # (e.g. no internet connection)
            self.emit('failed', _('Could not download cover, failure on ' +
                                   'our side'))
            return

        self.emit('failed', _('Could not get album data from LastFM'))
        self.tried_urls[self.url] = GLib.get_real_time()


class CoverReimagined(EventPlugin):
    PLUGIN_ID = "cover-reimagined"
    PLUGIN_NAME = _("Cover Arts Reimagined")
    PLUGIN_DESC = _("Quodlibet cover arts reimagined")
    PLUGIN_ICON = Gtk.STOCK_FIND
    PLUGIN_VERSION = "1.0"

    cancellable = Gio.Cancellable.new()
    providers = [MusicBrainzCover, LastFMCover, EmbedCover, FallbackCover]

    def __init__(self):
        self.old_methods = {
            'CoverImage.set_song': CoverImage.set_song,
        }
        return super(CoverReimagined, self).__init__()

    def enabled(self):
        print_w('Monkey-patching quodlibet')
        current_loc = path.dirname(path.abspath(__file__))
        self.wait_file = open(path.join(current_loc, 'waiting-icon.png'), 'rb')
        CoverImage.set_song = lambda s, song: set_song(s, song, plugin=self)
        self.cancellable.reset()

    def disabled(self):
        print_w('Un-monkey-patching quodlibet')
        CoverImage.set_song = self.old_methods['CoverImage.set_song']
        self.wait_file.close()
        self.cancellable.cancel()

    def PluginPreferences(self, parent):
        prefer_lbl = _("Store cover into the directory of song")
        prefer_key = 'prefer_song_dir'

        grid = Gtk.Grid.new()
        prefer_cb = ConfigCheckButton(prefer_lbl, 'albumart', prefer_key)
        prefer_cb.set_active(config.getboolean('albumart', prefer_key, False))
        grid.attach(prefer_cb, 0, 0, 1, 1)

        return grid


def set_song(self, song, plugin=None):
    self._CoverImage__song = song
    self._CoverImage__file = plugin.wait_file
    self.get_child().set_path(plugin.wait_file and plugin.wait_file.name)


    def success(source, cover):
        if not plugin.cancellable.is_cancelled():
            self._CoverImage__file = cover
            self.get_child().set_path(cover and cover.name)

    def failure(source, error):
        if not plugin.cancellable.is_cancelled():
            run() # Try another source

    def _run(providers):
        try:
            provider_cls = next(providers)
        except StopIteration:
            self._CoverImage__file = None
            self.get_child().set_path(None)
        else:
            provider = provider_cls(song, plugin.cancellable)
            provider.connect('cover-found', success)
            provider.connect('failed', failure)
            cover = provider.cover
            if cover:
                # This is ugly
                provider.emit('cover-found', cover)
            else:
                provider.fetch_cover()

    run = partial(_run, iter(sorted(plugin.providers, reverse=True,
                                    key=lambda x: x.priority())))
    run()
