#!/usr/bin/env python3
"""
EPUB to Web Converter
将EPUB文件转换为可在浏览器中阅读的网页格式
支持多本书籍同时转换
"""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import argparse
from tqdm import tqdm

from .server import EPUBServer
from .library import EPUBLibrary

def main():
    parser = argparse.ArgumentParser(description='EPUB to Web Converter - Multi-book Support')
    parser.add_argument('filename', nargs='+', help='EPUB file path(s)')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Web server port (default: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='Do not automatically open browser')
    parser.add_argument('--output-dir', '-o', help='Output directory for converted books')
    parser.add_argument('--keep-files', action='store_true', help='Keep converted files after server stops. To enable direct deployment, please use the --no-server parameter.')
    parser.add_argument('--log', action='store_true', help='Enable log messages')
    parser.add_argument('--no-server', action='store_true', help='Do not start a server, just generate files which can be directly deployed on any web server such as Apache.')
    
    args = parser.parse_args()
    
    # 检查文件是否存在
    for filename in args.filename:
        if not os.path.exists(filename):
            print(f"Error: File '{filename}' does not exist")
            sys.exit(1)
    
    # 创建图书馆
    library = EPUBLibrary(args.output_dir)

    # 收集所有的 epub file，可能传递了路径需要下钻
    real_epub_files = []
    for filename in args.filename:
        cur_files = library.epub_file_discover(filename)
        real_epub_files.extend(cur_files)

    # 添加所有书籍
    # 线程安全相关变量
    success_count = 0
    count_lock = threading.Lock()  # 保证计数器操作的原子性
    progress_lock = threading.Lock()  # 保证 tqdm 进度条显示正常

    # 创建进度条（总任务数为文件数量）
    pbar = tqdm(total=len(real_epub_files), desc="Processing books")

    # 多线程处理函数：添加单本书籍
    def add_book_thread(filename, pbar):
        nonlocal success_count
        # 调用 add_book 添加书籍（假设该方法线程安全，若不安全需额外加锁）
        result = library.add_book(filename)
        # 线程安全地更新计数器和进度条
        with count_lock:
            if result:
                success_count += 1
        with progress_lock:
            pbar.update(1)  # 每次处理完一本书，更新进度条

    # 创建并启动线程
    threads = []
    with ThreadPoolExecutor(max_workers=10) as executor:  # 限制最大10个并发线程
        for filename in real_epub_files:
            thread = threading.Thread(
                target=add_book_thread,
                args=(filename, pbar)
            )
            threads.append(thread)
            thread.start()

    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    # 关闭进度条
    pbar.close()

    if success_count == 0:
        print("No books were successfully processed")
        sys.exit(1)

    library.create_library_home()

    # 仅生成文件
    if args.no_server:
        # 重新组织文件格式
        library.reorganize_files()
        print(f"Files generated in: {library.base_directory}")
        return
    
    # 创建服务器
    server_instance = EPUBServer(library, args.log)
    try:
        server_instance.start_server(
            port=args.port, 
            no_browser=args.no_browser,
        )
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        server_instance.stop_server()
        if not args.keep_files:
            library.cleanup()


if __name__ == '__main__':
    main()