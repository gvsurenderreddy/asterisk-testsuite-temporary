#!/usr/bin/env python
'''
Copyright (C) 2013, Digium, Inc.
Jonathan Rose <jrose@digium.com>

This program is free software, distributed under the terms of
the GNU General Public License Version 2.
'''

import sys
import logging
import re

sys.path.append("lib/python")

LOGGER = logging.getLogger(__name__)

class Executioner(object):
    def __init__(self, module_config, test_object):
        self.ami = None
        self.parked_channel = None
        test_object.register_ami_observer(self.ami_connect)
        self.test_object = test_object

        self.calls = []
        self.calls.append({'parker' : 'alice', 'parkee' : 'bob'})
        self.calls.append({'parker' : 'bob', 'parkee' : 'alice'})
        self.calls.append({'parker' : 'alice', 'parkee' : 'bob'})
        self.calls.append({'parker' : 'bob', 'parkee' : 'alice'})

        self.parking_events_received = 0

        return

    def ami_connect(self, ami):
        # We only care about the UUT's AMI here
        if ami.id != 0:
            return

        self.ami = ami
        self.ami.registerEvent('Hangup', self.check_hangup)
        self.ami.registerEvent('ParkedCall', self.check_park)


    def check_hangup(self, ami, event):
        # We only hangup when we know that both the channel that initiated park and our zombie channel are gone.
        if (self.hangups_processed == 1):
            ami.hangup(self.parked_channel)
        self.hangups_processed += 1

    def check_park(self, ami, event):
        self.parking_events_received += 1
        this_expectation = self.calls.pop(0)
        this_parker = this_expectation['parker']
        this_parkee = this_expectation['parkee']

        this_result_parker = event.get('from')
        this_result_parkee = event.get('channel')
        self.parked_channel = this_result_parkee

        self.hangups_processed = 0

        # Make sure the park event matches expectations. If not, we autofail.
        if this_result_parker == None or this_result_parkee == None:
            LOGGER.error("Phase %d: event %s - missing either 'from' or 'channel' fields." % (self.parking_events_received, event))
            self.test_object.set_passed(False)
            return

        if not (re.match( (".*/%s-.*" % this_parker), this_result_parker)):
            LOGGER.error("Phase %d: The expected parker (%s) did not match the parker received in the park event (%s)." % (self.parking_events_received, this_parker, this_result_parker))
            self.test_object.set_passed(False)
            return

        if not (re.match( (".*/%s-.*" % this_parkee), this_result_parkee)):
            LOGGER.error("Phase %d: The expected parkee (%s) did not match the parkee received from the park event (%s)." % (self.parking_events_received, this_parkee, this_result_parkee))
            self.test_object.set_passed(False)
            return

        LOGGER.info ("Phase %d: Parker and Parkee for this phase arrived as expected.  The parkee (%s) will be hungup." % (self.parking_events_received, this_result_parkee))
