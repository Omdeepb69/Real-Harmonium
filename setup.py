from setuptools import setup, find_packages

setup(
    name="realharmonium",
    version="1.0.0",
    description="A tilt-controlled harmonium instrument for the Linux terminal",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="realharmonium contributors",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "numpy>=1.21",
        "pygame>=2.0",
    ],
    extras_require={
        "evdev": ["evdev>=1.4"],
    },
    entry_points={
        "console_scripts": [
            "realhm = realharmonium.__main__:main",
        ],
    },
    classifiers=[
        "Environment :: Console :: Curses",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Topic :: Multimedia :: Sound/Audio",
    ],
)
