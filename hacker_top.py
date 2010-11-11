#!/usr/bin/python
#
# Peteris Krumins (peter@catonmat.net)
# http://www.catonmat.net  --  good coders code, great reuse
#
# Released under GNU GPL.
#
# A Hacker News `top' like program.
# http://www.catonmat.net/blog/follow-hacker-news-from-the-console
#

""" Hacker Top: Follow your hacker news from the console """

import os
import re
import sys
import time
import Queue
import fcntl
import getopt
import curses
import signal
import struct
import termios
import datetime
import threading
import webbrowser
from htmlentitydefs import entitydefs
from pyhackerstories import get_stories, RedesignError, SeriousError, stories_per_page

version = "1.0"

# Default refresh interval.
# Example values:
# 20 - 20 seconds (same as 20s), 1m - 1 minute,  20m - 20 minutes
default_interval = '3m'

# Is the terminal capable of outputting utf8? (this is the default value)
# Change with -u|--utf command option
default_can_utf8 = False

# Monitor new stories?
default_new = False

# Terminal got resized?
RESIZE_EVENT = False

# Queue used by Retriever to send stories and exceptions
retr_queue_out = Queue.Queue()

# Queue used to notify Retriever about quitting or other events
retr_queue_in = Queue.Queue()

class ProgError(Exception):
    """ This prog's exception class thrown from curse mode """

    def __init__(self, msg=None, callback=None):
        """ Sets error message and callback to be called after we quit
        the curses mode """
        self.msg = msg
        self.callback = callback
        Exception.__init__(self, msg)

class ArgError(Exception):
    """ Invalid command line argument exception """
    pass

class Retriever(threading.Thread):
    """ Thread which runs "data retriever" """
    
    def __init__(self, args):
        self.running = False
        self.pages = 1
        self.old_pages = 1
        self.new = args['new']
        self.update_secs = Interval(args['interval']).to_secs()
        threading.Thread.__init__(self)
    
    def run(self):
        self.running = True
        while self.running:
            try:
                retr_queue_out.put(StartGettingData());
                stories = get_stories(self.pages, self.new)
                retr_queue_out.put(FinishedGettingData())
                retr_queue_out.put(Story(stories))
                if self.old_pages != self.pages:
                    self.old_pages = self.pages
                    retr_queue_out.put(ChangedPages())
            except RedesignError, e:
                retr_queue_out.put(FinishedGettingData())
                retr_queue_out.put(DisplayError("Hacker News might have redesigned:", str(e)))
                return
            except SeriousError, e:
                retr_queue_out.put(FinishedGettingData())
                retr_queue_out.put(DisplayError("Serious error:", str(e)))
                return

            try:
                # see if the main thread notified us to do something
                action = retr_queue_in.get(True, self.update_secs)
                action.do(self)
            except Queue.Empty:
                pass

class RetrieverNotification(object):
    """ Base class for Retriever Notifications """
    pass

class DisplayError(RetrieverNotification):
    """ Display a retriever error """
    def __init__(self, *msgs):
        self.msgs = msgs;

    def do(self, interface):
        interface.body_win.erase()
        error_msg = "Error!"
        offset = len(self.msgs)/2
        interface.body_win.addstr(interface.body_max_y/2-offset-1, interface.body_max_x/2 - len(error_msg)/2,
            error_msg, curses.color_pair(5))
        for idx, msg in enumerate(self.msgs):
            interface.body_win.addstr(interface.body_max_y/2-offset+idx, interface.body_max_x/2 - len(msg)/2,
                msg, curses.color_pair(3))

class StartGettingData(RetrieverNotification):
    """ Notify user that retriever went after data """
    def do(self, interface):
        interface.head_win.addstr(1, 4, "Updating...", curses.color_pair(3))
        interface.head_win.refresh()

class FinishedGettingData(RetrieverNotification):
    """ Notify user that retriever finished going after data """
    def do(self, interface):
        interface.head_win.addstr(1, 4, "           ", curses.color_pair(3))
        interface.head_win.refresh()

class Story(RetrieverNotification):
    """ Got Hacker News stories """
    def __init__(self, stories):
        self.stories = stories

    def do(self, interface):
        interface.stories = self.stories
        interface.display.display(self.stories)

