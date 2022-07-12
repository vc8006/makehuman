#!/usr/bin/python

__all__ = ["api","namespace","JsonCall"]

from .api import API
from logging import *
LOG_FORMAT = "[%(asctime)s] [%(filename)s:%(lineno)s - %(funcName)s() ] %(message)s"
# LOG_FORMAT = '%m-%d %H:%M:%S','[%(asctime)s] {%(pathname)s:%(lineno)d} %(funcName)s - %(message)s'
basicConfig(filename="allLogs.log",level = DEBUG,format=LOG_FORMAT)


def load(app):
    debug("log")

    app.mhapi = API(app)

def unload(app):
    debug("log")
    pass

