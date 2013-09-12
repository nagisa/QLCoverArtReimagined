from os import path
from gi.repository import Gio, GLib, Gtk, Soup
import json
from functools import partial
from hashlib import sha256

from quodlibet.plugins.events import EventPlugin
from quodlibet import app
from quodlibet.formats._audio import AudioFile

session = Soup.Session.new()
session.set_properties(user_agent="QL Automatic Cover Fetcher Plugin")
cover_dir = path.join(GLib.get_user_cache_dir(), 'quodlibet', 'covers')
old_find_cover = None


class SoupDownloaderMixin(object):
    """ This Mixin's entry point is cover_fetched as a callback from
    `session.queue_message` and it expects that data attribute is a mutable
    dictionary.
    """
    def should_download(self, url):
        hour_us = 3600000000
        return GLib.get_real_time() - self.data.get(url, 0) > hour_us

    def cover_fetched(self, session, message, data):
        if self.cancellable and self.cancellable.is_cancelled():
            print_d('Plugin was disabled while the cover was being downloaded')
            return self.callback(False)

        if 200 <= message.get_property('status-code') < 400:
            data['body'] = message.get_property('response-body')
            data['file'] = Gio.file_new_for_path(self.cover_path)
            data['file'].replace_async(None, False, Gio.FileCreateFlags.NONE,
                                       GLib.PRIORITY_DEFAULT, self.cancellable,
                                       self.cover_file_opened, data)
        elif 100 <= message.get_property('status-code'):
            # Status codes less than 100 usually mean a failure on our side
            # (e.g. no internet connection)
            self.callback(False)
        else:
            self.data[self.url] = GLib.get_real_time()
            self.callback(False)

    def cover_file_opened(self, cover_file, result, data):
        out_stream = cover_file.replace_finish(result)
        out_stream.write_bytes_async(data['body'].flatten().get_as_bytes(),
                                     GLib.PRIORITY_DEFAULT, self.cancellable,
                                     self.cover_written, data)

    def cover_written(self, stream, result, data):
        stream.write_bytes_finish(result)
        stream.close(None)  # Operation is cheap enough to not care about async
        self.data[self.url] = GLib.get_real_time()
        self.callback(True)


class CoverProvider(object):
    """
    A base class of all cover providers.
    """
    def __init__(self, song, cancellable=None, callback=lambda x: x,
                 data=None):
        self.song = song
        self.cancellable = cancellable
        self.callback = callback
        self.data = data or {}

    @property
    def cover_path(self):
        """ Returns where the cover would be stored for this song, however
            it doesn't neccessarily mean the cover is actually at the returned
            location.

            Can return None meaning this cover provider wouldn't be able
            to store this cover due to the lack of information.
        """
        return None

    def find_cover(self):
        """ Entry method for finding the cover.

            Should always return a file-like object opened as read-only if any
            and None otherwise.
        """
        cp = self.cover_path
        return open(cp, 'rb') if cp and path.isfile(cp) else None

    def fetch_cover(self):
        """ Entry method for downloading the cover """
        self.callback(False)


class MusicBrainzCoverProvider(CoverProvider, SoupDownloaderMixin):
    @property
    def cover_path(self):
        return path.join(cover_dir, self.mbid) if self.mbid else None

    @property
    def mbid(self):
        return self.song.get('musicbrainz_albumid', None)

    @property
    def url(self):
        if not self.mbid:
            return None
        return 'http://coverartarchive.org/release/{0}/front'.format(self.mbid)

    def fetch_cover(self):
        if not self.mbid:
            print_d("Album MBID is required to fetch the cover, stopping")
            return self.callback(False)
        if not self.should_download(self.url):
            print_d('Decided against downloading cover from MB, stopping')
            return self.callback(False)
        else:
            msg = Soup.Message.new('GET', self.url)
            session.queue_message(msg, self.cover_fetched, {})


class LastFMCoverProvider(CoverProvider, SoupDownloaderMixin):
    @property
    def cover_path(self):
        if self.key:
            return path.join(cover_dir, self.key)

    @property
    def key(self):
        mbid = self.song.get('musicbrainz_albumid', None)
        artist = self.song.get('artist', None)
        album = self.song.get('album', None)
        if mbid:
            return mbid
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
            print_w('Not enough data to get cover from LastFM, stopping')
            return self.callback(False)
        if not self.should_download(self.url):
            print_d('Decided against downloading cover from LastFM, stopping')
            return self.callback(False)

        msg = Soup.Message.new('GET', self.url)
        session.queue_message(msg, self.json_fetched, {})

    def json_fetched(self, session, message, data):
        if self.cancellable.is_cancelled():
            print_d('Plugin was disabled while the album data was being' +
                    ' downloaded')
            return self.callback(False)

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
                    print_d('Could not get cover image of satisfactory size')
                    self.callback(False)
                return
        elif 100 <= message.get_property('status-code'):
            # Status codes less than 100 usually mean a failure on our side
            # (e.g. no internet connection)
            self.callback(False)
            return

        print_w('Could not get JSON from LastFM')
        self.data[self.url] = GLib.get_real_time()
        self.callback(False)


class AutomaticCoverFetcher(EventPlugin):
    PLUGIN_ID = "auto-cover-fetch"
    PLUGIN_NAME = _("Automatic Cover Art Fetcher")
    PLUGIN_DESC = _("Automatically fetch cover art")
    PLUGIN_ICON = Gtk.STOCK_FIND
    PLUGIN_VERSION = "1.0"

    cancellable = Gio.Cancellable.new()
    data = {}
    cover_providers = (MusicBrainzCoverProvider, LastFMCoverProvider,
                       CoverProvider,)
    current_song = None

    def enabled(self):
        global old_find_cover
        print_w('Patching all songs to use our find_cover method')
        if not old_find_cover:
            old_find_cover = AudioFile.find_cover
        AudioFile.find_cover = lambda *x, **k: self.find_cover(*x, **k)
        self.cancellable.reset()

    def disabled(self):
        global old_find_cover
        print_w('Unpatching all songs to use original find_cover method')
        AudioFile.find_cover = old_find_cover
        old_find_cover = None
        self.cancellable.cancel()

    def find_cover(self, song, fallback=True):
        for cover_provider in self.cover_providers:
            cover = cover_provider(song).find_cover()
            if cover:
                return cover
        if fallback:
            return old_find_cover(song)

    def plugin_on_song_started(self, song):
        self.current_song = song

        if song.find_cover(fallback=False):
            return  # We've got nothing to do

        def _run(sources, result=None):
            if result and song is self.current_song:
                app.window.top_bar.image.set_song(song)
                return
            try:
                fetcher = next(sources)(song, self.cancellable, run, self.data)
                fetcher.fetch_cover()
            except StopIteration:
                pass # We have no more sources.
        run = partial(_run, iter(self.cover_providers))
        run()
