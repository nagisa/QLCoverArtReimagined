## [Quodlibet](http://code.google.com/p/quodlibet/)'s Cover Art Reimagined

Quodlibet's cover art system is very limited and is capable only of using
embed covers or covers from filesystem with filenames in some well known
format like `cover.png`.

This plugin monkeypatches quodlibet to introduce extensible cover art
infrastructure so one could fetch covers from everywhere, including the
internet.

Currently plugin provides following cover sources:

* MusicBrainz
* LastFM
* Fallback (uses quodlibet's methods of getting coverart)
* Embed (looks for cover art in audio files)

### Compatibility

Current master branch is only tested to work with 3.0 version of quodlibet.

### Accuracy

Usually this plugin is accurate 99% of time (I never measured, but the previous
version had 97% measured accuracy, and current version should be much
more accurate)

### Install instructions

#### Linux:

```
$ git clone https://github.com/nagisa/QLCoverFetcher.git /tmp/cover
$ cd /tmp/cover
$ mkdir -p ~/.quodlibet/plugins/events
$ cp {cover.py,waiting-icon.png} ~/.quodlibet/plugins/events
```

Then relaunch quodlibet and enable `Cover Art Reimagined` plugin.

#### Windows:

Put cover.py and waiting-icon.png of this repository into
`C:\Python2.x\Lib\site-packages\quodlibet\plugins\events\ `

Then relaunch quodlibet and enable `Cover Art Reimagined` plugin.
