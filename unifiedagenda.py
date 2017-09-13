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


def unfold_ical(lines):
    out = []
    for line in lines:
        if line[0] == ' ' or line[0] == '\t':
            out[-1] += line[1:]
        else:
            out += [line]
    return out


def getcomponents(lines):
    """Parse an array of lines into a series of nested dicts and arrays.

    RFC 5545 specified a recursive structure for calendar objects, with each
    component beginning with a `BEGIN:(component)` line, and ending with an
    `END:(component)` line. Sets of components may all occupy the same level,
    without any additional syntax. Recursive components may be defined within
    BEGIN and END lines of a single parent component.

    This function generalizes this format, and parses it into a nested dict
    structure, such that it may be faithfully output using the json library.

    Components with the same name, defined on the same level, are grouped into
    a single element in the containing dict as an array of dicts, with their
    shared name as the key. Unique components are still stored in a single
    element array.

    properties with the same name, defined on the same level, are grouped into
    a single element in the containing dict as an array of 2-tuples. each tuple
    contains a dict of the property's parameters, and an array or string of the
    property's values.
    """
    level = 0
    component = {}
    innercomponent = []
    innercomponentname = ''
    for line in lines:
        if line.startswith('BEGIN:'):
            level += 1
            if level == 1:
                innercomponentname = line.split(':')[1]
                innercomponent = []
                if innercomponentname not in component.keys():
                    component[innercomponentname] = []
            else:
                innercomponent += [line]
        elif line.startswith('END:'):
            level -= 1
            if level == 0:
                name = line.split(':')[1]
                if name == innercomponentname:
                    component[name] += [getcomponents(innercomponent)]
                else:
                    errortext = 'START:{} and END:{} statements do not match'
                    errortext = errortext.format(innercomponentname, name)
                    raise SyntaxError(errortext)
            else:
                innercomponent += [line]
        elif ':' in line:
            if level == 0:
                key = line[:line.index(':')]
                value = line[line.index(':') + 1:]
                params = key.split(';')
                name = params[0]
                params = params[1:]
                paramdict = {}
                for param in params:
                    [pname, pval] = param.split('=')
                    paramdict[pname] = pval.split(',')
                if name not in component.keys():
                    component[name] = []
                component[name] += [(paramdict, v) for v in value.split(',')]
            else:
                innercomponent += [line]
        else:
            errortext = 'Line {} does not contain ":"'.format(repr(line))
            raise SyntaxError(errortext)
    return component


def parse_calendar_data(calendarpath):
    with open(calendarpath, 'r') as calfile:
        lines = unfold_ical(calfile.readlines())
    return getcomponents(lines)['VCALENDAR']


class unifiedagenda:
    """docstring for unifiedagenda."""
    ID = 'io.zjp.unifiedagenda'
    CONFIG_PATH = '~/.config/' + ID
    SETTINGS_NAME = 'settings.json'
    DEFAULT_SETTINGS = {
        'calendars': []
    }

    def __init__(self):
        self.CONFIG_PATH = os.path.expanduser(self.CONFIG_PATH)
        self.SETTINGS_PATH = self.CONFIG_PATH + '/' + self.SETTINGS_NAME
        try:
            os.makedirs(self.CONFIG_PATH, 0o755)
        except FileExistsError:
            pass
        self.load_settings()
        self.parse_calendars()

    def sync_calendars(self):
        webcalendars = [cal for cal in self.settings['calendars']
                        if 'url' in cal.keys()
                        ]
        for calendar in webcalendars:
            r = requests.get(calendar['url'])
            print('requesting calendar for {}...'.format(calendar['name']))
            print(r.status_code)
            with open(calendar['path'], 'w') as calendarfile:
                calendarfile.write(r.text)

    def parse_calendars(self):
        self.calendars = []
        for calendar in self.settings['calendars']:
            self.calendars += parse_calendar_data(calendar['path'])

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
