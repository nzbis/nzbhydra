from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from builtins import *
from builtins import str
from future import standard_library

from nzbhydra.exceptions import DownloaderException

#standard_library.install_aliases()
import base64
import json
import logging
import socket
import xmlrpc.client
from furl import furl
import requests
from requests.exceptions import HTTPError, SSLError, ConnectionError, ReadTimeout
from nzbhydra import config


class Downloader(object):
    
    def add_link(self, link, title, category):
        return True

    def add_nzb(self, content, title, category):
        return True

    def get_categories(self):
        return []


class Nzbget(Downloader):
    logger = logging.getLogger('root')

    def get_rpc(self, host=None, ssl=None, port=None, username=None, password=None):
        if host is None:
            host = config.settings.downloader.nzbget.host
        if ssl is None:
            ssl = config.settings.downloader.nzbget.ssl
        if port is None:
            port = config.settings.downloader.nzbget.port
        if username is None:
            username = config.settings.downloader.nzbget.username
        if password is None:
            password = config.settings.downloader.nzbget.password
        f = furl()
        f.host = host
        f.username = username
        f.password = password
        f.scheme = "https" if ssl else "http"
        f.port = port
        f.path.add("xmlrpc")

        return xmlrpc.client.ServerProxy(f.tostr())

    def test(self, host, ssl=False, port=None, username=None, password=None, apikey=None):
        self.logger.debug("Testing connection to snzbget")
        rpc = self.get_rpc(host, ssl, port, username, password)

        try:
            if rpc.writelog('INFO', 'NZB Hydra connected to test connection'):
                version = rpc.version()
                #todo: show error if version older than 13
                if int(version[:2]) < 13:
                    self.logger.error("NZBGet needs to be version 13 or higher")
                    return False, "NZBGet needs to be version 13 or higher"
                self.logger.info('Connection test to NZBGet successful')
            else:
                self.logger.info('Successfully connected to NZBGet, but unable to send a message')
        except socket.error:
            self.logger.error('NZBGet is not responding. Please ensure that NZBGet is running and host setting is correct.')
            return False, "NZBGet is not responding under this address, scheme and port"
        except xmlrpc.client.ProtocolError as e:
            if e.errcode == 401:
                self.logger.error('Wrong credentials')
                return False, "Wrong credentials"
            else:
                self.logger.error('Protocol error: %s', e)
            return False, str(e)

        return True, ""

    def add_link(self, link, title, category):
        self.logger.debug("Sending add-link request for %s to nzbget" % title)
        if title is None:
            title = ""
        else:
            if not title.endswith(".nzb"):  # NZBGet skips entries of which the filename does not end with NZB
                title += ".nzb"
        category = "" if category is None else category

        rpc = self.get_rpc()
        try:
            rcode = rpc.append(title, link, category, 0, False, False, "", 0, "SCORE",[])
            if rcode > 0:
                self.logger.info("Successfully added %s from %s to NZBGet" % (title, link))
                return True
            else:
                self.logger.error("NZBGet returned an error while adding %s from %s" % (title, link))
                return False
        except socket.error:
            self.logger.error('NZBGet is not responding. Please ensure that NZBGet is running and host setting is correct.')
            return False
        except xmlrpc.client.ProtocolError as e:
            if e.errcode == 401:
                self.logger.error('Wrong credentials')
            else:
                self.logger.error('Protocol error: %s', e)
            return False

    def add_nzb(self, content, title, category):
        self.logger.debug("Sending add-nzb request for %s to nzbget" % title)
        if title is None:
            title = ""
        else:
            if not title.endswith(".nzb"):  # NZBGet skips entries of which the filename does not end with NZB
                title += ".nzb"
        category = "" if category is None else category

        encoded_content = base64.standard_b64encode(content).decode()  # Took me ages until I found out I was still sending bytes instead of a string 

        rpc = self.get_rpc()
        try:
            rcode = rpc.append(title, encoded_content, category, 0, False, False, "", 0, "SCORE")
            if rcode > 0:
                self.logger.info("Successfully added %s to NZBGet" % title)
                return True
            else:
                self.logger.error("NZBGet returned an error while adding NZB for %s" % title)
                return False
        except socket.error as e:
            self.logger.debug(str(e))
            self.logger.error('NZBGet is not responding. Please ensure that NZBGet is running and host setting is correct.')
            return False
        except xmlrpc.client.ProtocolError as e:
            if e.errcode == 401:
                self.logger.error('Wrong credentials')
            else:
                self.logger.error('Protocol error: %s', e)
            return False
        
    def get_categories(self):
        self.logger.debug("Sending categories request to nzbget")
        try:
            rpc = self.get_rpc()
            config = rpc.config()
            categories = []
            for i in config:
                if "Category" in i["Name"] and "Name" in i["Name"]:
                    categories.append(i["Value"])
            return categories

        except socket.error as e:
            self.logger.debug(str(e))
            self.logger.error('NZBGet is not responding. Please ensure that NZBGet is running and host setting is correct.')
            raise DownloaderException("Unable to contact NZBGet")
        
        except xmlrpc.client.ProtocolError as e:
            if e.errcode == 401:
                self.logger.error('Wrong credentials')
            else:
                self.logger.error('Protocol error: %s', e)
            raise DownloaderException("Unable to contact NZBGet")


