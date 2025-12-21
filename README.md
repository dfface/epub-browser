# epub-browser

![GitHub Repo stars](https://img.shields.io/github/stars/dfface/epub-browser)
[![python](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![pypi](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![wheel](https://img.shields.io/pypi/wheel/epub-browser)](https://pypi.org/project/epub-browser/)
[![license](https://img.shields.io/github/license/dfface/epub-browser)](https://pypi.org/project/epub-browser/)
![PyPI - Downloads](https://img.shields.io/pypi/dd/epub-browser)

A simple and modern web E-book reader, which allows you to read e-books within a browser.

Try it online: [https://epub-browser.vercel.app](https://epub-browser.vercel.app)

It now supports the following features:

- **Basic library management**: Search by title, author or tag.

- Dark mode

- **Page navigation**: Keyboard controls supported (Left Arrow, Right Arrow and Spacebar for page turning/scrolling).

- **Kindle Mode**: Enhanced style optimizations; allows page turning by tapping either side of the screen.

- Reading progress bar

- **Chapter-wise table of contents** (disabled in Page Turning Mode).

- Font size and font family adjustment

- Image zoom functionality

- **Mobile device compatibility**: Especially for Kindle users—remember to tap *Not Kindle* on the homepage header to enable Kindle Mode for an optimized experience.

- **Code highlighting** (disabled in Kindle Mode).

- **Reading position retention**: Restores your last-read chapter (supported on all devices including Kindle) and your last-read location (supported on all devices *except* Kindle).

- **Custom CSS**: Tailor the reading experience with custom styles, e.g.

    ```css
    #eb-content { margin: 50px; }
    #eb-content p { font-size: 2rem; }
    ```

  *Note: All core content is nested under the element with the `#eb-content` selector.*

- **Direct deployment** on any web server (e.g. Apache): Use the `--no-server` parameter.

- Multithreading support

- **Drag-and-drop sorting**: Main interface elements are draggable.

- **Calibre metadata integration**: Displays tags (`dc:subject`) and comments (`dc:description`) edited in Calibre. *Note: After editing metadata in Calibre, use the "Edit book" function to save your changes.*

- **Watchdog utility**: Monitors the user-specified directory (or the directory containing EPUB files) with `--watch` parameter. Automatically adds newly added or updated EPUB files to the library.


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

For more usage information, please use the `--help` parameter.

```bash
➜ epub-browser --help                                                                                        
usage: epub-browser [-h] [--port PORT] [--no-browser] [--output-dir OUTPUT_DIR] [--keep-files] [--log] [--no-server] [--watch]
                    filename [filename ...]

EPUB to Web Converter - Multi-book Support

positional arguments:
  filename              EPUB file path(s)

options:
  -h, --help            show this help message and exit
  --port, -p PORT       Web server port (default: 8000)
  --no-browser          Do not automatically open browser
  --output-dir, -o OUTPUT_DIR
                        Output directory for converted books
  --keep-files          Keep converted files after server stops. To enable direct deployment, please use the --no-server parameter.
  --log                 Enable log messages
  --no-server           Do not start a server, just generate files which can be directly deployed on any web server such as Apache.
  --watch, -w           Monitor all EPUB files in the directory specified by the user (or the directory where the EPUB file resides).
                        When there are new additions or updates, automatically add them to the library.
```
## Startup

How do I set it to start automatically on boot?

### macOS

1. add a file `epub-browser.plist` in `~/Library/LaunchAgents`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>Label</key>
        <string>Epub-Browser</string>
        <key>ProgramArguments</key>
        <array>
            <string>/path/to/.venv/bin/epub-browser</string>
            <string>--output-dir</string>
            <string>/path/to/workdir</string>
            <string>--watch</string>
            <string>--no-browser</string>
            <string>--keep-files</string>
            <string>/path/to/Calibre Library</string>
        </array>
        <key>RunAtLoad</key>
        <true/>
        <key>WorkingDirectory</key>
        <string>/path/to/workdir</string>
        <key>StandardOutPath</key>
        <string>/path/to/workdir/run.log</string>
        <key>StandardErrorPath</key>
        <string>/path/to/workdir/err.log</string>
    </dict>
</plist>
```

> run `which epub-browser` to get the full path of `epub-browser`

1. run the command to make effective:

```bash
launchctl load -w ~/Library/LaunchAgents/epub-browser.plist
# launchctl unload -w ~/Library/LaunchAgents/epub-browser.plist
launchctl start epub-browser
```

### Linux

wait someone to add or ask ChatGPT.

## Screenshots

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
