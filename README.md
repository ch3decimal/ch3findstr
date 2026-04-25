# ch3findstr
This script looks for whole string/binary/regex matches inside any files that it finds
inside given directory and any of its subdirectories.
It has many options to configurate the search process and may work multithreaded.

Note: i have **NOT** tested it on any linux-based OS and any fs other than fat32 yet. I've
implemented some precautions for that manner, but at this point of time I am not sure if this 
script will work fine on linux.

## Usage
```
usage: ch3findstr.py [-h] -p PATH (-r REGEX | -s STRING | -b BINARY) [-v]
                         [-k KNOWN_EXTENSIONS] [--follow-links]
                         [--thread-count THREAD_COUNT]
                         [--log-filename LOG_FILENAME]
                         [--check-filename [{name,name_contents}]]

ch3coona's findstr script helps you find regex-matches or whole strings in all
of the files inside a directory and it's children directories

options:
  -h, --help            show this help message and exit
  -p, --path PATH       Starting directory path
  -v, --verbose         Verbose runtime (include debug entries)
  -k, --known-extensions KNOWN_EXTENSIONS
                        Only search inside files with given filename
                        extensions. Pass them, separated with a comma. Ex.: -k
                        "txt,doc,csv,cfg"
  --follow-links        Follow symlinks inside directories, false by default
  --thread-count THREAD_COUNT
                        In case there are any links in the way that lead to
                        different drives or if you search inside of an SSD,
                        then multithreading might make script run faster. Not
                        preferrable to use more than 1 due to I/O operations
                        interferring with each another. Set to 1 by default
  --log-filename LOG_FILENAME
                        Path to a log file. If not set, then only log to the
                        console stdout
  --check-filename [{name,name_contents}]
                        If you use -s or -r, then enabling this argument makes
                        the script look at the filename as well and match your
                        string with it. "name" will flag the file as matching
                        even if at least name fits. "name_contents" will only
                        match file if both name check and contents check pass

Input:
  -r, --regex REGEX     Expression to match inside files. One of: -r, -b or -s
                        must be used
  -s, --string STRING   Whole string to match inside files. One of: -r, -b or
                        -s must be used
  -b, --binary BINARY   Look for whole binary strings inside files. Format it
                        as hexadecimal, ex.: "ab030343fa". One of: -r, -b or
                        -s must be used
```
## TODO
 - [ ] Test on ext4 fs
 - [ ] Add setup to install as a python module (python -m ...)
 - [ ] Test on linux
 - [ ] Put argument parser in separate module so it'd look cleaner
