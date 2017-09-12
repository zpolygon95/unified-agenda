#!/usr/bin/env python3
"""Unified Agenda creates a Unity AppIndicator, showing your next appointment.

Unified Agenda gets information about events from iCal sources -- either local
files, or those hosted on the web -- and displays information from those
calendars about the day's appointments as a Unity AppIndicator. Visible on the
Top Bar, will be the name of and time remaining until the next scheduled
appointment. During an appointment, Unified Agenda can optionally display the
time until the end of the current appointment -- for when you just need to know
how much longer this meeting will be.

The attached menu will show the names and times for each subsequent event, and
will include several configuration options.

    00:30 'til Foo
    ├── Foo: 09:00 - 10:00
    ├── Bar: 11:00 - 11:30
    └── Baz: 12:00 - 14:00
    ┌── Sync Now
    ├── Settings
    └── Quit
"""

import json
import os
import requests


class unifiedagenda:
    """docstring for unifiedagenda."""
    ID = 'io.zjp.unified-agenda'
    CONFIG_PATH = '~/.config/' + ID
    SETTINGS_NAME = 'settings.json'
    DEFAULT_SETTINGS = {
        'webcalendars': []
    }

    def __init__(self):
        self.CONFIG_PATH = os.path.expanduser(self.CONFIG_PATH)
        self.SETTINGS_PATH = self.CONFIG_PATH + '/' + self.SETTINGS_NAME
        try:
            os.makedirs(self.CONFIG_PATH, 0o755)
        except FileExistsError:
            pass
        self.load_settings()
        print(self.settings)
        self.sync_calendars()

    def sync_calendars(self):
        for calendar in self.settings['webcalendars']:
            r = requests.get(calendar['url'])
            print('requesting calendar for {}...'.format(calendar['name']))
            print(r.status_code)
            calendarpath = self.CONFIG_PATH + '/' + calendar['name'] + '.ics'
            with open(calendarpath, 'w') as calendarfile:
                calendarfile.write(r.text)

    def load_settings(self):
        try:
            with open(self.SETTINGS_PATH) as settingsfile:
                self.settings = json.load(settingsfile)
        except FileNotFoundError:
            self.settings = self.DEFAULT_SETTINGS
            self.save_settings()

    def save_settings(self):
        with open(self.SETTINGS_PATH, 'w') as settingsfile:
            json.dump(self.settings, settingsfile, indent=1)
            settingsfile.write('\n')


if __name__ == '__main__':
    unifiedagenda()