class RetrieverQuit(RetrieverNotification):
    """ Notify retriever to quit """
    def do(self, retriever):
        retriever.running = False

class ForceUpdate(RetrieverNotification):
    """ Notify retriever to do an update right now """
    def do(self, retriever):
        pass

class ChangePages(RetrieverNotification):
    """ Notify retriever to retrieve more pages """
    def __init__(self, pages):
        self.pages = pages

    def do(self, retriever):
        retriever.pages = self.pages

class ChangedPages(RetrieverNotification):
    """ Notify the interface that retriever changed a page """
    def do(self, interface):
        interface.pages_changed = True

class DisplayMode(object):
    """ Base class for display modes """
    def __init__(self, interface):
        self.interface = interface

    def display(self, stories):
        self.interface.body_win.erase()
        self.interface.body_win.move(0, 0)

        if not stories:
            no_story = "No stories found on Hacker News!"
            self.interface.body_win.addstr(self.interface.body_max_y/2,
                self.interface.body_max_x/2 - len(no_story)/2, no_story, curses.color_pair(3))
            return

        max_display = self.max_display()
        for idx in range(max_display - 1):
            try:
                story = stories[idx + self.interface.start_pos]
                story.title = html_unescape(story.title)
                if not interface.can_utf8:
                    story.title = story.title.decode('utf8').encode('ascii', 'replace')
                self.do_display(story)
            except IndexError:
                break

        self.interface.body_win.refresh()

    def max_display(self):
        """ Returns max number of stories that can be displayed on screen """
        return self.interface.body_max_y / self.lines_per_story()

class BasicDisplay(DisplayMode):
    """ Base class for basic display modes """

    def do_display(self, story):
        title_line = self.format_title(story)
        self.display_title(title_line)
        self.display_info(story)

    def display_title(self, title_line):
        self.interface.body_win.addstr(title_line[:4])
        self.interface.body_win.addstr(title_line[4:] + "\n", curses.color_pair(1))

    def format_title(self, story):
        title_line = "%2d. %s" % (story.position, story.title)
        if len(title_line) > self.interface.body_max_x:
            title_line = title_line[:self.interface.body_max_x-1]
        return title_line

    def display_info(self, story):
        when = nice_date(datetime.datetime.fromtimestamp(story.unix_time), datetime.datetime.now())
        self.interface.body_win.addstr("    ")
        self.interface.body_win.addstr("points: ")
        if story.score == 1:
            points = "1"
        elif story.score > 1:
            points = "%d" % story.score
        else:
            points = "-"
        self.interface.body_win.addstr(points.ljust(5), curses.color_pair(2) | curses.A_BOLD)

        self.interface.body_win.addstr("comments: ")
        if story.comments == 1:
            comments = "1"
        elif story.comments >= 0:
            comments = "%d" % story.comments
        else:
            comments = '-'
        self.interface.body_win.addstr(comments.ljust(5), curses.color_pair(2) | curses.A_BOLD)
            
        self.interface.body_win.addstr("posted: ")
        self.interface.body_win.addstr(when.ljust(17), curses.color_pair(2) | curses.A_BOLD)

        self.interface.body_win.addstr("user: ") # this takes 63 chars on the screen
        if len(story.user) > 79 - 63:
            self.interface.body_win.addstr(story.user[:79-63], curses.color_pair(2) | curses.A_BOLD)
        else:
            self.interface.body_win.addstr(story.user, curses.color_pair(2) | curses.A_BOLD)

        self.interface.body_win.addstr("\n")

class SpacedDetailed(BasicDisplay):
    """
    Spaced Detailed display mode.
    Example:
    --------
     1. Story title
        points: 37   comments: 23   posted: 3 hours ago      user: username

    --------
    """
    def lines_per_story(self):
        """ Returns number of lines a story takes """
        return 3

    def display_info(self, story):
        super(SpacedDetailed, self).display_info(story)
        self.interface.body_win.addstr("\n")

class CompressedDetailed(BasicDisplay):
    """
    Compressed Detailed display mode.
    Example:
    --------
     1. Story title
        points: 37   comments: 23   posted: 3 hours ago      user: username
    --------
    """
    def lines_per_story(self):
        return 2

