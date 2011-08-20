[Quodlibet](http://code.google.com/p/quodlibet/) Automatic Album Art Downloader
===============================================================================

## Statistics

* Total: 383 albums
* More than 500x500: 15 images
* Around 500x500: 331 image
* Around 250x250: 20 images
* Less than 250x250: 6 images
* Incorrect images: 1 image
* Not found: 10 images

So fetcher has about 97% accuracy and everything's automatic!

Notes:

* Some testing albums were brand-new, so I couldn't even find cover on google
* Some albums were with pretty dirty tags.
* A lot of pseudo-releases.

## Install instructions

### Step 1:

#### Dependencies:

* [bottlenose](https://github.com/dlo/bottlenose) - `easy_install bottlenose` or `pip install bottlenose`
* [BeautifulSoup](http://www.crummy.com/software/BeautifulSoup/) - `easy_install BeautifulSoup` or `pip install BeautifulSoup`

### Step 2:

#### Linux:

Put cover.py inside `/usr/lib/python2.x/site-packages/quodlibet/plugins/events/`

`sudo cp ./cover.py /usr/lib/python2.7/site-packages/quodlibet/plugins/events/cover.py`

#### Windows:

Put cover.py into `C:\Python2.x\Lib\site-packages\quodlibet\plugins\events\`

### Step 3:

* Relaunch Quodlibet
* Enable `Automatic Album Art` in `Music`>`Plugins`

## One more notice

Due to quodlibet restrictions cover will appear only when you play album second time.
