<h1><a href="http://code.google.com/p/quodlibet/">Quodlibet</a> Automatic Album Art Downloader</h1>

<h2>Statistics</h2>

<ul>
<li>Total: 383 albums</li>
<li>More than 500x500: 15 images</li>
<li>Around 500x500: 331 image</li>
<li>Around 250x250: 20 images</li>
<li>Less than 250x250: 6 images</li>
<li>Incorrect images: 1 image</li>
<li>Not found: 10 images</li>
</ul>

<p>So fetcher has about 97% accuracy and everything&#39;s automatic!</p>

<p>Notes:</p>

<ul>
<li>Some testing albums were brand-new, so I couldn&#39;t even find cover on google</li>
<li>Some albums were with pretty dirty tags.</li>
<li>A lot of pseudo-releases.</li>
</ul>

<h2>Install instructions</h2>

<h3>Step 1:</h3>

<h4>Dependencies:</h4>

<ul>
<li><a href="https://github.com/dlo/bottlenose">bottlenose</a> - <code>easy_install bottlenose</code> or <code>pip install bottlenose</code></li>
<li><a href="http://www.crummy.com/software/BeautifulSoup/">BeautifulSoup</a> - <code>easy_install BeautifulSoup</code> or <code>pip install BeautifulSoup</code></li>
</ul>

<h3>Step 2:</h3>

<h4>Linux:</h4>

<p>Put cover.py inside <code>/usr/lib/python2.x/site-packages/quodlibet/plugins/events/</code></p>

<p><code>sudo cp ./cover.py /usr/lib/python2.7/site-packages/quodlibet/plugins/events/cover.py</code></p>

<h4>Windows:</h4>

<p>Put cover.py into <code>C:\Python2.x\Lib\site-packages\quodlibet\plugins\events\</code></p>

<h3>Step 3:</h3>

<ul>
<li>Relaunch Quodlibet</li>
<li>Enable <code>Automatic Album Art</code> in <code>Music</code>&gt;<code>Plugins</code></li>
</ul>

<h2>Check your quodlibet version!</h2>

<p>If you are using Quodlibet 2.3 or below, you should use files tagged with ql2.3</p>
