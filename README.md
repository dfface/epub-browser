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
* Mobile devices.

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

![epub library home](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-GEpNPv-8bIkJB.png)

![epub book home](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-zayg9n-moqApI.png)

![epub chapter](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-Fj7aTM-v2Li0z.png)

![mobile support](https://fastly.jsdelivr.net/gh/dfface/img0@master/2025/11-13-tFUcoE-CKAxJE.png)

## Tips

If there are errors or some mistakes in epub files, then you can use [calibre](https://calibre-ebook.com/) to convert to epub again.

Tags can be managed by [calibre](https://calibre-ebook.com/).

Just find calibre library and run `epub-browser .`, it will collect all books that managed by calibre.

You can combine web reading with the web extension called [Circle Reader](https://circlereader.com/) to gain more elegant experience.

Other extensions that are recommended are:

1. [Diigo](https://www.diigo.com/): Read more effectively with annotation tools.
2. ...
