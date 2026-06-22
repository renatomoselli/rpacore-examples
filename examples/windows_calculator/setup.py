from __future__ import annotations

from setuptools import setup

setup(
    name="windows-calculator",
    version="0.2.0",
    py_modules=[
        "calculator_calculator",
        "calculator_csv_loader",
        "calculator_test_runner",
        "calculator_utils",
        "main",
    ],
    packages=["skills"],
    install_requires=[
        "rpacore",
        "pywinauto>=0.6.8",
    ],
    entry_points={
        "console_scripts": [
            "windows-calculator=main:main",
        ],
    },
)
