# epub_browser/setup.py
import re
from pathlib import Path

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("epub_browser/version.py", "r", encoding="utf-8") as fh:
    version = re.search(r'^VERSION = ["\']([^"\']+)', fh.read(), re.MULTILINE).group(1)

vendor_package_data = [
    path.relative_to("epub_browser").as_posix()
    for path in sorted(Path("epub_browser/assets/vendor").rglob("*"))
    if path.is_file()
]

setup(
    name="epub-browser",  # 在PyPI上显示的项目名称
    version=version,
    author="dfface",   # 作者名
    author_email="dfface@sina.com",  # 作者邮箱
    keywords="epub reader ai reading ai assistant mind map annotations html export browser convert calibre-web calibre kindle web server local",
    description="A private EPUB reader with AI-native learning layers and a self-contained static-site generator.",  # 简短描述
    long_description=long_description,  # 详细描述，从README.md读取
    long_description_content_type="text/markdown",  # 详细描述格式
    url="https://github.com/dfface/epub-browser",  # 项目主页，如GitHub仓库地址
    project_urls={
        "Documentation": "https://github.com/dfface/epub-browser#ai-native-reading-server-only",
        "AI reading guide": "https://github.com/dfface/epub-browser/blob/main/docs/ai-native-reading.md",
        "Release notes": "https://github.com/dfface/epub-browser/tree/main/docs/releases",
    },
    packages=find_packages(exclude=("tests", "tests.*")),
    package_data={
        "epub_browser": [
            "assets/*",
            "assets/vendor/**/*",
            "prompt_templates/*.json",
            *vendor_package_data,
        ]
    },
    data_files=[("share/doc/epub-browser", ["THIRD_PARTY_NOTICES.md"])],
    classifiers=[  # 项目分类器，帮助用户找到你的项目
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    license="MIT",
    license_files=["License.txt", "THIRD_PARTY_NOTICES.md"],
    python_requires='>=3.9',  # Path and type syntax used by the v2 runtime
    install_requires=[  # 项目依赖的第三方包
        # 版本约束须守住 python_requires=">=3.9" 的承诺。下面两个包在 PyPI 上
        # 不声明 Requires-Python（或声明得比实际宽松），不设上限的话，
        # pip 在 Python 3.9 上可能装上要求更高解释器的未来版本。
        # 下限取有 cp39 wheel（或纯 Python）且满足本仓库所用 API 的版本。
        "tqdm>=4.62,<5.0",
        "watchdog>=3.0,<7.0",
        "starlette>=0.37,<1.0",
        "uvicorn[standard]>=0.30,<1.0",
        "argon2-cffi>=23.1,<26.0",
        "Authlib>=1.6.11,<1.7",
        "httpx>=0.27,<1.0",
        "mdict-utils==1.3.14",
        "pypdf>=6.0,<7.0",
        "pypdfium2>=5.0,<6.0",
        "Pillow>=10.0,<12.0",
        # Unified EPUB XML/XHTML parser: strict-first, recovery fallback.
        "lxml>=5.0,<7.0",
    ],
    entry_points={  # 创建命令行可执行脚本的关键！
        'console_scripts': [
            'epub-browser=epub_browser.main:main',  # 格式：'命令名=模块路径:函数名'
        ],
    },
)
