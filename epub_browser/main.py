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
from watchdog.observers import Observer

from .server import EPUBServer
from .library import EPUBLibrary
from .watch import EPUBWatcher

def main():
    parser = argparse.ArgumentParser(description='EPUB to Web Converter - Multi-book Support')
    parser.add_argument('filename', nargs='+', help='EPUB file path(s)')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Web server port (default: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='Do not automatically open browser')
    parser.add_argument('--output-dir', '-o', help='Output directory for converted books')
    parser.add_argument('--keep-files', action='store_true', help='Keep converted files after server stops. To enable direct deployment, please use the --no-server parameter.')
    parser.add_argument('--log', action='store_true', help='Enable log messages')
    parser.add_argument('--no-server', action='store_true', help='Do not start a server, just generate files which can be directly deployed on any web server such as Apache.')
    parser.add_argument('--watch', '-w', action='store_true', help="Monitor all EPUB files in the directory specified by the user (or the directory where the EPUB file resides). When there are new additions or updates, automatically add them to the library.")
    
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
        result, book_info = library.add_book(filename)
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
    
    # 创建 library home
    library.create_library_home()
    # 添加静态资源
    library.add_assets()
    # 重新组织文件位置
    library.reorganize_files()

    # 仅生成文件
    if args.no_server:
        print(f"Files generated in: {library.base_directory}")
        return

    # 是否需要监控
    watcher = EPUBWatcher(args.filename, library)
    def watch_changes():
        try:
            watcher.watch()
        except Exception as e:
            print(f"Error occurred: {e}")  

    if args.watch:
        watchdog_thread = threading.Thread(
            target=watch_changes, name="WatchdogThread"
        )
        watchdog_thread.daemon = True # 设置为守护线程（可选，这样主程序退出时线程会自动结束）
        watchdog_thread.start()
         
    # 创建服务器
    server_instance = EPUBServer(library, args.log)
    def start_serve():
        try:
            server_instance.start_server(
                port=args.port, 
                no_browser=args.no_browser,
            )
        except Exception as e:
            print(f"Error occurred: {e}")   
    
    server_thread = threading.Thread(
        target=start_serve, name="ServerThread"
    )
    server_thread.daemon = True
    server_thread.start()

    try:
        # 主线程等待所有子线程完成
        while True:
            # 检查线程是否存活
            if not server_thread.is_alive():
                print("Server down")
                break
            if args.watch and watchdog_thread:
                if not watchdog_thread.is_alive():
                    print("Watchdog down")
                    break
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        if not args.keep_files:
            library.cleanup()


if __name__ == '__main__':
    main()