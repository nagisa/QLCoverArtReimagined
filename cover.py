from os import path
from gi.repository import Gio, GLib, Gtk, Soup
import functools

from quodlibet.plugins.events import EventPlugin
from quodlibet import app
from quodlibet.formats._audio import AudioFile

session = Soup.Session.new()
session.set_properties(user_agent="QL Automatic Cover Fetcher Plugin")
cover_dir = path.join(GLib.get_user_cache_dir(), 'quodlibet', 'covers')
old_find_cover = None


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
        self.callback(None)


class MusicBrainzCoverProvider(CoverProvider):
    url = 'http://coverartarchive.org/release/{mbid}/front'

    @property
    def mbid(self):
        return self.song.get('musicbrainz_albumid', None)

    @property
    def mb_cover_path(self):
        return path.join(cover_dir, self.mbid)

    def find_cover(self):
        cover = super(MusicBrainzCoverProvider, self).find_cover()
        if cover:
            return cover
        elif path.isfile(self.mb_cover_path):
            print_d('Found already existing cover art, stopping')
            self.cover_path = self.mb_cover_path
            return open(self.mb_cover_path, 'rb')
        else:
            return None

    def fetch_cover(self):
        if not self.mbid:
            print_d("Album MBID is required to fetch the cover, stopping")
            return self.callback(None)

        hour = 3600000000
        if GLib.get_real_time() - self.data.get(self.mbid, 0) < hour:
            print_d('Tried downloading this not too long ago, stopping')
            return self.callback(None)

        msg = Soup.Message.new('GET', self.url.format(mbid=self.mbid))
        session.queue_message(msg, self.cover_fetched, {})

    def cover_fetched(self, session, message, data):
        if self.cancellable.is_cancelled():
            print_d('Plugin was disabled while the cover was being downloaded')
            return self.callback(None)

        if message.get_property('status-code') == 200:
            data['body'] = message.get_property('response-body')
            data['file'] = Gio.file_new_for_path(self.mb_cover_path)
            data['file'].replace_async(None, False, Gio.FileCreateFlags.NONE,
                                       GLib.PRIORITY_DEFAULT, self.cancellable,
                                       self.cover_file_opened, data)
            print_d('Downloaded cover art from CoverArtArchive')
        else:
            self.data[self.mbid] = GLib.get_real_time()
            print_w('Could not get the cover from CoverArtArchive')


    def cover_file_opened(self, cover_file, result, data):
        out_stream = cover_file.replace_finish(result)
        out_stream.write_bytes_async(data['body'].flatten().get_as_bytes(),
                                     GLib.PRIORITY_DEFAULT, self.cancellable,
                                     self.cover_written, data)

    def cover_written(self, stream, result, data):
        stream.write_bytes_finish(result)
        stream.close(None)  # Operation is cheap enough to not care about async
        self.cover_path = data['file'].get_path()
        self.callback(data['file'].get_path())


class AutomaticCoverFetcher(EventPlugin):
    PLUGIN_ID = "auto-cover-fetch"
    PLUGIN_NAME = _("Automatic Cover Art Fetcher")
    PLUGIN_DESC = _("Automatically fetch cover art")
    PLUGIN_ICON = Gtk.STOCK_FIND
    PLUGIN_VERSION = "1.0"

    cancellable = Gio.Cancellable.new()
    data = {}
    cover_providers = (MusicBrainzCoverProvider, CoverProvider)
    current_song = None

    def enabled(self):
        global old_find_cover
        print_w('Patching all songs to use our find_cover method')
        if not old_find_cover:
            old_find_cover = AudioFile.find_cover
        AudioFile.find_cover = lambda *x: self.find_cover(*x)

        self.cancellable.reset()

    def disabled(self):
        global old_find_cover
        print_w('Unpatching all songs to use original find_cover method')
        AudioFile.find_cover = old_find_cover
        old_find_cover = None

        self.cancellable.cancel()

    def find_cover(self, song):
        for cover_provider in self.cover_providers:
            cover = cover_provider(song).find_cover()
            if cover:
                return cover
        return old_find_cover(song)

    def plugin_on_song_started(self, song):
        self.current_song = song

        if song.find_cover():
            return  # We've got nothing to do

        def run(to_try, result):
            if result and song is self.current_song:
                app.window.top_bar.image.set_song(song)
            elif to_try:
                callback = lambda x: run(to_try, x)
                to_try.pop(0)(song, self.cancellable, callback,
                              self.data).fetch_cover()

        run(list(self.cover_providers), None)
