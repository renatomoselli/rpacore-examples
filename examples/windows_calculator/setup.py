from setuptools import setup

setup(
    name="windows-calculator",
    version="0.1.0",
    py_modules=[
        "calculator_calculator",
        "calculator_csv_loader",
        "calculator_test_runner",
    ],
    install_requires=[
        "pywinauto>=0.6.8",
    ],
    entry_points={
        'console_scripts': [
            'windows-calculator-test=calculator_test_runner:main',
        ],
    },
)