class Compact(BasicDisplay):
    """
    Compact display mode.
    Example:
    --------
     1. Story title
    -------- 
    """
    def lines_per_story(self):
        return 1

    def display_info(self, story):
        pass

class CompressedFull(BasicDisplay):
    """
    Compressed Full display mode.
    Example:
    --------
     1. Story title
        http://www.example.com
        points: 37   comments: 23   posted: 3 hours ago      user: username
    --------
    """
    def lines_per_story(self):
        return 3

    def display_info(self, story):
        if len(story.url) > self.interface.body_max_x - 4:
            story.url = story.url[:self.interface.body_max_x-4-1]
        self.interface.body_win.addstr("    ")
        self.interface.body_win.addstr(story.url + "\n")
        super(CompressedFull, self).display_info(story)

class Full(CompressedFull):
    """
    Full display mode.
    Example:
    --------
     1. Story title
        http://www.example.com
        points: 37   comments: 23   posted: 3 hours ago      user: username

    --------
    """
    def lines_per_story(self):
        return 4

    def display_info(self, story):
        super(Full, self).display_info(story)
        self.interface.body_win.addstr("\n")


class Interface(object):
    """ ncurses interface of the program """

    display_modes = [CompressedFull, Full, SpacedDetailed, CompressedDetailed, Compact]

    def __init__(self, args):
        self.update_secs = Interval(args['interval']).to_secs()
        self.can_utf8 = args['utf8']
        self.new = args['new']
        self.pages_changed = True
        self.pages = 1
        self.start_pos = 0
        self.stories = []
        self.display_mode = 2
        self.display = self.display_modes[self.display_mode](self)

    def init_and_run(self, stdscr):
        """ called by ncurses.wrapper """
        self.stdscr = stdscr

        try:
            curses.curs_set(0)
        except:
            pass

        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)

        self.max_y, self.max_x = stdscr.getmaxyx()

        self.head_win = curses.newwin(4, self.max_x, 0, 0)
        self.body_win = curses.newwin(self.max_y-4, self.max_x, 4, 0)

        self.init_head_win()
        self.init_body_win()
        curses.doupdate()

        self.run()

    def init_head_win(self):
        """ Initializes the head/information window """
        info = "Hacker Top v" + version
        self.head_win.addstr(0, 4, info, curses.color_pair(4))

        x = self.head_win.getyx()[1]
        x += 4
        self.head_win.addstr("    Monitoring: ")

        if self.new:
            self.head_win.addstr("Hacker News newest stories", curses.A_BOLD)
        else:
            self.head_win.addstr("Hacker News front page", curses.A_BOLD)

        self.head_win.addstr(1, x, "Interval: ")
        if self.update_secs == 1:
            self.head_win.addstr("1 second", curses.A_BOLD)
        else:
            self.head_win.addstr("%d seconds" % self.update_secs, curses.A_BOLD)

        self.head_win.addstr(2, x, "Keys: 'j'/'k' - scroll, 'u' - update, 'm' - display mode")

        self.head_win.noutrefresh()

    def init_body_win(self):
        """ Initializes the body/story window """
        self.body_win.timeout(100)
        self.body_win.keypad(1)
        self.body_max_y, self.body_max_x = self.body_win.getmaxyx()
        wait_msg = "Retrieving data from Hacker News."
        self.body_win.addstr(self.body_max_y/2, self.body_max_x/2 - len(wait_msg)/2, wait_msg, curses.color_pair(3))

        self.body_win.noutrefresh()

    def resize(self):
        h, w = gethw()
        if not h:
            return

        curses.endwin()
        os.environ["LINES"] = str(h)
        os.environ["COLUMNS"] = str(w)
        curses.doupdate()

        self.body_max_y, self.body_max_x = self.body_win.getmaxyx()
        self.display.display(self.stories)
        
    def run(self):
        global RESIZE_EVENT
        while True:
            try:
                if RESIZE_EVENT:
                    RESIZE_EVENT = False
                    self.resize()
                c = self.body_win.getch()    # getch() has a 100ms timeout
                ret = self.handle_keystroke(c)
                if (ret == -1): return
                if retr_queue_out.empty():
                    continue
                action = retr_queue_out.get()
                action.do(self)
            except KeyboardInterrupt:
                break
            except curses.error, e:
                raise ProgError, "Curses Error: %s" % e

    def handle_keystroke(self, char):
        if char == ord('q'):
            # Notify Retriever to quit
            retr_queue_in.put(RetrieverQuit())
            return -1
        elif char == ord('u'):
            # Update stories NOW
            retr_queue_in.put(ForceUpdate())
            return
        elif char == curses.KEY_DOWN or char== ord('j'):
            # Scroll stories down by one
            if len(self.stories) - self.start_pos > self.display.max_display() / 2:
                self.start_pos += 1
                if self.stories:
                    self.display.display(self.stories)
                    if len(self.stories) - self.start_pos < self.display.max_display() and self.pages_changed:
                        self.pages += 1
                        self.pages_changed = False
                        retr_queue_in.put(ChangePages(self.pages))
            return
        elif char == curses.KEY_UP or char == ord('k'):
            # Scroll stories up by one
            if self.start_pos > 0:
                self.start_pos -= 1
                if self.stories:
                    self.display.display(self.stories)
                    if len(self.stories) - self.start_pos - self.display.max_display() > stories_per_page() and self.pages_changed:
                        self.pages -= 1
                        self.pages_changed = False
                        retr_queue_in.put(ChangePages(self.pages))
            return
        elif char == ord('m'):
            # Change display mode
            self.display_mode += 1 
            self.display_mode %= len(self.display_modes)
            self.display = self.display_modes[self.display_mode](self)
            if self.stories:
                self.display.display(self.stories)
            return
        elif char == ord('o'):
            # Open topmost story in webbrrowser (new window)
            webbrowser.open_new(self.stories[self.start_pos].url)
            return
        elif char == ord('t'):
            # Open topmost story in webbrowser (new tab)
            webbrowser.open_new_tab(self.stories[self.start_pos].url)
            return
        elif char == ord('c'):
            # Open topmost story's comments in webbrowser (new tab)
            webbrowser.open_new_tab(self.stories[self.start_pos].comments_url)
            return
            
