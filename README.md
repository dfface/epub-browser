# epub-browser

![GitHub Repo stars](https://img.shields.io/github/stars/dfface/epub-browser)
[![python](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![pypi](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![wheel](https://img.shields.io/pypi/wheel/epub-browser)](https://pypi.org/project/epub-browser/)
[![license](https://img.shields.io/github/license/dfface/epub-browser)](https://pypi.org/project/epub-browser/)
![PyPI - Downloads](https://img.shields.io/pypi/dd/epub-browser)

A simple and modern web E-book reader, which allows you to read e-books within a browser.

Try it online: [https://epub-browser.vercel.app](https://epub-browser.vercel.app)

It now supports:

* Simple library management: searching by title, author or tag.
* Dark mode.
* Page turning/scrolling: support keyboards(left arrow & right arrow & space).
* Kindle mode: more style optimizations; Clicking on both sides of the screen is allowed to turn pages.
* Reading progress bar.
* Table of contents in each chapter(not active in `Page turning mode`).
* Font size/family adjustment.
* Image zoom.
* Mobile devices: especially for Kindle, remember to click `Not Kindle` in the header of home page to enable `Kindle Mode` to optimize experience.
* Code highlight(not active in `Kindle Mode`).
* Remember position: remember your last reading chapter(support all devices including Kindle) and your last reading position(support all devices except Kindle).
* Custom CSS: you can write your own CSS style to improve your reading experience, such as `.content{margin: 50px;}.content p{ font-size: 2rem; }`(All the main content is under the element with the class `content`).
* Can be directly deployed on any web server such as Apache: use `--no-server` parameter.
* Multi threads.
* Sortable: main elements can be dragged.
* Calibre metadata reading: supports the display of tags (dc:subject) and comments (dc:description) edited in [Calibre](https://calibre-ebook.com/) (remember to "Edit book" after "Edit metadata" to save the changes).
* Watchdog: Monitor all EPUB files in the directory specified by the user (or the directory where the EPUB file resides). When there are new additions or updates, automatically add them to the library.

## Usage

Type the command in the terminal:

```bash
pip install epub-browser

# Open single book
epub-browser path/to/book1.epub

# Open multiple books
epub-browser book1.epub book2.epub book3.epub

# Open multiple books under the path
epub-browser *.epub

# Open multiple books under the current path
epub-browser .

# Do not start the server; only generate static website files, which can be directly deployed on any web server such as Apache.
epub-browser . --no-server

# Monitor all EPUB files in the directory specified by the user (or the directory where the EPUB file resides). When there are new additions or updates, automatically add them to the library.

epub-browser . --watch

# Specify the output directory of html files, or use tmp directory by default
epub-browser book1.epub book2.epub --output-dir /path/to/output

# Save the converted html files, will not clean the target tmp directory;
# Note: These files are for inspection purposes only and cannot be directly deployed to a web server. To enable direct deployment, please use the --no-server parameter.
epub-browser book1.epub --keep-files

# Do not open the browser automatically
epub-browser book1.epub book2.epub --no-browser

# Specify the server port
epub-browser book1.epub --port 8080
```

Then a browser will be opened to view the epub file.

### Desktop

#### Library home

![home](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-HWZoEf-3pN2vj.png)

* View All Books
* Switch Kindle Mode
* Search for Books
* Toggle Dark Mode

#### Page-turning mode

![page turning](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-VvMhcs-Y6EeNs.png)

* Previous Chapter
* Next Chapter
* Previous Page: Keyboard Left Arrow
* Next Page: Keyboard Right Arrow, Spacebar
* Jump to a Specific Page
* Set Pagination Page Height to Customize Content Display per Page

#### Book home

![book home](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-IFvr9L-oZR6vO.png)

* View Book Table of Contents

#### Reader

![reader](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-yWbMdb-NPTPJq.png)

![reader](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-17-w5l7ns-XvggSO.png)

* Breadcrumb
* Custom CSS
* Scroll Reading
* Page-Turning Reading
* View Book Table of Contents
* View Chapter Table of Contents
* Return to Library Homepage
* Font Adjustment
* Drag Elements

### Mobile

![mobile support](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-eQFGMw-4ONeC0.png)

### Kindle

![kindle support1](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-BpV0De-screenshot_2025_11_16T20_34_57+0800.png)

![kindle support2](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-wmsmxP-screenshot_2025_11_16T20_36_01+0800.png)

![kindle support3](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-VZqKQ4-screenshot_2025_11_16T23_26_59+0800.png)

![kindle support4](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-Ib1pM1-screenshot_2025_11_16T23_28_27+0800.png)

![kindle support5](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-16-Fta2oI-screenshot_2025_11_16T23_28_58+0800.png)

## Tips

* If there are errors or some mistakes in epub files, then you can use [calibre](https://calibre-ebook.com/) to convert to epub again.
* Tags can be managed by [calibre](https://calibre-ebook.com/). After adding tags, **you should click "Edit book" and just close the window to update the epub file** or the tags will not change in the browser.
* By default, the program listens on the address `0.0.0.0`. This means you can access the service via any of your local machine's addresses (such as a local area network (LAN) address like `192.168.1.233`), not just `localhost`.
* Just find calibre library and run `epub-browser .`, it will collect all books that managed by calibre.
* You can combine web reading with the web extension called [Circle Reader](https://circlereader.com/) to gain more elegant experience.Other extensions that are recommended are: [Diigo](https://www.diigo.com/): Read more effectively with annotation tools ...
