#!/usr/bin/env python
# (c) 2011 Christian Kellner <kellner@bio.lmu.de>

import sys
import getopt
import os
import datetime
from paramiko import SSHClient, SSHConfig

baseURL = "sftp://gate.g-node.org/groups/wachtler/literature"

class Paper(object):
    def __init__(self, name, inCentury):
        self._name = name
        extStart = name.rfind(".")
        ext = name[extStart+1:]
        self._ext = ext
        if ext != 'pdf':
            return None
        self._century = inCentury

        yearStart = -1
        for idx in xrange(0, extStart):
            if name[idx].isdigit():
                yearStart = idx
                break

        if not yearStart != -1:
            return None

        yearEnd = -1
        for idx in xrange(yearStart, extStart+1):
            if not name[idx].isdigit():
                yearEnd = idx
                break

        if not yearEnd != -1:
            return None

        self._author = name[:yearStart]
        self._year = int(name[yearStart:yearEnd])

    @property
    def year(self):
        year = self._year
        yearBase = self._century
        if not yearBase:
            yearBase = 20

        year += yearBase * 100
        return year
        
    @property
    def author(self):
        return self._author

    @property
    def filetype(self):
        return self._ext

    @property
    def uri(self):
        return None

    @property
    def name(self):
        return self._name

    def __repr__(self):
        return "Paper('%s')" % self.name

    def __str__(self):
        return "%s %d" % (self.author, self.year)


class Filter(object):
    def __init__(self, searchFor=None, inYear=None):
        self._filterString = searchFor
        self.year = inYear

    def apply(self, paper):

        if paper.filetype != 'pdf':
            return False

        if self.year != None and paper.year != self.year:
            return False

        if not self._filterString:
            return True
        else:
            return paper.author.startswith(self._filterString)

    @property
    def year(self):
        return self._year

    @year.setter
    def year(self, value):
        if not value:
            self._year = None
            return

        if type(value) != int:
            value = self._parseYear(value)
        self._year = value

    def _parseYear(self, string):
        yearEnd = len(string)
        for idx in xrange(0, yearEnd):
            if not string[idx].isdigit():
                yearEnd = idx
                break

        year = int(string[0:yearEnd])
        return year

class Library(object):
    def __init__(self):
        path = os.path.expanduser ('~/.ssh/config')
        cfg = SSHConfig()
        cfg.parse(open(path))

        ssh = SSHClient()
        ssh.load_system_host_keys()

        (host, params) = self._ssh_cfg2params(cfg)
        ssh.connect(host, **params)

        self._ssh = ssh
        self._sftp = ssh.open_sftp()

    def _ssh_cfg2params(self, config):
        params = {}
        cfg = config.lookup ('gate.g-node.org')
        if cfg and cfg.has_key('user'):
            params['username'] = cfg['user']
        else:
            params['username'] = os.getlogin()
            
        if cfg and cfg.has_key('identityfile'):
            params['key_filename'] = cfg['identityfile']
        else:
            keyfile = os.path.expanduser ('~/.ssh/id_rsa')
            params['key_filename'] = keyfile

        return ('gate.g-node.org', params)

    def _year2folder(self, year):  
        if year < 1998:
            if year < 1990:
                string = "%.2s.." % str(year)
            else:
                string = "%.3s." % str(year)
        else:
            string = str(year)

        return string

    def _folder2century(self, folder):
        yearEnd = len(folder)
        for idx in xrange(0, yearEnd):
            if not folder[idx].isdigit():
                yearEnd = idx
                break
        yearStr = folder[0:yearEnd]
        return int (int(yearStr)/(pow(10, len(yearStr) - 2)))

    def _pathForPaper(self, paper):
        basepath = self.basepath
        folder = self._year2folder(paper.year)
        path = "%s%s/%s" % (basepath, folder, paper.name)
        return path

    def uriForPaper(self, paper):
        path = self._pathForPaper(paper)
        return "sftp://gate.g-node.org" + path

    def list(self, withFilter):
        basepath = self.basepath
        melitta = withFilter

        if not melitta.year:
            folders = self.paperFolders
        else:
            folders = {str(melitta.year) : basepath + self._year2folder(melitta.year)}

        sftp = self._sftp
        papers = []
        for year in folders.iterkeys():
            names = sftp.listdir(path=folders[year])
            for name in names:
                century = self._folder2century(year)
                try:
                    paper = Paper(name, century)
                    if melitta.apply(paper):
                        papers.append(paper)
                except:
                    print "Could not parse: %s" % (name)

        return papers

    def download(self, papers, pbar, localDir=None):
        sftp = self._sftp
        localFiles = []

        if type(papers) != list:
            papers = [papers]

        for paper in papers:
            remote = self._pathForPaper(paper)
            if not localDir:
                localDir = os.getcwd()
            local = os.path.join (localDir, paper.name)
            sftp.get(remote, local, pbar.callback)
            localFiles.append(local)
            pbar.nextTask()

        return localFiles

    @property
    def paperFolders(self):
        sftp = self._sftp
        wd = self.basepath
        dirs = sftp.listdir(path=wd)
        folders = {folder : wd + folder for folder in dirs if folder[0].isdigit()}
        return folders

    @property
    def basepath(self):
        return '/groups/wachtler/literature/'


