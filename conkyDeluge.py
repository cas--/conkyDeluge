#!/usr/bin/python
# -*- coding: utf-8 -*-
###############################################################################
# conkyDeluge.py is a simple python script to gather
# details of Deluge torrents for use in conky.
#
# Author: Kaivalagi
# Created: 13/10/2008
#
#Modified:
#    13/10/2008    Fixed progress % issue with multi-file torrents
#    14/10/2008    Added expected time of arrival (eta) as an output, can be used in the template with <eta>
#    17/10/2008    Updated to import and use deluge sclient and common formatting functions, disabled deluge logging functions too
#    17/10/2008    Updated to use "progress", "eta", "download_payload_rate", "upload_payload_rate" dictionary data to avoid invalid calculations
#    17/10/2008    --version now only returns version and doesn't try to display normal output too
#    30/10/2008    Updated error handling for when no torrent status data available, issues usually happen when half way through torrents output and a torrent is no longer there
#    30/10/2008    Added --errorlogfile and infologfile options, when set with a filepath, errors and info are appended to the filepath given
#    02/11/2008    Added --downloadsonly option to limit output to only currently active torrents in a downloading state
#    03/11/2008    Added currentpeers, currentseeds, totalpeers, totalseeds and ratio to the data available
#    03/11/2008    Updated to output text in utf-8 format, in case of strange characters used in torrent names etc
#    06/11/2008    Replaced the --downloadonly option with --activeonly, when used torrent output is only printed if there are active peers or seeds
#    06/11/2008    Renamed --template option to be called --torrenttemplate as it relates to individual torrent information
#    06/11/2008    Added --showsummary and --summarytemplate options to facilitate the displaying of summary information for all torrents. If --showsummary is used no torrent details are output. This is affected by the --activeonly option.
#    09/11/2008    Updated to collect torrent data into a class list to allow sorting (highest to lowest progress)
#    09/11/2008    Added --limit option to restrict the number of torrents displayed
#    12/11/2008    Now handles when Deluge is not running, and skips doing template prep that isn't required

#    15/11/2008    Now loading the template file in unicode mode to allow for the extended character set
#    18/11/2008    Added --hidetorrentdetail option, so both all combinations of output can be output in one exec call
#    18/11/2008    Added <totaleta> to the summary, basically displaying the highest eta for all torrents
#    18/11/2008    Changed option tags from <...> to [...], so <eta> now needs to be [eta] in the template to work
#    08/02/2009    Changed to use total_wanted stats (only selected parts of torrent) instead of total_size, fixes summary progress where partial downloads of torrents are in place

#    21/02/2009    Altered the ordering of the output to include state as well as progress, states are listed in the order downloading, seeding, paused, unknown
#    18/04/2009    Updated to retrieve data items for each torrent based on a finite list rather than all of them, this stops an error occuring with python 2.6 and xmlrpc
#    18/05/2009    Updated to expand ~ based template paths
#    26/06/2009    Added --sortby option, takes either "progress", "queue", "eta", "download", "upload" and "ratio" for sorting method.
#                  Also note that a torrent's state supersedes anything else for sorting,
#                  in the order, from top to bottom: downloading, seeding, queued, paused, unknown
#    18/10/2009    Updated to handle new DelugeRPC async methods used in 1.2.0 onwards (will mean this script breaks for previous deluge version users)

from datetime import datetime
from deluge.common import ftime, fsize, fspeed
from deluge.ui.client import client
from twisted.internet import reactor
from optparse import OptionParser
import codecs
import logging
import os
import sys
logging.disable(logging.FATAL) #disable logging within Deluge functions, only output info from this script

