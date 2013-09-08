## [Quodlibet](http://code.google.com/p/quodlibet/) Automatic Cover Art Fetcher

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
$ cp cover.py ~/.quodlibet/plugins/events
```

Then relaunch quodlibet and enable `Automatic Cover Art Fetcher` plugin.

#### Windows:

Put cover.py of this repository into
`C:\Python2.x\Lib\site-packages\quodlibet\plugins\events\\`

Then relaunch quodlibet and enable `Automatic Cover Art Fetcher` plugin.
