# epub-browser

![GitHub Repo stars](https://img.shields.io/github/stars/dfface/epub-browser)
[![python](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![pypi](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![wheel](https://img.shields.io/pypi/wheel/epub-browser)](https://pypi.org/project/epub-browser/)
[![license](https://img.shields.io/github/license/dfface/epub-browser)](https://pypi.org/project/epub-browser/)
![PyPI - Downloads](https://img.shields.io/pypi/dd/epub-browser)

A simple and modern web E-book reader, which allows you to read e-books within a browser.

It now supports:

* Simple library management: searching by title, author or tag.
* Dark mode.
* Reading progress bar.
* Table of contents in each chapter.
* Font size adjustment.
* Image zoom.
* Mobile devices: especially kindle.
* Code highlight.
* Remember your last reading chapter.
* Custom CSS: you can write your own CSS style to improve your reading experience, such as `.content{margin: 50px;}.content p{ font-size: 2rem; }`(All the main content is under the element with the class `content`).

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

# Specify the output directory of html files, or use tmp directory by default
epub-browser book1.epub book2.epub --output-dir /path/to/output

# Save the converted html files, will not clean the target tmp directory
epub-browser book1.epub --keep-files

# Do not open the browser automatically
epub-browser book1.epub book2.epub --no-browser

# Specify the server port
epub-browser book1.epub --port 8080
```

Then a browser will be opened to view the epub file.

### Desktop

![epub library home](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-7Zojnb-JH0qhY.png)

![epub book home](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-DMXr4g-DG7fei.png)

![epub chapter example1](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-oQzhk1-Z8g6hg.png)

![epub chapter example2](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-B3rpC0-BSaN6R.png)

### Mobile

![mobile support](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-tFUcoE-CKAxJE.png)

### Kindle

![kindle support1](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-14-wXATw7-screenshot_2025_11_14T00_05_50+0800.png)

![kindle support2](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-14-JsykYo-screenshot_2025_11_14T00_06_18+0800.png)

![kindle support3](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-14-S3hqb9-screenshot_2025_11_14T00_06_51+0800.png)

![kindle support4](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-14-l0maxe-screenshot_2025_11_14T00_07_11+0800.png)

## Tips

* If there are errors or some mistakes in epub files, then you can use [calibre](https://calibre-ebook.com/) to convert to epub again.
* Tags can be managed by [calibre](https://calibre-ebook.com/). After adding tags, **you should click "Edit book" and just close the window to update the epub file** or the tags will not change in the browser.
* By default, the program listens on the address `0.0.0.0`. This means you can access the service via any of your local machine's addresses (such as a local area network (LAN) address like `192.168.1.233`), not just `localhost`.
* Just find calibre library and run `epub-browser .`, it will collect all books that managed by calibre.
* You can combine web reading with the web extension called [Circle Reader](https://circlereader.com/) to gain more elegant experience.Other extensions that are recommended are: [Diigo](https://www.diigo.com/): Read more effectively with annotation tools ...
