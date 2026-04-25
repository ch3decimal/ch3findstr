#!/usr/bin/python3
# ch3decimal - ch3findstr.py (https://github.com/ch3decimal/ch3findstr)
# Licensed with GNU GPLv3
import os
import sys
import argparse
import queue
import threading
import time
import re
import select
import logging

STATUS = True  # all workers run while this is true
DIR_QUEUE = queue.Queue()  # all found dirs end up here for workers
LOGS = queue.Queue()  # unused for now, because i've only ran it with 1 thread yet, but i guess there'll be problems with multithreaded logging
# probably will make a separate thread just to collect and post logs

# Argument parser, gotta make it a separate script or at least wrap it up better
parser = argparse.ArgumentParser(prog="ch3findstr.py",
	description="ch3coona's findstr script helps you find regex-matches or whole strings" +\
		" in all of the files inside a directory and it's children directories")
parser.add_argument("-p", "--path", help="Starting directory path", required=True)
_input_group = parser.add_argument_group("Input")
input_group = _input_group.add_mutually_exclusive_group(required=True)
input_group.add_argument("-r", "--regex", help="Expression to match inside files. One of: -r, -b or -s must be used", required=False)
input_group.add_argument("-s", "--string", help="Whole string to match inside files. One of: -r, -b or -s must be used", required=False)
input_group.add_argument("-b", "--binary", help="Look for whole binary strings inside files. Format it as hexadecimal, ex.: \"ab030343fa\". One of: -r, -b or -s must be used", required=False)
parser.add_argument("-v", "--verbose", help="Verbose runtime (include debug entries)", required=False, action="store_true", default=False)
parser.add_argument("-k", "--known-extensions", help="Only search inside files with given filename extensions. Pass them, separated with a comma. Ex.: -k \"txt,doc,csv,cfg\"", required=False)
parser.add_argument("--follow-links", help="Follow symlinks inside directories, false by default", action="store_true", required=False, default=False)
parser.add_argument("--thread-count", help="In case there are any links in the way that lead to different drives or if you search inside of an SSD, " +\
		"then multithreading might make script run faster. Not preferrable to use more than 1 due to I/O operations interferring with each another. Set to 1 by default", required=False, default=1, type=int)
parser.add_argument("--log-filename", help="Path to a log file. If not set, then only log to the console stdout", default=None, required=False)
parser.add_argument("--check-filename",
		help="If you use -s or -r, then enabling this argument makes the script look at the filename as " +\
			"well and match your string with it. \"name\" will flag the file as matching even if at least name fits. \"name_contents\" will only match file if both name check and contents check pass",
		required=False, default=None, nargs="?", choices=["name", "name_contents"], action="store", type=str)
parser.add_argument("--include-errors", help="Log about unreadable, unaccessible and locked files in the log as well", required=False, default=False, action="store_true")
args = parser.parse_args(sys.argv[1:])
print(args.check_filename)

if args.thread_count.__class__ != int:
	parser.error("--thread-count must be a positive integer")
	sys.exit(1)
if args.check_filename and args.binary:
	parser.error("You cannot use --check-filename while in -b/--binary mode. It only works with -r/--regex and -s/--string arguments")
	sys.exit(1)
if not args.string and not args.regex and not args.binary:
	parser.error("No data to match was passed. Use at least one of these: -r, -b, -s")
	sys.exit(1)
	
if not os.access(args.path, os.R_OK | os.F_OK) or not os.path.isdir(args.path):
	parser.error("--path argument is not accessible or is not a folder")
	sys.exit(1)
else:
	DIR_QUEUE.put(args.path)

# logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.DEBUG if args.verbose else logging.INFO, **({"filename": args.log_filename} if args.log_filename else {}))
logger_ = logging.getLogger('ch3findstr')
logger_level = logging.DEBUG if args.verbose else logging.INFO
logger_.setLevel(logger_level)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
if args.log_filename:
	file_handler = logging.FileHandler(args.log_filename)
	file_handler.setLevel(logging.DEBUG)
	file_handler.setFormatter(formatter)
	logger_.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setLevel(logger_level)
console_handler.setFormatter(formatter)
logger_.addHandler(console_handler)

# i thought it might be unnecessary to spam the logs with countless error messages in cade starting directory is high enough in the file tree
# so i added new argument to config that
# this is my way around for now
if not args.include_errors:
	class logger:  # i dont wanna rewrite logger for now, so this would solve the problem
		@staticmethod
		def info(*args, **kwargs):
			logger_.info(*args, **kwargs)
		
		@staticmethod
		def warning(*args, **kwargs):
			logger_.warning(*args, **kwargs)
			
		@staticmethod
		def debug(*args, **kwargs):
			logger_.debug(*args, **kwargs)
			
		@staticmethod
		def error(*args, **kwargs):
			pass
else:
	logger = logger_

regex_compiled = None
bin_data = None
known_extensions: tuple = None

