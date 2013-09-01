from os import path
from gi.repository import Gio, GLib, Gtk, Soup
import json

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
    def cover_fetched(self, session, message, data):
        if self.cancellable and self.cancellable.is_cancelled():
            print_d('Plugin was disabled while the cover was being downloaded')
            return self.callback(False)

        if 200 <= message.get_property('status-code') < 400:
            data['body'] = message.get_property('response-body')
            data['file'] = self.cover_gfile
            data['file'].replace_async(None, False, Gio.FileCreateFlags.NONE,
                                       GLib.PRIORITY_DEFAULT, self.cancellable,
                                       self.cover_file_opened, data)
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
        self.cover_path = data['file'].get_path()
        self.callback(True)


class CoverProvider(object):
    """ Abstracts all cover providers that store path to their fetched cover
    in ~#cover-path
    """
    def __init__(self, song, cancellable=None, callback=lambda x: x,
                 data=None):
        self.song = song
        self.cancellable = cancellable
        self.callback = callback
        self.data = data or {}

    @property
    def cover_path(self):
        return self.song.get('~#cover-path', None)

    @cover_path.setter
    def cover_path(self, val):
        self.song['~#cover-path'] = val

    def find_cover(self):
        if self.cover_path and path.isfile(self.cover_path):
            return open(self.cover_path, 'rb')

    def fetch_cover(self):
        self.callback(False)


class MusicBrainzCoverProvider(CoverProvider, SoupDownloaderMixin):
    @property
    def url(self):
        return 'http://coverartarchive.org/release/{0}/front'.format(self.mbid)

    @property
    def cover_gfile(self):
        return Gio.file_new_for_path(self.mb_cover_path)

    @property
    def mbid(self):
        return self.song.get('musicbrainz_albumid', None)

    @property
    def mb_cover_path(self):
        return path.join(cover_dir, self.mbid)

    def find_cover(self):
        cover = super(MusicBrainzCoverProvider, self).find_cover()
        if cover: return cover
        elif path.isfile(self.mb_cover_path):
            print_d('Found already existing cover art, stopping')
            self.cover_path = self.mb_cover_path
            return open(self.mb_cover_path, 'rb')
        else: return None

    def fetch_cover(self):
        if not self.mbid:
            print_d("Album MBID is required to fetch the cover, stopping")
            return self.callback(False)
        hour = 3600000000
        if GLib.get_real_time() - self.data.get(self.url, 0) < hour:
            print_d('Tried downloading this not too long ago, stopping')
            return self.callback(False)
        msg = Soup.Message.new('GET', self.url)
        session.queue_message(msg, self.cover_fetched, {})


class LastFMCoverProvider(CoverProvider, SoupDownloaderMixin):
    @property
    def url(self):
        _url = 'http://ws.audioscrobbler.com/2.0?method=album.getinfo&' + \
               'api_key=2dd4db6614e0f314b4401a92dce5e04a&format=json&' +\
               '&artist={artist}&album={album}&mbid={mbid}'
        artist = Soup.URI.encode(self.song.get('artist', ''), None)
        album = Soup.URI.encode(self.song.get('album', ''), None)
        mbid = Soup.URI.encode(self.song.get('musicbrainz_albumid', ''), None)
        if not (artist and album) or not mbid:
            return None  # Not enough data
        return _url.format(artist=artist, album=album, mbid=mbid)

    @property
    def cover_gfile(self):
        return Gio.file_new_for_path(self.lastfm_cover_path)

    @property
    def lastfm_mbid(self):
        return self.song.get('~#lastfm-musicbrainz-albumid', None)

    @lastfm_mbid.setter
    def lastfm_mbid(self, val):
        self.song['~#lastfm-musicbrainz-albumid'] = val

    @property
    def lastfm_cover_path(self):
        return path.join(cover_dir, self.lastfm_mbid)

    def find_cover(self):
        cover = super(LastFMCoverProvider, self).find_cover()
        if cover: return cover
        elif self.lastfm_mbid and path.isfile(self.lastfm_cover_path):
            print_d('Found already existing cover art, stopping')
            self.cover_path = self.lastfm_cover_path
            return open(self.lastfm_cover_path, 'rb')
        else: return None

    def fetch_cover(self):
        if not self.url:
            print_w('Not enough data to get cover from LastFM, stopping')
            return self.callback(False)
        hour = 3600000000
        if GLib.get_real_time() - self.data.get(self.url, 0) < hour:
            print_d('Tried downloading this not too long ago, stopping')
            return self.callback(False)

        msg = Soup.Message.new('GET', self.url)
        session.queue_message(msg, self.json_fetched, {})

    def json_fetched(self, session, message, data):
        if self.cancellable.is_cancelled():
            print_d('Plugin was disabled while the cover was being downloaded')
            return self.callback(False)

        # LastFM always return code 200, but we might still get
        # something else in some corner case
        if 200 <= message.get_property('status-code') < 400:
            resp = message.get_property('response-body').flatten().get_data()
            resp_json = json.loads(resp)
            album = resp_json.get('album', {})
            if album:
                self.lastfm_mbid = album['mbid']
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

        self.data[self.url] = GLib.get_real_time()
        self.callback(False)
        print_w('Could not get JSON from LastFM')


class AutomaticCoverFetcher(EventPlugin):
    PLUGIN_ID = "auto-cover-fetch"
    PLUGIN_NAME = _("Automatic Cover Art Fetcher")
    PLUGIN_DESC = _("Automatically fetch cover art")
    PLUGIN_ICON = Gtk.STOCK_FIND
    PLUGIN_VERSION = "1.0"

    cancellable = Gio.Cancellable.new()
    data = {}
    cover_providers = (MusicBrainzCoverProvider, LastFMCoverProvider,
                       CoverProvider)
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

        def run(to_try, result):
            if result and song is self.current_song:
                app.window.top_bar.image.set_song(song)
            elif to_try:
                callback = lambda x: run(to_try, x)
                to_try.pop(0)(song, self.cancellable, callback,
                              self.data).fetch_cover()

        run(list(self.cover_providers), None)