class Interval(object):
    """ A class to dealing with refresh intervals """

    class IntervalError(Exception):
        """ Invalid interval error """
        pass
    
    interval_re = re.compile(r'^(\d+)(h|m|s)?$')

    def __init__(self, _interval):
        self._interval = _interval
        if not self.interval_ok():
            raise Interval.IntervalError, "Invalid interval format (%s)" % interval

    def interval_ok(self):
        if Interval.interval_re.match(self._interval):
            return True
        return False

    def to_secs(self):
        m = Interval.interval_re.match(self._interval)
        num, unit = m.groups()
        if not unit:
            unit = 's'
        
        num = int(num)
        
        if unit == 's':
            return num
        elif unit == 'm':
            return num*60
        elif unit == 'h':
            return num*60*60

    interval = property(lambda self: self._interval)

def gethw():
    """
    Get height and width of the terminal. Thanks to bobf from #python @ Freenode
    """

    h, w = struct.unpack(
        "hhhh", fcntl.ioctl(sys.__stdout__, termios.TIOCGWINSZ, "\000"*8))[0:2]
    return h, w

def html_unescape(str):
    """ Unescapes HTML entities """
    def entity_replacer(m):
        entity = m.group(1)
        if entity in entitydefs:
            return entitydefs[entity]
        else:
            return m.group(0)

    return re.sub(r'&([^;]+);', entity_replacer, str)