class CommandLineParser:

    parser = None

    def __init__(self):

        self.parser = OptionParser()
        self.parser.add_option("-s","--server", dest="server", type="string", default="127.0.0.1", metavar="SERVER", help=u"[default: %default] The server to connect to where the deluge core is running")
        self.parser.add_option("-p","--port", dest="port", type="int", default=58846, metavar="PORT", help=u"[default: %default] The port to connect to where the deluge core is running")
        self.parser.add_option("-U","--username", dest="username", type="string", metavar="USERNAME", help=u"The username to use when connecting, can be left unset if none is required")
        self.parser.add_option("-P","--password", dest="password", type="string", metavar="PASSWORD", help=u"The password to use when connecting, can be left unset if none is required")
        self.parser.add_option("-S","--showsummary",dest="showsummary", default=False, action="store_true", help=u"Display summary output. This is affected by the --activeonly option.")
        self.parser.add_option("-H","--hidetorrentdetail",dest="hidetorrentdetail", default=False, action="store_true", help=u"Hide torrent detail output, if used no torrent details are output.")
        self.parser.add_option("-t","--torrenttemplate",dest="torrenttemplate", type="string", metavar="FILE", help=u"Template file determining the format for each torrent. Use the following placeholders: [name], [state], [totaldone], [totalsize], [progress], [nofiles], [downloadrate], [uploadrate], [eta], [currentpeers], [currentseeds], [totalpeers], [totalseeds], [ratio].")
        self.parser.add_option("-T","--summarytemplate",dest="summarytemplate", type="string", metavar="FILE", help=u"Template file determining the format for summary output. Use the following placeholders: [notorrents], [totalprogress], [totaldone], [totalsize], [totaldownloadrate], [totaluploadrate], [totaleta], [currentpeers], [currentseeds], [totalpeers], [totalseeds], [totalratio].")
        self.parser.add_option("-a", "--activeonly", dest="activeonly", default=False, action="store_true", help=u"If set only info for torrents in an active state will be displayed.")
        self.parser.add_option("-l","--limit",dest="limit", default=0, type="int", metavar="NUMBER", help=u"[default: %default] Define the maximum number of torrents to display, zero means no limit.")
        self.parser.add_option("-b","--sortby",dest="sortby", default="eta", type="string", metavar="SORTTYPE", help=u"Define the sort method for output, can be \"progress\", \"queue\", \"eta\", \"download\", \"upload\" and \"ratio\". Also note that a torrent's state supersedes anything else for sorting, in the order, from top to bottom: downloading, seeding, queued, paused, unknown)")
        self.parser.add_option("-v","--verbose",dest="verbose", default=False, action="store_true", help=u"Request verbose output, no a good idea when running through conky!")
        self.parser.add_option("-V", "--version", dest="version", default=False, action="store_true", help=u"Displays the version of the script.")
        self.parser.add_option("--errorlogfile", dest="errorlogfile", type="string", metavar="FILE", help=u"If a filepath is set, the script appends errors to the filepath.")
        self.parser.add_option("--infologfile", dest="infologfile", type="string", metavar="FILE", help=u"If a filepath is set, the script appends info to the filepath.")

    def parse_args(self):
        (options, args) = self.parser.parse_args()
        return (options, args)

    def print_help(self):
        return self.parser.print_help()

