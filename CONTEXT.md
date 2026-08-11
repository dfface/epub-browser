# EPUB Browser

EPUB Browser turns EPUB files into a locally served reading library. Its reading experience must remain responsive on long books and large local libraries.

## Language

**Reading window**:
The bounded set of fully rendered chapters around the reader's current location in continuous scroll mode. Chapters outside the reading window are represented only by their accumulated space until they are needed again.
_Avoid_: loaded chapter list, infinite scroll cache

**Book cover**:
The representative image of a book shown in the library or bookshelf.
_Avoid_: thumbnail, preview image