class ProgressBar(object):
    
    def __init__(self, numTasks=1):
        self._numTasks = numTasks
        self._curTask = 1

    def progress(self,  cur_value, max_value):
        size = 60
        prefix = "%2s/%2s" % (self._curTask, self._numTasks)
        x = int (size*cur_value/max_value)
        sys.stdout.write("%s [%s%s] %i/%i\r" % (prefix, "#"*x, "." * (size-x),
                                                cur_value, max_value))
        sys.stdout.flush()

    def nextTask(self):
        self._curTask += 1

    @property
    def callback(self):
        return self.progress

# ----- -----
def printPaperList(papers, withNumber=False):
    extraSpace = 0

    fmt = "%-20s | %4s | %-25s"
    string = fmt % ("Author", "year", "Filename")
    fmt_len = 55

    if withNumber:
        prefix = " Id | "
        string = prefix + string
        extraSpace = len(prefix)

    print string
    print "-"*(fmt_len + extraSpace)

    num = 0
    for paper in papers:
        string = fmt % (paper.author, paper.year, paper.name)
        if withNumber:
            string = "%3d | %s" % (num, string)
            num += 1
        print string

    print "-"*(fmt_len + extraSpace)

def userPickPaper(papers):
    question = "Select number or all[default] ?"

    while True:
        answer = raw_input(question)
        if answer == 'all' or answer == 'a':
            return papers
        try:
            num = int(answer)
            paper = papers[num]
            return [paper]
        except:
            continue

# ---- commands ----

commands = {}
def Command(name, aliases=None):
    def decorator(func):
        commands[name] = func
        if aliases:
            for alias in aliases:
                commands[alias] = func
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
        return wrapper
    return decorator


@Command('list', ['l'])
def doList(lib, withFilter):
    melitta = withFilter
    if not melitta.year:
        print "Global search! This may take a while..."
    papers = lib.list(withFilter=melitta)
    printPaperList(papers)
    return 0

@Command('download', ['dl'])
def doDownload(lib, withFilter):
    melitta = withFilter
    papers = lib.list(withFilter=melitta)

    if len(papers) > 1:
        printPaperList(papers, withNumber=True)
        print "Multiple matches found!"
        papers = userPickPaper(papers)
        
    pbar = ProgressBar(numTasks=len(papers))
    lib.download(papers, pbar)
    return 0

@Command('open', ['o'])
def doOpen(lib, withFilter):
    melitta = withFilter
    papers = lib.list(withFilter=melitta)

    if len(papers) > 1:
        printPaperList(papers, withNumber=True)
        numStr = raw_input ('Number to open? ')
        try:
            num = int(numStr)
            paper = papers[num]
        except:
            print "Oh oh!"
            return -1
    else:
        paper = papers[0]

    pbar = ProgressBar(numTasks=len(papers))
    local = lib.download (paper, pbar, '/tmp')

    cmd = 'xdg-open "%s"' % (local[0])
    os.system (cmd)
    return 0

# ---- ---- ----
def createFilter(argv):
    year=None
    filterStr=None

    if argv[0][0].isdigit():
        year = argv[0]
    else:
        filterStr = argv[0]

    if len(argv) > 1:
        if not year:
            year = argv[1]
        else:
            filterStr = argv[1]

    melitta = Filter(searchFor=filterStr, inYear=year)
    return melitta

def main(argv):
    
    opts, rem = getopt.getopt(sys.argv[1:], 'v', ['version',
                                                   ])
    output = None
    for opt, arg in opts:
        if opt in ("-o", "--output"):
            output = arg

    if len (rem) < 1:
        print "Wrong number of arguments"
        return -1

    cmdStr = rem[0]

    if not commands.has_key(cmdStr):
        print >> sys.stderr, "Unkown command: %s." % (cmdStr)
        return -1;

    melitta = createFilter(rem[1:])
    cmd = commands[cmdStr]
    lib = Library()
    res = cmd(lib, melitta)

    return res

if __name__ == "__main__":
    res = main(sys.argv[1:])
    sys.exit(res)
