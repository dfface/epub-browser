# epub_browser/setup.py
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="epub-browser",  # 在PyPI上显示的项目名称
    version="0.6.2",      # 初始版本号
    author="dfface",   # 作者名
    author_email="dfface@sina.com",  # 作者邮箱
    description="A tool to open epub files and serve them via a local web server for reading in a browser.",  # 简短描述
    long_description=long_description,  # 详细描述，从README.md读取
    long_description_content_type="text/markdown",  # 详细描述格式
    url="https://github.com/dfface/epub-browser",  # 项目主页，如GitHub仓库地址
    packages=find_packages(),  # 自动发现包
    classifiers=[  # 项目分类器，帮助用户找到你的项目
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  # 请根据实际情况选择许可证
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',  # 指定Python版本要求
    install_requires=[  # 项目依赖的第三方包
        # 例如 "requests", 如果您的工具没有额外依赖，可以留空列表 []
    ],
    entry_points={  # 创建命令行可执行脚本的关键！
        'console_scripts': [
            'epub-browser=epub_browser.main:main',  # 格式：'命令名=模块路径:函数名'
        ],
    },
)