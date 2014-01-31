#!/usr/bin/env python

import logging
import pjsua as pj

LOGGER = logging.getLogger(__name__)

states = [
    ('INUSE', 2, "Offline"),
    ('ONHOLD', 2, "Offline"),
    ('BUSY', 2, "Offline"),
    ('RINGING', 2, "Offline"),
    ('UNAVAILABLE', 2, "Offline"),
    ('NOT_INUSE', 1, "Online"),
    ('', 1, "Online")  # Final state upon subscription teardown
]


class BobCallback(pj.BuddyCallback):
    def __init__(self, bob, test_object):
        pj.BuddyCallback.__init__(self, bob)
        self.pos = 0
        self.test_object = test_object
        self.ami = self.test_object.ami[0]
        self.check_status = False

    def on_state(self):
        info = self.buddy.info()

        LOGGER.info("Bob status to folow")
        LOGGER.info("Online status: %d" % info.online_status)
        LOGGER.info("Online text: %s" % info.online_text)
        LOGGER.info("Activity: %d" % info.activity)
        LOGGER.info("Sub state: %d" % info.sub_state)

        # We don't care about the buddy state until the subscription is active.
        if info.sub_state < pj.SubscriptionState.ACTIVE:
            return

        if self.check_status:
            if info.online_status != states[self.pos][1]:
                LOGGER.error("Unexpected state %d. Expected %d" %
                             (info.online_status,  states[self.pos][1]))
                self.test_object.set_passed(False)
                self.test_object.stop_reactor(False)
            if info.online_text != states[self.pos][2]:
                LOGGER.error("Unexpected text %s. Expected %s" %
                             (info.online_text, states[self.pos][2]))
                self.test_object.set_passed(False)
                self.test_object.stop_reactor()
            self.pos += 1
            if (self.pos >= len(states)):
                self.test_object.set_passed(True)
                self.test_object.stop_reactor()

        if self.pos < len(states) and states[self.pos][0]:
            LOGGER.info("Setting device state to %s" % states[self.pos][0])
            self.check_status = True
            self.ami.setVar(channel="", variable="DEVICE_STATE(Custom:bob)",
                            value=states[self.pos][0])
        else:
            self.buddy.unsubscribe()


def buddy_subscribe(test_object, accounts):
    alice = accounts.get('alice')
    bob = alice.buddies.get('bob')
    bob.set_callback(BobCallback(bob, test_object))
    bob.subscribe()