class TorrentData:

    def __init__(self, name, state, statecode, totaldone, totalsize, progress, nofiles, downloadrate, downloadtext, uploadrate, uploadtext, eta, etatext, currentpeers, currentseeds, totalpeers, totalseeds, ratio, queueorder, sortby):
        self.name = name
        self.state = state
        self.statecode = statecode
        self.totaldone = totaldone
        self.totalsize = totalsize
        self.progress = progress
        self.nofiles = nofiles
        self.downloadrate = downloadrate
        self.downloadtext = downloadtext
        self.uploadrate = uploadrate
        self.uploadtext = uploadtext
        self.eta = eta
        self.etatext = etatext
        self.currentpeers = currentpeers
        self.currentseeds = currentseeds
        self.totalpeers = totalpeers
        self.totalseeds = totalseeds
        self.ratio = ratio
        self.queueorder = queueorder
        self.sortby = sortby

    def __cmp__(self, other):
        if self.sortby == "progress":
            return cmp(self.getProgressOrder(self.statecode,self.progress) , self.getProgressOrder(other.statecode,other.progress))
        elif self.sortby == "queue":
            return cmp(self.getQueueOrder(self.statecode,self.queueorder) , self.getQueueOrder(other.statecode,other.queueorder))
        elif self.sortby == "eta":
            return cmp(self.getETAOrder(self.statecode,self.eta) , self.getETAOrder(other.statecode,other.eta))
        elif self.sortby == "download":
            return cmp(self.getRateOrder(self.statecode,self.downloadrate) , self.getRateOrder(other.statecode,other.downloadrate))
        elif self.sortby == "upload":
            return cmp(self.getRateOrder(self.statecode,self.uploadrate) , self.getRateOrder(other.statecode,other.uploadrate))
        elif self.sortby == "ratio":
            return cmp(self.getRatioOrder(self.statecode,self.ratio) , self.getRatioOrder(other.statecode,other.ratio))
        else:
            return 0

    def __str__(self):
        return str(self.name + " - " + self.eta)

    def getProgressOrder(self,statecode,progress):
        return (statecode*10000.0)+float(progress.rstrip("%"))

    def getQueueOrder(self,statecode,queueorder):
        if queueorder <> -1:
            queueorder = 1000 - queueorder
        return (statecode*10000.0)+float(queueorder)

    def getETAOrder(self,statecode,eta):
        try:
            if eta <> -1:
                eta = (100000000 - eta)/100
            return (statecode*10000000.0)+float(eta)
        except:
            return 0

    def getRateOrder(self,statecode,rate):
        try:
            return (statecode*1000000.0)+float(rate)
        except:
            return 0

    def getRatioOrder(self,statecode,ratio):
        try:
            return (statecode*10000.0)+(100.0*float(ratio))
        except:
            return 0

