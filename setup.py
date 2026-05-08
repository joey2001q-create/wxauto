"""
企业微信自动化工具 - setup.py
"""
from setuptools import setup, find_packages

# 尝试读取 README.md，如果不存在则使用默认描述
try:
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()
except FileNotFoundError:
    long_description = "企业微信自动化工具 - 基于OCR+SendInput"

setup(
    name="wxauto",
    version="1.2.0",
    author="joey2001q",
    author_email="",
    description="企业微信自动化工具 - 基于OCR+SendInput",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/joey2001q-create/wxauto",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Automation",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "mss>=9.0.0",
        "rapidocr-onnxruntime>=1.2.0",
        "opencv-python>=4.8.0",
        "numpy>=1.24.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=22.0.0",
        ],
    },
)
