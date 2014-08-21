'''
Copyright (C) 2014, Digium, Inc.
Jonathan Rose <jrose@digium.com>

This program is free software, distributed under the terms of
the GNU General Public License Version 2.
'''

import logging

LOGGER = logging.getLogger(__name__)

def on_kickoff_start(ari, event, test_object):
    LOGGER.debug("on_kickoff_start(%r)" % event)
    ari.post('channels', endpoint='Local/1000@default', app='testsuite',
             channelId='continue_guy', appArgs='dummy')
    ari.delete('channels', event['channel']['id'])
    return True

def on_channel_destroyed(ari, event, test_object):
    LOGGER.debug("on_channel_destroyed(%r)" % event)
    if event['channel']['id'] == 'continue_guy':
        test_object.stop_reactor()
    return True