class DelugeInfo:

    uri = None
    options = None
    sessionstate = None
    sessionstatefound = False

    STATE_DOWNLOADING = 4
    STATE_SEEDING = 3
    STATE_QUEUED = 2
    STATE_PAUSED = 1
    STATE_UNKNOWN = 0

    def __init__(self, options):

        try:

            #disable all logging within Deluge functions, only output info from this script
            logging.disable(logging.FATAL)

            self.options = options
            self.torrents_status = []
            # sort out the server option
            self.options.server = self.options.server.replace("localhost", "127.0.0.1")

            # create the rpc and client objects
            self.d = client.connect(self.options.server, self.options.port, self.options.username, self.options.password)

            # We add the callback to the Deferred object we got from connect()
            self.d.addCallback(self.on_connect_success)

            # We add the callback (in this case it's an errback, for error)
            self.d.addErrback(self.on_connect_fail)

            reactor.run()

        except Exception,e:
            self.logError("DelugeInfo Init:Unexpected error:" + e.__str__())

    def on_get_torrents_status(self,torrents_status):

        self.torrents_status = torrents_status

        #for torrentid in torrents_status:
            #print torrentid
            #torrent_status =  torrents_status[torrentid]

        # Disconnect from the daemon once we successfully connect
        client.disconnect()
        # Stop the twisted main loop and exit
        reactor.stop()

    # We create a callback function to be called upon a successful connection
    def on_connect_success(self,result):
        self.logInfo("Connection successful")
        client.core.get_torrents_status("","").addCallback(self.on_get_torrents_status)

    # We create another callback function to be called when an error is encountered
    def on_connect_fail(self,result):
        self.logError("Connection failed! : %s" % result.getErrorMessage())
        reactor.stop()

    def getTorrentTemplateOutput(self, template, name, state, totaldone, totalsize, progress, nofiles, downloadrate, uploadrate, eta, currentpeers, currentseeds, totalpeers, totalseeds, ratio):

        try:

            output = template

            output = output.replace("[name]",name)
            output = output.replace("[state]",state)
            output = output.replace("[totaldone]",totaldone)
            output = output.replace("[totalsize]",totalsize)
            output = output.replace("[progress]",progress)
            output = output.replace("[nofiles]",nofiles)
            output = output.replace("[downloadrate]",downloadrate)
            output = output.replace("[uploadrate]",uploadrate)
            output = output.replace("[eta]",eta)
            output = output.replace("[currentpeers]",currentpeers)
            output = output.replace("[currentseeds]",currentseeds)
            output = output.replace("[totalpeers]",totalpeers)
            output = output.replace("[totalseeds]",totalseeds)
            output = output.replace("[ratio]",ratio)

            # get rid of any excess crlf's and add just one
            output = output.rstrip(" \n")
            output = output + "\n"

            return output

        except Exception,e:
            self.logError("getTorrentTemplateOutput:Unexpected error:" + e.__str__())
            return ""

    def getSummaryTemplateOutput(self, template, notorrents, totalprogress, totaldone, totalsize, totaldownloadrate, totaluploadrate, totaleta, currentpeers, currentseeds, totalpeers, totalseeds, totalratio):

        try:

            output = template

            output = output.replace("[notorrents]",notorrents)
            output = output.replace("[totalprogress]",totalprogress)
            output = output.replace("[totaldone]",totaldone)
            output = output.replace("[totalsize]",totalsize)
            output = output.replace("[totaldownloadrate]",totaldownloadrate)
            output = output.replace("[totaluploadrate]",totaluploadrate)
            output = output.replace("[totaleta]",totaleta)
            output = output.replace("[currentpeers]",currentpeers)
            output = output.replace("[currentseeds]",currentseeds)
            output = output.replace("[totalpeers]",totalpeers)
            output = output.replace("[totalseeds]",totalseeds)
            output = output.replace("[totalratio]",totalratio)

            # get rid of any excess crlf's and add just one
            output = output.rstrip(" \n")
            output = output + "\n"

            return output

        except Exception,e:
            self.logError("getSummaryTemplateOutput:Unexpected error:" + e.__str__())
            return ""

    def writeOutput(self):

        try:

            self.logInfo("Proceeding with torrent data interpretation...")

            torrentDataList = []
            torrentItemList = ["num_peers","num_seeds","name","state","total_done","total_size","total_wanted","progress","files","eta","download_payload_rate","upload_payload_rate","total_peers","total_seeds","ratio","queue"]
            highesteta = 0

            # summary variables
            summary_notorrent = 0
            summary_totaldone = 0
            summary_totalsize = 0
            summary_totaldownloadrate = 0.0
            summary_totaluploadrate = 0.0
            summary_totaleta = 0
            summary_currentpeers = 0
            summary_currentseeds = 0
            summary_totalpeers = 0
            summary_totalseeds = 0
            summary_totalratio = 0.0

            self.logInfo("Preparing templates...")

            if self.options.summarytemplate == None:
                # create default summary template
                summarytemplate = "Total Torrents Queued:[notorrents] \n[totaldone]/[totalsize] - [totalprogress]\n" + "DL: [totaldownloadrate] UL: [totaluploadrate]\n"
            else:
                # load the template file contents
                try:
                    #fileinput = open(self.options.summarytemplate)
                    fileinput = codecs.open(os.path.expanduser(self.options.summarytemplate), encoding='utf-8')
                    summarytemplate = fileinput.read()
                    fileinput.close()
                except:
                    self.logError("Summary Template file no found!")
                    sys.exit(2)

            if self.options.torrenttemplate == None:
                # create default template
                torrenttemplate = "[name]\n[state]\n[totaldone]/[totalsize] - [progress]\n" + "DL: [downloadrate] UL: [uploadrate] ETA:[eta]\n"
            else:
                # load the template file contents
                try:
                    #fileinput = open(self.options.torrenttemplate)
                    fileinput = codecs.open(os.path.expanduser(self.options.torrenttemplate), encoding='utf-8')
                    torrenttemplate = fileinput.read()
                    fileinput.close()
                except:
                    self.logError("Torrent Template file no found!")
                    sys.exit(2)

            if len(self.torrents_status) > 0:

                self.logInfo("Processing %s torrent(s)..."%str(len(self.torrents_status)))

                for torrentid in self.torrents_status:
                    torrent_status = self.torrents_status[torrentid]

                    if torrent_status != None:

                        if self.options.activeonly == True:

                            active = False

                            # check for activity
                            if "num_peers" in torrent_status:
                                if torrent_status["num_peers"] > 0:
                                    active = True

                            if "num_seeds" in torrent_status:
                                if torrent_status["num_seeds"] > 0:
                                    active = True

                        # output details if all required or if active
                        if self.options.activeonly == False or active == True:

                            if "name" in torrent_status:
                                name = torrent_status["name"]
                            else:
                                name = "Unknown"

                            if "state" in torrent_status:
                                state = torrent_status["state"]

                                if state == "Downloading":
                                    statecode = self.STATE_DOWNLOADING
                                elif state == "Seeding":
                                    statecode = self.STATE_SEEDING
                                elif state == "Queued":
                                    statecode = self.STATE_QUEUED
                                elif state == "Paused":
                                    statecode = self.STATE_PAUSED
                                else:
                                    statecode = self.STATE_UNKNOWN
                            else:
                                state = "Unknown"
                                statecode = self.STATE_UNKNOWN

                            if "total_done" in torrent_status:
                                totaldone = fsize(torrent_status["total_done"])
                                summary_totaldone = summary_totaldone + int(torrent_status["total_done"])
                            else:
                                totaldone = "??.? KiB"

                            if "total_size" in torrent_status:
                                totalsize = fsize(torrent_status["total_wanted"])
                                summary_totalsize = summary_totalsize + int(torrent_status["total_wanted"])
                            else:
                                totalsize = "??.? KiB"

                            if "progress" in torrent_status:
                                progress = str(round(torrent_status["progress"],2))+"%"
                            else:
                                progress = "?.?%"

                            if "files" in torrent_status:
                                nofiles = str(len(torrent_status["files"]))
                            else:
                                nofiles = "?"

                            if "eta" in torrent_status:
                                eta = torrent_status["eta"]

                                if eta > highesteta:
                                    highesteta = eta

                                etatext = ftime(eta)
                            else:
                                eta = None
                                etatext = "Unknown"

                            if "download_payload_rate" in torrent_status:
                                downloadrate = float(torrent_status["download_payload_rate"])
                                summary_totaldownloadrate = summary_totaldownloadrate + downloadrate
                                downloadtext = fspeed(downloadrate)
                            else:
                                downloadrate = 0
                                downloadtext = "?.? KiB/s"

                            if "upload_payload_rate" in torrent_status:
                                uploadrate = float(torrent_status["upload_payload_rate"])
                                summary_totaluploadrate = summary_totaluploadrate + uploadrate
                                uploadtext = fspeed(uploadrate)
                            else:
                                uploadrate = 0
                                uploadtext = "?.? KiB/s"

                            if "num_peers" in torrent_status:
                                currentpeers = str(torrent_status["num_peers"])
                                summary_currentpeers = summary_currentpeers + int(torrent_status["num_peers"])
                            else:
                                currentpeers = "?"

                            if "num_seeds" in torrent_status:
                                currentseeds = str(torrent_status["num_seeds"])
                                summary_currentseeds = summary_currentseeds + int(torrent_status["num_seeds"])
                            else:
                                currentseeds = "?"

                            if "total_peers" in torrent_status:
                                totalpeers = str(torrent_status["total_peers"])
                                summary_totalpeers = summary_totalpeers + int(torrent_status["total_peers"])
                            else:
                                totalpeers = "?"

                            if "total_seeds" in torrent_status:
                                totalseeds = str(torrent_status["total_seeds"])
                                summary_totalseeds = summary_totalseeds + int(torrent_status["total_seeds"])
                            else:
                                totalseeds = "?"

                            if "ratio" in torrent_status:
                                ratio = str(round(torrent_status["ratio"],3)).ljust(5,"0")
                            else:
                                ratio = "?.???"

                            # for sorting in the same way as progress, we need to order from high to low
                            if "queue" in torrent_status:
                                queueorder = torrent_status["queue"]
                            else:
                                queueorder = -1

                            sortby = self.options.sortby

                            summary_notorrent = summary_notorrent + 1

                            # add torrent data to list
                            torrentData = TorrentData(name, state, statecode, totaldone, totalsize, progress, nofiles, downloadrate, downloadtext, uploadrate, uploadtext, eta, etatext, currentpeers, currentseeds, totalpeers, totalseeds, ratio, queueorder, sortby)
                            torrentDataList.append(torrentData)

                    else:
                        self.logInfo("No torrent status data available for torrentid: "+torrentid)

                if summary_notorrent > 0:

                    output = u""

                    if self.options.showsummary == True:

                        # sort out summary data for output
                        summary_notorrent = str(summary_notorrent)
                        summary_totalprogress = str(round((float(summary_totaldone) / float(summary_totalsize)) *100,2))+"%"
                        summary_totaldone = fsize(summary_totaldone)
                        summary_totalsize = fsize(summary_totalsize)
                        summary_totaldownloadrate = fspeed(summary_totaldownloadrate)
                        summary_totaluploadrate = fspeed(summary_totaluploadrate)
                        summary_totaleta = ftime(highesteta)
                        summary_currentpeers = str(summary_currentpeers)
                        summary_currentseeds = str(summary_currentseeds)
                        summary_totalpeers = str(summary_totalpeers)
                        summary_totalseeds = str(summary_totalseeds)
                        summary_totalratio = "?.???"

                        output = self.getSummaryTemplateOutput(summarytemplate, summary_notorrent, summary_totalprogress, summary_totaldone, summary_totalsize, summary_totaldownloadrate, summary_totaluploadrate, summary_totaleta, summary_currentpeers, summary_currentseeds, summary_totalpeers, summary_totalseeds, summary_totalratio)

                    if self.options.hidetorrentdetail == False:

                        outputCount = 0

                        # sort list, eta based
                        self.logInfo("Sorting torrent list using: %s"%self.options.sortby)
                        torrentDataList.sort(reverse = True)

                        # output torrent data using the template
                        for torrentData in torrentDataList:

                            # keep a tally of torrent output, if past the limit then exit
                            if self.options.limit <> 0:
                                outputCount = outputCount + 1
                                if outputCount > self.options.limit:
                                    break

                            output = output + self.getTorrentTemplateOutput(torrenttemplate, torrentData.name, torrentData.state, torrentData.totaldone, torrentData.totalsize, torrentData.progress, torrentData.nofiles, torrentData.downloadtext, torrentData.uploadtext, torrentData.etatext, torrentData.currentpeers, torrentData.currentseeds, torrentData.totalpeers, torrentData.totalseeds, torrentData.ratio)+"\n"

                    print output.encode("utf-8")

                else:
                    print u"No torrent info to display"

            else:
                self.logInfo("No torrents found")

        except Exception,e:
            self.logError("writeOutput:Unexpected error:" + e.__str__())

    def logInfo(self, text):
        if self.options.verbose == True:
            print >> sys.stdout, "INFO: " + text

        if self.options.infologfile != None:
            datetimestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fileoutput = open(self.options.infologfile, "ab")
            fileoutput.write(datetimestamp+" INFO: "+text+"\n")
            fileoutput.close()

    def logError(self, text):
        print >> sys.stderr, "ERROR: " + text

        if self.options.errorlogfile != None:
            datetimestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fileoutput = open(self.options.errorlogfile, "ab")
            fileoutput.write(datetimestamp+" ERROR: "+text+"\n")
            fileoutput.close()

def main():

    parser = CommandLineParser()
    (options, args) = parser.parse_args()

    if options.version == True:

        print >> sys.stdout,"conkyDeluge v.2.14.1"

    else:

        if options.verbose == True:
            print >> sys.stdout, "*** INITIAL OPTIONS:"
            print >> sys.stdout, "    server:",options.server
            print >> sys.stdout, "    port:",options.port
            print >> sys.stdout, "    username:",options.username
            print >> sys.stdout, "    password:",options.password
            print >> sys.stdout, "    showsummary:",options.showsummary
            print >> sys.stdout, "    torrenttemplate:",options.torrenttemplate
            print >> sys.stdout, "    summarytemplate:",options.summarytemplate
            print >> sys.stdout, "    activeonly:",options.activeonly
            print >> sys.stdout, "    limit:",options.limit
            print >> sys.stdout, "    sortby:",options.sortby
            print >> sys.stdout, "    errorlogfile:",options.errorlogfile
            print >> sys.stdout, "    infologfile:",options.infologfile

        delugeInfo = DelugeInfo(options)
        if len(delugeInfo.torrents_status) > 0:
            delugeInfo.writeOutput()

if __name__ == '__main__':
    main()
    sys.exit()

