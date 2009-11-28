This is the Hacker Top program. It's a top-like program for monitoring stories
on hacker news (news.ycombinator.com) from the console.

It was written by Peteris Krumins (peter@catonmat.net).
His blog is at http://www.catonmat.net  --  good coders code, great reuse.

The code is licensed under the GNU GPL license.

The code was written as a part of the article "Follow Hacker News from the
Console" on my website. The whole article can be read at:

    http://www.catonmat.net/blog/follow-hacker-news-from-the-console/

I explained some parts of the code in this program in another article "How
Reddit Top and Hacker Top Programs Were Made". It can be read here:

http://www.catonmat.net/blog/how-reddit-top-and-hacker-top-programs-were-made/

------------------------------------------------------------------------------

Table of contents:

    [1] The Hacker Top program.
    [2] Program's usage.
    [3] Keyboard shortcuts.
    [4] Future TODO improvements.


[1]-The-Hacker-Top-program----------------------------------------------------

This program monitors the Hacker News website ( http://news.ycombinator.com )
for hacker stories and displays them in the console via ncurses.

The program is written in Python programming language and is supposed to
be run on Unix type operating systems, such as Linux.

It uses one external Python module - BeautifulSoup - for parsing HTML.
BeautifulSoup can be downloaded from http://crummy.com/software/BeautifulSoup
or via `easy_install beautifulsoup` 

See my original article for a screenshot:

    http://www.catonmat.net/blog/follow-hacker-news-from-the-console/


[2]-Hacker-Top-usage----------------------------------------------------------

Usage: ./hacker_top.py [-h|--help] - displays help message

Usage: ./hacker_top.py [-i|--interval interval]
          [-u|--utf8 <on|off>] [-n|--new]

    -i or --interval specifies refresh interval.
    The default refresh interval is 3 minutes. Here are a few
    examples:  10s (10 seconds), 12m (12 minutes), 2h (2 hours). 

    -u or --utf8 turns on utf8 output mode.
    Default: off. Use this if you know for sure that your
    terminal supports it, otherwise your terminal might turn into garbage.

    -n or --new follows only the newest hacker stories.
    Default: follow front page stories.


[3]-Keyboard-shortcuts--------------------------------------------------------

q - quits the program.
u - forces an update of the stories.
m - changes the display mode.
up/down arrows (or j/k) - scrolls the news list up or down.


[4]-Future-TODO-improvements--------------------------------------------------

* Add a feature to open a story in web browser. (Someone suggested to use
  webbrowser module)

* Fix it to work on Windows. (Perhaps try the Console module)

* Merge it with "Reddit Top" program (see below) and create "Social Top"
  program. Then write plugins for Digg, and other websites.

  Reddit Top is here (currently broken, will fix on Sunday 2009.11.29):
  http://www.catonmat.net/blog/follow-reddit-from-the-console/

* Add ability to login and vote for the favorite stories.


------------------------------------------------------------------------------


Have fun using it!


Sincerely,
Peteris Krumins
http://www.catonmat.net

