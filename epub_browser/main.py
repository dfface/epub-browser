#!/usr/bin/env python3
"""
EPUB to Web Converter
将EPUB文件转换为可在浏览器中阅读的网页格式
支持多本书籍同时转换
"""

import os
import sys
import argparse

from tqdm import tqdm
from server import EPUBServer
from library import EPUBLibrary

def main():
    parser = argparse.ArgumentParser(description='EPUB to Web Converter - Multi-book Support')
    parser.add_argument('filename', nargs='+', help='EPUB file path(s)')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Web server port (default: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='Do not automatically open browser')
    parser.add_argument('--output-dir', '-o', help='Output directory for converted books')
    parser.add_argument('--keep-files', action='store_true', help='Keep converted files after server stops')
    
    args = parser.parse_args()
    
    # 检查文件是否存在
    for filename in args.filename:
        if not os.path.exists(filename):
            print(f"Error: File '{filename}' does not exist")
            sys.exit(1)
    
    # 创建图书馆
    library = EPUBLibrary(args.output_dir)
    server_instance = EPUBServer(library)
    
    try:
        # 添加所有书籍
        success_count = 0
        # 收集真实的 epub file
        real_epub_files = []
        for filename in args.filename:
            files = library.epub_file_discover(filename)
            real_epub_files.extend(files)
        # 构建图书馆
        for filename in tqdm(real_epub_files):
            if library.add_book(filename):
                success_count += 1
        if success_count == 0:
            print("No books were successfully processed")
            sys.exit(1)

        library.create_library_home()
        # print(f"Successfully processed {success_count} out of {len(args.filename)} books")
        
        # 启动服务器
        server_instance.start_server(args.port, args.no_browser)
        
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        server_instance.stop_server()
        if not args.keep_files:
            server_instance.cleanup()

if __name__ == '__main__':
    main()