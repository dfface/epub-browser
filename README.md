# epub-browser

Read epub file in the browser(Chrome/Edge/Safari...).

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

# Open multiple books under the path
epub-browser /path/to/epub

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

![epub on web](https://github.com/dfface/epub-browser/raw/main/assets/test1.png)

## Tips

If there are errors or some mistakes in epub files, then you can use [calibre](https://calibre-ebook.com/) to convert to epub again.

You can combine web reading with the web extension called [Circle Reader](https://circlereader.com/) to gain more elegant experience.

Other extensions that are recommended are:

1. [Diigo](https://www.diigo.com/): Read more effectively with annotation tools.
2. ...