class Sabnzbd(Downloader):
    logger = logging.getLogger('root')

    def get_sab(self, url=None, apikey=None, username=None, password=None):
        if url is None:
            url = config.settings.downloader.sabnzbd.url
        if apikey is None:
            apikey = config.settings.downloader.sabnzbd.apikey
        if username is None:
            username = config.settings.downloader.sabnzbd.username
        if password is None:
            password = config.settings.downloader.sabnzbd.password
        f = furl(url)
        f.path.add("api")
        if apikey:
            f.add({"apikey": apikey})
        elif username and password:
            pass
        else:
            raise DownloaderException("Neither API key nor username/password provided")
        f.add({"output": "json"})

        return f

    def test(self, url, username=None, password=None, apikey=None):
        self.logger.debug("Testing connection to sabnzbd")
        try:
            f = self.get_sab(url, apikey, username, password)
            f.add({"mode": "qstatus"})
            r = requests.get(f.tostr(), verify=False, timeout=15)
            r.raise_for_status()
            if "state" in json.loads(r.text).keys():
                self.logger.info('Connection test to sabnzbd successful')
                return True, ""
            else:
                self.logger.info("Access to sabnzbd failed, probably due to wrong credentials")
                return False, "Credentials wrong?"
        except DownloaderException as e:
            self.logger.error("Error while trying to connect to sabnzbd: %s" % e)
            return False, str(e)
        except (SSLError, HTTPError, ConnectionError, ReadTimeout) as e:
            self.logger.error("Error while trying to connect to sabnzbd: %s" % e)
            return False, "SABnzbd is not responding"

    def add_link(self, link, title, category):
        self.logger.debug("Sending add-link request for %s to sabnzbd" % title)
        if title is None:
            title = ""
        else:
            if not title.endswith(".nzb"):  # sabnzbd skips entries of which the filename does not end with NZB
                title += ".nzb"

        f = self.get_sab()
        f.add({"mode": "addurl", "name": link, "nzbname": title})
        if category is not None:
            f.add({"cat": category})
        try:
            r = requests.get(f.tostr(), verify=False, timeout=15)
            r.raise_for_status()
            return r.json()["status"]
        except (SSLError, HTTPError, ConnectionError, ReadTimeout):
            self.logger.exception("Error while trying to connect to sabnzbd using link %s" % link)
            return False

    def add_nzb(self, content, title, category):
        self.logger.debug("Sending add-nzb request for %s to sabnzbd" % title)
        if title is None:
            title = ""
        else:
            if not title.endswith(".nzb"):  # sabnzbd skips entries of which the filename does not end with NZB
                title += ".nzb"

        f = self.get_sab()
        f.add({"mode": "addfile", "nzbname": title})
        if category is not None:
            f.add({"cat": category})
        try:
            files = {'nzbfile': (title, content)}
            r = requests.post(f.tostr(), files=files, verify=False,timeout=15)
            r.raise_for_status()
            return r.json()["status"]
        except (SSLError, HTTPError, ConnectionError, ReadTimeout):
            self.logger.exception("Error while trying to connect to sabnzbd with URL %s" % f.url)
            return False

    def get_categories(self):
        self.logger.debug("Sending categories request to sabnzbd")
        f = self.get_sab()
        f.add({"mode": "get_cats", "output": "json"})
        try:
            r = requests.get(f.tostr(), verify=False, timeout=15)
            r.raise_for_status()
            return r.json()["categories"]
        except (SSLError, HTTPError, ConnectionError, ReadTimeout):
            self.logger.exception("Error while trying to connect to sabnzbd with URL %s" % f.url)
            raise DownloaderException("Unable to contact SabNZBd")
