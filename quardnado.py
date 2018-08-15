#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys, imp, time, signal
#reload(sys)
#sys.setdefaultencoding('utf8')
import random, threading
import os, glob
import collections

import tornado
import tornado.httpserver
import tornado.ioloop
import tornado.web

__TTSVERSION__ = lambda:1
def TTSRHclear(self):
    self._TTS_pre_clear()
    self._headers = tornado.web.httputil.HTTPHeaders({
        "Content-Type": "text/html; charset=UTF-8",
        "Date": tornado.web.httputil.format_timestamp(time.time()),
    })
TTSRequestHandler = tornado.web.RequestHandler
TTSRequestHandler._TTS_pre_clear = TTSRequestHandler.clear
TTSRequestHandler.clear = TTSRHclear

def fullroot(a):
    return a.strip('/') + '(?:|/(.+)?)$'

def tornado_get_client(cls, abspath, start=None, end=None):
        """Retrieve the content of the requested resource which is located
        at the given absolute path.

        This class method may be overridden by subclasses.  Note that its
        signature is different from other overridable class methods
        (no ``settings`` argument); this is deliberate to ensure that
        ``abspath`` is able to stand on its own as a cache key.

        This method should either return a byte string or an iterator
        of byte strings.  The latter is preferred for large files
        as it helps reduce memory fragmentation.

        .. versionadded:: 3.1
        """
        with open(abspath, "rb") as file:
            if start is not None:
                file.seek(start)
            if end is not None:
                remaining = end - (start or 0)
            else:
                remaining = None
            while True:
                chunk_size = 64 * 1024
                if remaining is not None and remaining < chunk_size:
                    chunk_size = remaining
                chunk = file.read(chunk_size)
                if chunk:
                    if remaining is not None:
                        remaining -= len(chunk)
                    yield chunk
                else:
                    if remaining is not None:
                        assert remaining == 0
                    return

class DLFileHandler(TTSRequestHandler):
    def initialize(self, nf=None, download=False, py=False, folder=None, pyfct=None, postget=False):
        self.ttserver = sys.modules[__name__]
        self.nf = nf
        self.py = py
        self.pyfct = pyfct or 'main'
        self.dl = download
        self.folder = folder
        if postget:
            self.post = self.get

    @tornado.gen.coroutine
    def get(self, *a, **kw):
        nf = self.nf
        if self.folder:
            nf = self.folder+'/'+a[0]
        if nf and '@' in nf:
            i = 0
            while True:
                rep = '@'+str(i)
                if rep not in nf:break
                print(nf, rep, a[i])
                nf = nf.replace(rep, a[i])
                i += 1
        if nf and '*' in nf:
            nfs = glob.glob(nf)
            print(nfs)
            nf = nfs[0]
        if self.dl:
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Length', str(os.path.getsize(nf)))
            self.set_header('Content-Disposition', 'attachment; filename="%s"'%(nf.split('/')[-1]))

        if self.py:
            if self.py.__class__ == type:
                mdl = self.py(**dict([['handler',self]] * int('handler_in_main' in dir(self.py))))
                mdl.handler = self
            else:
                mdl = imp.load_source('mdl', self.nf)
            assert mdl.__TTSVERSION__() >= __TTSVERSION__(), "Bad protocol version of Quarnado ({} >= {})".format(mdl.__TTSVERSION__(), __TTSVERSION__())
            content = getattr(mdl,self.pyfct)(self,*a,**kw)
        else:
            content = self.get_content(nf)

        if content.__class__ == str:content = [content]
        if content != None:
            for c in content:
                self.write(c)
                yield self.flush()

    @classmethod
    def get_content(cls, abspath, start=None, end=None):
        return tornado_get_client(cls, abspath, start, end)

class Application(tornado.web.Application):
    def __init__(self, port = None, sslparams = None):
        handlers = []
        self.httpsettings = dict(
#            template_path = os.path.join(os.path.dirname(__file__), "templates"),
#            static_path = os.path.join(os.path.dirname(__file__), "static"),
#            debug = True,
        )
        if sslparams:
            certfile, keyfile = sslparams   # *.crt, *.key
            self.httpsettings['ssl_options'] = {'certfile': certfile, 'keyfile': keyfile}

        tornado.web.Application.__init__(self, handlers)
        self.listening = False
        self.port = port
    def addh(self, path, h, params=None, hostname='.*'):
        params = params or {}
        h = h or DLFileHandler
        return self.add_handlers(hostname,
            [(path, h, params)],
        )
    def makeserv(self, port):
        http_server = tornado.httpserver.HTTPServer(self, **self.httpsettings)
        http_server.listen(port)
        print('Quardnado port: %d'%port)
        self.listening = True
        return http_server
    def tstart(self):
        t = threading.Thread(None, self.start)
        t.start()
        t.name = "TTserver.Application"
    def start(self):
        if not self.listening:
            self.makeserv(self.port)
        ioloop = tornado.ioloop.IOLoop.instance()
        ioloop.start()
    def stop(self):
        ioloop = tornado.ioloop.IOLoop.instance()
        ioloop.add_callback(ioloop.stop)

class MyNameHandler(TTSRequestHandler):
    def get(self, *a, **kw):
        sys.stdout = self
        print("File: %s"%os.path.basename(__file__))
        sys.stdout = sys.__stdout__

def create_cert(fn):
    cmds = '''openssl genrsa -des3 -passout pass:x -out "{fn}.pass.key" 2048
openssl rsa -passin pass:x -in "{fn}.pass.key" -out "{fn}.key"
openssl req -new -key "{fn}.key" -out "{fn}.csr"
openssl x509 -req -sha256 -days 365 -in "{fn}.csr" -signkey "{fn}.key" -out "{fn}.crt"
cat {fn}.crt {fn}.key > {fn}.hap.pem'''.format(fn=fn).split('\n')
    for cmd in cmds:
        os.system(cmd)

if 'sharefile' in sys.argv:
    import uuid
    port = 9000
    app = Application()
    as_dl = str(uuid.uuid4())
    as_raw = str(uuid.uuid4())
    filename = 'quardnado.py'
    app.addh('/' + as_dl, DLFileHandler, {'nf': filename, 'download': True})
    app.addh('/' + as_raw, DLFileHandler, {'nf': filename, 'download': False})
    print('Open as download: /%s'%as_dl)
    print('Open as raw: /%s'%as_raw)
    http_server = tornado.httpserver.HTTPServer(app)
    http_server.bind(port)
    http_server.start(0)
    tornado.ioloop.IOLoop.instance().start()

elif __name__ == "__main__":
    app = Application()
    port = int(sys.argv[1]) if len(sys.argv)>1 else 9000
    app.addh('/myname', MyNameHandler)
    app.addh('/download_file', DLFileHandler, {'nf': 'quardnado.py'})
    app.addh('/download_in_folder/(.*)', DLFileHandler, {'folder': './', 'download': True})
    app.addh('/advanced_download_file_(.*).mp4', DLFileHandler, {'nf': '/home/user/downloads/*/*Final Fantasy @0*/*.iso', 'download': True})
    http_server = tornado.httpserver.HTTPServer(app)
    http_server.bind(port)
    http_server.start(0)
    tornado.ioloop.IOLoop.instance().start()
