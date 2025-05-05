from setuptools import setup, Extension, find_packages
import subprocess

def pkg_config(library: str, flag: str) -> list[str]:
    try:
        output = subprocess.check_output(["pkg-config", flag, library])
        return output.decode().split()
    except subprocess.CalledProcessError:
        return []

def get_include_dirs(library: str) -> list[str]:
    # Get flags like "-I/usr/include/ffmpeg" and strip off the "-I"
    flags = pkg_config(library, '--cflags-only-I')
    return [flag[2:] for flag in flags if flag.startswith('-I')]

def get_library_dirs(library: str) -> list[str]:
    # Get flags like "-L/usr/lib" and strip off the "-L"
    flags = pkg_config(library, '--libs-only-L')
    return [flag[2:] for flag in flags if flag.startswith('-L')]

def get_libraries(library: str) -> list[str]:
    # Get flags like "-lavformat" and strip off the "-l"
    flags = pkg_config(library, '--libs-only-l')
    return [flag[2:] for flag in flags if flag.startswith('-l')]

# Get the FFmpeg configuration from pkg-config for libavformat, libavcodec, and libavutil.
include_dirs = (
    get_include_dirs("libavformat")# +
    #get_include_dirs("libavcodec") +
    #get_include_dirs("libavutil")
)

library_dirs = (
    get_library_dirs("libavformat")# +
    #get_library_dirs("libavcodec") +
    #get_library_dirs("libavutil")
)

libraries = (
    get_libraries("libavformat")# +
    #get_libraries("libavcodec") +
    #get_libraries("libavutil")
)

# Define the extension module.
module = Extension(
    'av_info._ffmpeg',
    sources=['src/ffmpeg.cpp'],  # your C++ source file
    language='c++',
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    libraries=libraries,
)

_ = setup(
    name="av_info",
    version="1.0",
    description="A Python extension module for FFmpeg interfacing built with setuptools.",
    ext_modules=[module],
    packages=find_packages(),
)
