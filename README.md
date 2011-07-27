Quodlibet Automatic Album Art
=============================

## Statistics

Having 354 albums with „maybe“ correct tags. Some of them misses artist, some - album name itself.
This script found and downloaded 338 album arts. Of which 16 were bigger than 500x500. 3 of them was smaller.
Only 1 cover was incorrect.
Worth mentioning, that most of music was pretty random - japanese music, some random releases and even fan-music.

So this script has about 95% success rate. And everything is automatic!

## Install instructions
 
#### Linux

- For Amazon support you will need bottlenose package.

    sudo easy_install bottlenose
    
- Put cover.py inside /usr/lib/python2.**x**/site-packages/quodlibet/plugins/events/

    sudo cp cover.py /usr/lib/python2.7/site-packages/quodlibet/plugins/events/cover.py
    
- Relaunch Quodlibet
- Enable plugin in Music>Plugins

#### Windows

- Install bottlenose
- Put cover.py inside C:\Python2.**x**\Lib\site-packages\quodlibet\plugins\events\
- Relaunch Quodlibet
- Enable plugin in Music>Plugins


#### Mac OS

- Linux instructions should be OK. Not sure about that.
