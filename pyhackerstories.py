#!/usr/bin/python
# 
# Peteris Krumins (peter@catonmat.net)
# http://www.catonmat.net  --  good coders code, great reuse
#
# Released under GNU GPL license.
#
# Developed as a part of hacker top program. Read how it was designed:
# http://www.catonmat.net/blog/follow-hacker-news-from-the-console/
#

import re
import sys
import time
import socket
import urllib2
import datetime
from BeautifulSoup import BeautifulSoup

version = "1.0"

hacker_url = 'http://news.ycombinator.com'
hacker_url_new = 'http://news.ycombinator.com/newest'

class RedesignError(Exception):
    """
    An exception class thrown when it seems that Hacker News has redesigned
    """
    pass

class SeriousError(Exception):
    """
    An exception class thrown when something unexpected happened
    """
    pass

class Story(dict):
    """
    Encapsulates the information about a single Hacker News story.

    After the object is constructed it contains the following attributes:
    * position
    * id
    * title
    * url
    * user
    * score
    * human_time
    * unix_time
    * comments
    """

    def __repr__(self):
        inner = ', '.join([repr(x) for x in ((self.position),  str(self.id), str(self.title),
            str(self.url), str(self.user), str(self.score), str(self.human_time),
            str(self.unix_time), str(self.comments))])
        return ''.join(('{', inner, '}'))

def stories_per_page():
    """ Returns stories per single web page """
    return 30

def get_stories(pages=1, new=False):
    """
    Finds all stories accross 'pages' pages and returns a list of Story objects
    representing stories.

    If new is True, gets new stories from http://news.ycombinator.com/newest
    """

    stories = [] 
    url = hacker_url
    if new: url = hacker_url_new
    for i in range(pages):
        content = _get_page(url)
        entries = _extract_stories(content)
        stories.extend(entries)
        url = _get_next_page(content)
        if not url:
            break

    for pos, story in enumerate(stories):
        story.position = pos+1

    return stories;

def _extract_stories(content):
    """
    Given an HTML page, extracts all the stories and returns a list of Story
    objects representing stories.
    """

    stories = []
    soup = BeautifulSoup(content)

    def mk_tag_finder(name, klass, attrs):
        def td_finder(tag):
            if tag.name != name: return False
            if len(tag.attrs) != attrs: return False
            # if 'class' not in tag: return False          ### won't work
            try:
                if tag['class'] == klass: return True
            except KeyError:
                return False
        return td_finder
        
    title_tds = soup.findAll(mk_tag_finder('td', 'title', 1))
    vote_as = soup.findAll('a', id=re.compile(r'up_\d+'))
    subtext_tds = soup.findAll(mk_tag_finder('td', 'subtext', 1))

    if len(title_tds) != len(subtext_tds) != len(vote_as):
        raise RedesignError, "lengths of title, vote and subtext lists do not match"

    for title_td, vote_a, subtext_td in zip(title_tds, vote_as, subtext_tds):
        title_a = title_td.find('a')
        if not title_a:
            raise RedesignError, "title <a> was not found"

        title = title_a.string.strip()
        url = title_a['href']
        if url.startswith('item'): # link to the story itself
            url = hacker_url + '/' + url

        m = re.search(r'up_(\d+)', vote_a['id'])
        if not m:
            raise RedesignError, "title id did not contain story id"
        id = m.group(1)

        score_span = subtext_td.find('span', id=re.compile(r'score_(\d+)'))
        if not score_span:
            raise RedesignError, "could not find <span> containing score"
        m = re.search(r'(\d+) point', score_span.string)
        if not m:
            raise RedesignError, "unable to extract score"
        score = int(m.group(1))

        user_a = subtext_td.find('a', href=re.compile(r'^user'))
        if not user_a:
            raise RedesignError, "unable to find <a> containing username"
        user = user_a.string

        posted_re = re.compile(r'\s+(.+)\s+ago')
        posted_text = subtext_td.find(text = posted_re)
        if not posted_text:
            raise RedesignError, "could not find posted ago text"
        m = posted_re.search(posted_text);
        posted_ago = m.group(1)
        unix_time = _ago_to_unix(posted_ago)
        if not unix_time:
            raise RedesignError, "unable to extract story date"
        human_time = time.ctime(unix_time)

        comment_a = subtext_td.find('a', href=re.compile(r'^item'))
        if not comment_a:
            comments = -1
        elif comment_a.string == "discuss":
            comments = 0
        else:
            m = re.search(r'(\d+) comment', comment_a.string)
            if not m:
                raise RedesignError, "could not extract comment cound"
            comments = int(m.group(1))

        story = Story()
        story.id = id
        story.title = title.encode('utf8')
        story.url = url.encode('utf8')
        story.score = score
        story.comments = comments
        story.user = user.encode('utf8')
        story.unix_time = unix_time
        story.human_time = human_time.encode('utf8')

        stories.append(story)

    return stories

def _ago_to_unix(ago):
    m = re.search(r'(\d+) (\w+)', ago, re.IGNORECASE)
    if not m:
        return 0

    delta = int(m.group(1))
    units = m.group(2)

    if not units.endswith('s'): # singular
        units += 's' # append 's' to make it plural

    if units == "months":
        units = "days"
        delta *= 30        # lets take 30 days in a month
    elif units == "years":
        units = "days"
        delta *= 365

    dt = datetime.datetime.now() - datetime.timedelta(**{units: delta})
    return int(time.mktime(dt.timetuple()))

def _get_page(url, timeout=10):
    """ Gets and returns a web page at url with timeout 'timeout'. """

    old_timeout = socket.setdefaulttimeout(timeout)

    request = urllib2.Request(url)
    request.add_header('User-Agent', 'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)')

    try:
        response = urllib2.urlopen(request)
        content = response.read()
    except (urllib2.HTTPError, urllib2.URLError, socket.error, socket.sslerror), e:
        socket.setdefaulttimeout(old_timeout)
        raise SeriousError, e

    socket.setdefaulttimeout(old_timeout)
    return content

def _get_next_page(content):
    soup = BeautifulSoup(content)
    a = soup.find(lambda tag: tag.name == 'a' and tag.string == u'More')
    if a:
        return hacker_url + a['href']

def print_stories_paragraph(stories):
    """
    Given a list of Stories, prints them out paragraph by paragraph
    """
    
    for story in stories:
        print 'position:', story.position
        print 'id:', story.id
        print 'title:', story.title
        print 'url:', story.url
        print 'score:', story.score
        print 'comments:', story.comments
        print 'user:', story.user
        print 'unix_time:', story.unix_time
        print 'human_time:', story.human_time
        print

if __name__ == '__main__':
    from optparse import OptionParser

    description = "A program by Peteris Krumins (http://www.catonmat.net)"
    usage = "%prog [options]"

    parser = OptionParser(description=description, usage=usage)
    parser.add_option("-p", action="store", type="int", dest="pages",
                      default=1, help="How many pages of stories to output. Default: 1.")
    parser.add_option("-n", action="store_true", dest="new", 
                      help="Retrieve new stories. Default: nope.")
    options, args = parser.parse_args()

    try:
        stories = get_stories(options.pages, options.new)
    except RedesignError, e:
        print >>sys.stderr, "Hacker News have redesigned: %s!" % e
        sys.exit(1)
    except SeriousError, e:
        print >>sys.stderr, "Serious error: %s!" % e
        sys.exit(1)

    print_stories_paragraph(stories)