def nice_date(then, now=None):
    """
    Converts a (UTC) datetime object to a nice string representation.
    
    Taken from web.py
    """
    def agohence(n, what, divisor=None):
        if divisor: n = n // divisor

        out = str(abs(n)) + ' ' + what       # '2 day'
        if abs(n) != 1: out += 's'           # '2 days'
        out += ' '                           # '2 days '
        if n < 0:
            out += 'from now'
        else:
            out += 'ago'
        return out                           # '2 days ago'

    oneday = 24 * 60 * 60

    if not now: now = datetime.datetime.utcnow()
    if type(now).__name__ == "DateTime":
        now = datetime.datetime.fromtimestamp(now)
    if type(then).__name__ == "DateTime":
        then = datetime.datetime.fromtimestamp(then)
    delta = now - then
    deltaseconds = int(delta.days * oneday + delta.seconds + delta.microseconds * 1e-06)
    deltadays = abs(deltaseconds) // oneday
    if deltaseconds < 0: deltadays *= -1 # fix for oddity of floor

    if deltadays:
        if abs(deltadays) < 4:
            return agohence(deltadays, 'day')

        out = then.strftime('%B %e') # e.g. 'June 13'
        if then.year != now.year or deltadays < 0:
            out += ', %s' % then.year
        return out

    if int(deltaseconds):
        if abs(deltaseconds) > (60 * 60):
            return agohence(deltaseconds, 'hour', 60 * 60)
        elif abs(deltaseconds) > 60:
            return agohence(deltaseconds, 'minute', 60)
        else:
            return agohence(deltaseconds, 'second')

    deltamicroseconds = delta.microseconds
    if delta.days: deltamicroseconds = int(delta.microseconds - 1e6) # datetime oddity
    if abs(deltamicroseconds) > 1000:
        return agohence(deltamicroseconds, 'millisecond', 1000)

    return agohence(deltamicroseconds, 'microsecond')

def parse_args(args):
    """ Parse args given to program. Change appropriate variables.
    ps. i don't like optparse. """

    try:
        opts = getopt.getopt(args, "i:unh", ['interval=', 'utf8', 'new', 'help'])[0]
    except getopt.GetoptError, e:
        raise ArgError, str(e)

    return_args = {
        'interval': default_interval,
        'utf8': default_can_utf8,
        'new': default_new
    }

    for opt, val in opts:
        if opt in ("-h", "--help"):
            print_help()
            sys.exit(1)
        elif opt in ("-i", "--interval"):
            try:
                return_args['interval'] = Interval(val).interval
            except Interval.IntervalError, e:
                raise ArgError, e
        elif opt in ("-u", "--utf8"):
            return_args['urf8'] = True
        elif opt in ("-n", "--new"):
            return_args['new'] = True
        else:
            raise ArgError, "Don't know how to handle argument %s" % opt
    
    return return_args
    
def print_help():
    print_head()
    print
    print_usage()

def print_head():
    print "Hacker Top - follow your hacker news from the console!"
    print
    print "Made by Peteris Krumins (peter@catonmat.net)"
    print "http://www.catonmat.net  --  good coders code, great reuse"

def print_usage():
    print "Usage: %s [-h|--help] - displays this" % sys.argv[0]
    print "Usage: %s [-i|--interval interval] [-u|--utf8 <on|off>]" % sys.argv[0]
    print "          [-n|--new]"
    print
    print "-i|--interval specifies refresh interval."
    print " Valid examples: 10s (10 seconds), 12m (12 minutes), 42h (42 hours)."
    print " Default: %s" % default_interval
    print "-u|--utf8 turns on utf8 output mode. Use this if you know for sure that"
    print " your terminal supports it. Default: %s" % str(default_can_utf8)
    print "-n|--new specifies that new stories only should be monitored"
    print " Default: %s" % default_new

def sigwinch_handler(*dummy):
    global RESIZE_EVENT
    RESIZE_EVENT = True

def sigint_handler(*dummy):
    pass

if __name__ == "__main__":
    try:
        args = parse_args(sys.argv[1:])
    except ArgError, e:
        print "Argument Error: %s!" % e
        print 
        print_usage()
        sys.exit(1)

    retriever = Retriever(args)
    retriever.start()

    exit_code = 0

    signal.signal(signal.SIGWINCH, sigwinch_handler)

    try:
        interface = Interface(args)
        curses.wrapper(interface.init_and_run)
    except ProgError, e:
        exit_code = 1
        print "Program Error: %s!" % e
        if e.callback:
            e.callback()

    signal.signal(signal.SIGINT, sigint_handler)
    retr_queue_in.put(RetrieverQuit())   # notify thread to quit
    print "Quitting in a few seconds (waiting for thread to finish)..."
    sys.stdout.flush()
    retriever.join()
    sys.exit(exit_code)