if args.known_extensions:
	known_extensions = args.known_extensions.split(",")
	for i in range(len(known_extensions)):
		if known_extensions[i].startswith("."):
			continue
		known_extensions[i] = f".{known_extensions[i]}"
	for ext in known_extensions:
		if not re.match(r"^[a-zA-Z0-9._]+$", ext):
			parser.error("Irregular --known_extensions format. It must be a comma-split string with extensions listed or a singular one. Ex.: --known_extensions \"txt,csv,tar.gz\" or --known_extensions \"sqlite_db\"")
			sys.exit(1)
			
	if sys.platform.startswith("win"):
		known_extensions = tuple(map(str.lower, known_extensions))  # fat32 doenst care about the case of a letter
	else:
		known_extensions = tuple(known_extensions)
		
if args.regex:
	try:
		regex_compiled = re.compile(args.regex)
	except Exception as ex:
		parser.error(f"Could not compile regular expression: {str(ex)}")
		sys.exit(1)

if args.binary:
	try:
		bin_data = bytes.fromhex(args.binary)
	except ValueError:
		parser.error("Invalid binary input format. It must be passed as raw hexadecimal string without a prefix, ex.: deadbeef, 10affa01 and etc.")
		sys.exit(1)
		
thread_waitingfornewdirectories: dict[int, bool] = {}


def worker(tnum: int) -> None:
	global STATUS, DIR_QUEUE, thread_waitingfornewdirectories
	thread_waitingfornewdirectories[tnum] = False
	while STATUS:
		try:
			dir_path = DIR_QUEUE.get_nowait()
		except queue.Empty:
			if tuple(set(thread_waitingfornewdirectories.values())) == (True, ):  # every other thread did not find any new directories
				thread_waitingfornewdirectories[tnum] = True
				STATUS = False
				logger.info("No new directories to search in found, stopping threads")
				break
			thread_waitingfornewdirectories[tnum] = True
			time.sleep(0.1)
			continue
			
		if not os.access(dir_path, os.R_OK | os.F_OK):
			logger.warning(f"Directory \"{dir_path}\" is not accessible, skipping it")
			continue
		
		contents = os.listdir(dir_path)
		fls = list()
		
		for i in contents:
			cpath = os.path.join(dir_path, i)
			
			if sys.platform.startswith("win") and os.path.isreserved(cpath):
				continue
			if not args.follow_links and os.path.islink(cpath):
				continue
			if not os.access(cpath, os.F_OK | os.R_OK):
				logger.warning(f"File at \"{cpath}\" is unaccessible or unreadable, skipping it")
				continue
				
			rcpath = cpath[::] if not os.path.islink(cpath) else os.path.realpath(cpath)
			
			if os.path.isfile(cpath):
				if known_extensions:
					l = False
					for known_extension in known_extensions:
						if cpath.lower().endswith(known_extension):
							l = True
					if not l:
						continue
				fls.append(rcpath)
			elif os.path.isdir(cpath):
				DIR_QUEUE.put(rcpath)
			else:
				logger.warning(f"Unknown file at \"{rcpath}\", skipping it")
				continue
		
		for fl in fls:
			fl_justname = os.path.split(fl)[-1]
			if args.check_filename:
				match = None
				if args.regex:
					match = regex_compiled.search(fl_justname)
					if match:
						logger.info(f"Found regex match in file's name: \"{fl}\"")
				elif args.string:
					match = fl_justname.find(args.string)
					if match:
						logger.info(f"Found whole string match in file's name: \"{fl}\"")
					
				if match and args.check_filename == "name":
					continue
					
			
			try:
				logger.debug(f"Processing {fl}")
				with open(fl, "rb" if args.binary else "r", **({encoding: "utf=8"} if args.string else {})) as fhandler_:
					try:
						d = fhandler_.read()
					except (UnicodeDecodeError, IOError, OSError) as ex:
						logger.error(f"Could not read file \"{fl}\". Skipping...")  # If -s mode is on, then probably couldn't decode. If -b, then file is locked or unreadable
						fhandler_.close()
						continue
			except (OSError, IOError) as ex:
				logger.error(f"Could not read file: \"{fl}\", skipping it")
				continue
			
			if not d:
				continue
				
			if d.__class__ == bytes:
				match = d.find(bin_data)
				if match < 0:
					continue
				logger.info(f"Found binary match at index {match} in file: \"{fl}\"")
			elif d.__class__ == str:
				if args.regex:
					match = regex_compiled.search(d)
					
					if not match:
						continue
					
					logger.info(f"Found regex match at index {match.span()[0]} in file: \"{fl}\"")
				else:
					match = d.find(args.string)
					
					if match < 0:
						continue
						
					logger.info(f"Found whole string match at index {match} in file: \"{fl}\"")
			else:
				pass  # idk what else it might be lol so just pass
	print(f"Thread #{tnum} has stopped working")

threads = list()
for _tnum in range(args.thread_count):
	threads.append(threading.Thread(target=worker, args=(_tnum,)))
	threads[-1].start()
print("Press enter or Ctrl-C to stop and wait for all the threads to stop")
try:
	while STATUS:
		with open(0) as stdin:
			try:
				rl = select.select([stdin,], [], [], timeout=0.1)
				if rl:
					if rl.read():
						STATUS = False
						print("Stopping all threads...")
						stdin.close()
						break
			except:
				time.sleep(0.1)
				continue
except BaseException as ex:  # systemexit or keyboardinterrupt called
	pass
STATUS = False
for t in threads:
	t.join(timeout=4)
print("Main loop stopped, wait for other threads to finish their work")