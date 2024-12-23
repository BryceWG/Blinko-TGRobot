from setuptools import setup, find_packages

setup(
    name="blinko-tg-robot",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-telegram-bot",
        "aiohttp",
        "sqlalchemy",
        "httpx",
    ],
) 