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

import argparse
import datetime as dt
import json
import os
import requests

import dateutil.parser as parser
import dateutil.rrule as rrule
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk as gtk
from gi.repository import AppIndicator3 as appind
from gi.repository import Notify as notify
import threading


def unfold_ical(lines):
    out = []
    for line in lines:
        if line[0] == ' ' or line[0] == '\t':
            out[-1] += line[1:].rstrip('\r\n')
        else:
            out += [line.rstrip('\r\n')]
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
                component[name] += [(paramdict, value)]
            else:
                innercomponent += [line]
        else:
            errortext = 'Line {} does not contain ":"'.format(repr(line))
            raise SyntaxError(errortext)
    return component


def parse_calendar_data(calendarpath):
    try:
        with open(calendarpath, 'r') as calfile:
            lines = unfold_ical(calfile.readlines())
        return getcomponents([l.strip() for l in lines])
    except FileNotFoundError:
        return None


def tzinfo_from_tzid(tzid, vtimezones):
    """Return a tzinfo object representing the given tzid string.

    The mappings between tzid and tzinfo are obtained from the list of
    vtimezones, as created from an ical source by the getcomponents function.
    """
    for tz in vtimezones:
        pass


def get_occurrences(event, rstart, rend):
    """Get the occurrences of event touching the range between rstart and rend.

    The dateutil.ruleset.between function does not properly detect that any
    part of an event falls within a range. There exist the following cases:

    1.  event lies entirely within range
           [event]
        [---range---]

    2.  event begins before, but ends during range
        [event]
           [---range---]

    3.  event begins during, but ends after range
                 [event]
        [---range---]

    4.  event begins before, and ends after range
        [---event---]
           [range]

    5.  event begins and ends before range
        [event]
                [range]

    6.  event begins and ends after range
                [event]
        [range]

    Cases 1 through 4 are considered to be "touching" the given range.
    """
    assert rstart <= rend
    start = parser.parse(event['DTSTART'][0][1])
    end = parser.parse(event['DTEND'][0][1])
    delta = end - start
    occurrences = []
    if 'RRULE' in event.keys() and start.date() <= rstart:
        ruleset = rrule.rrulestr(
            '\r\n'.join([e[1] for e in event['RRULE']]),
            dtstart=start,
            forceset=True,
            ignoretz=True
        )
        if 'EXDATE' in event.keys():
            for date in event['EXDATE']:
                ruleset.exdate(parser.parse(date[1]))
        return [
            (event, d, d + delta)
            for d in ruleset.between(
                dt.datetime.combine(rstart, dt.time(0, 0)),
                dt.datetime.combine(rend, dt.time(23, 59)),
                inc=True
            )
        ]
    else:
        occurrences = [(event, start, end)]
    return [
        o for o in occurrences
        if o[1].date() <= rend and o[2].date() >= rstart
    ]


class unifiedagenda:
    """docstring for unifiedagenda."""
    ID = 'io.zjp.unifiedagenda'
    CONFIG_PATH = '~/.config/' + ID
    SETTINGS_NAME = 'settings.json'
    DEFAULT_SETTINGS = {
        'calendars': []
    }

    def __init__(self, path):
        self.CONFIG_PATH = os.path.expanduser(path)
        self.SETTINGS_PATH = self.CONFIG_PATH + '/' + self.SETTINGS_NAME
        try:
            os.makedirs(self.CONFIG_PATH, 0o755)
        except FileExistsError:
            pass
        self.load_settings()
        self.parse_calendars()

    def get_events(self, rstart=dt.date.today(), rend=dt.date.today()):
        events = []
        for calendar in self.calendars:
            for event in calendar['VEVENT']:
                events += get_occurrences(event, rstart, rend)
        return events

    def sync_calendars(self):
        webcalendars = [cal for cal in self.settings['calendars']
                        if 'url' in cal.keys() and cal['url'] is not ''
                        ]
        for calendar in webcalendars:
            r = requests.get(calendar['url'])
            # print('requesting calendar for {}...'.format(calendar['name']))
            # print(r.status_code)
            with open(calendar['path'], 'w') as calendarfile:
                calendarfile.write(r.text)
        self.parse_calendars()

    def parse_calendars(self):
        self.calendars = []
        checkcals = [cal for cal in self.settings['calendars']
                     if 'path' in cal.keys() and cal['path'] is not ''
                     ]
        for calendar in checkcals:
            data = parse_calendar_data(calendar['path'])
            if data is not None:
                self.calendars += data['VCALENDAR']
            else:
                self.sync_calendars()
                data = parse_calendar_data(calendar['path'])
                if data is not None:
                    self.calendars += data['VCALENDAR']
                else:
                    print('Calendar {} not found.\nShould be at {}'.format(
                        calendar['name'],
                        calendar['path']
                    ))

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


class agendaindicator:
    """Insert docstring here"""

    def __init__(self, args):
        self.agenda = unifiedagenda(args.settings)
        self.ID = self.agenda.ID
        self.indicator = appind.Indicator.new(
            self.ID,
            gtk.STOCK_INFO,
            appind.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_label('testing!', '')
        self.indicator.set_status(appind.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())
        notify.init(self.ID)

    def run(self):
        self.running = True
        self.update()
        gtk.main()

    def build_menu(self):
        events = sorted(self.agenda.get_events(), key=lambda e: e[1])
        menu = gtk.Menu()
        for event in events:
            summary = event[0]['SUMMARY'][0][1]
            start = event[1].strftime('%H:%M')
            end = event[2].strftime('%H:%M')
            menutext = '{} - {}\t{}'
            menutext = menutext.format(start, end, summary)
            menuitem = gtk.MenuItem(menutext)
            menu.append(menuitem)
        menu.append(gtk.SeparatorMenuItem())
        item_sync = gtk.MenuItem('Sync')
        item_sync.connect('activate', self.sync)
        menu.append(item_sync)
        item_nudge = gtk.MenuItem('Nudge')
        item_nudge.connect('activate', self.nudge)
        menu.append(item_nudge)
        item_pref = gtk.MenuItem('Preferences')
        item_pref.connect('activate', self.open_prefs)
        menu.append(item_pref)
        item_quit = gtk.MenuItem('Quit')
        item_quit.connect('activate', self.quit)
        menu.append(item_quit)
        menu.show_all()
        return menu

    def nudge(self, e):
        print(repr(self.indicator.set_label('test', '')))
        print(repr(self.indicator.get_label()))

    def update(self):
        if self.running:
            events = sorted(self.agenda.get_events(), key=lambda e: e[1])
            now = dt.datetime.today()
            nextevent = None
            currentevent = None
            for event in events:
                if event[1] < now and event[2] > now:
                    currentevent = event
                if event[1] > now:
                    break
            for event in events:
                nextevent = event
                if event[1] > now:
                    break
            if currentevent is not None:
                label = '{name} for {hours:02d}:{minutes:02d}'
                ename = currentevent[0]['SUMMARY'][0][1]
                delta = currentevent[2] - now
                args = {
                    'name': ename,
                    'hours': delta.seconds // 3600,
                    'minutes': (delta.seconds // 60) % 60
                }
                label = label.format(**args)
                self.indicator.set_label(label, '')
            elif nextevent is not None:
                label = '{name} in {hours:02d}:{minutes:02d}'
                ename = nextevent[0]['SUMMARY'][0][1]
                delta = nextevent[1] - now
                args = {
                    'name': ename,
                    'hours': delta.seconds // 3600,
                    'minutes': (delta.seconds // 60) % 60
                }
                label = label.format(**args)
                self.indicator.set_label(label, '')
            else:
                self.indicator.set_label('No more events', '')
            threading.Timer(1, self.update).start()
        else:
            notify.uninit()
            gtk.main_quit()

    def sync(self, event):
        self.agenda.load_settings()
        self.agenda.sync_calendars()
        self.indicator.set_menu(self.build_menu())

    def open_prefs(self, event):
        win = PrefsWindow(self.agenda.settings)
        win.connect('delete-event', self.close_prefs)
        win.show_all()

    def close_prefs(self, window, event):
        self.agenda.settings = window.settings
        self.agenda.save_settings()

    def quit(self, event):
        self.running = False


class PrefsWindow(gtk.Window):

    def __init__(self, settings):
        gtk.Window.__init__(self, title="Preferences")
        self.settings = settings

        self.set_border_width(10)
        vbox = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=6)
        vbox.pack_start(self.build_sources_menu(), False, False, 10)
        # vbox.pack_start(self.build_placeholder_menu(), False, False, 10)
        self.add(vbox)

    def build_placeholder_menu(self):
        return gtk.Label('Placeholder')

    def build_sources_menu(self):
        hbox = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=6)

        self.calstack = gtk.Stack()
        self.calstack.set_transition_type(gtk.StackTransitionType.NONE)

        for calendar in self.settings['calendars']:
            grid = self.build_cal_menu(calendar)
            self.calstack.add_titled(grid, calendar['name'], calendar['name'])

        stack_switcher = gtk.StackSidebar()
        stack_switcher.set_stack(self.calstack)
        addbutton = gtk.Button('+')
        addbutton.connect('clicked', self.add_calendar)
        delbutton = gtk.Button('-')
        delbutton.connect('clicked', self.remove_calendar)
        buttonbox = gtk.Box(orientation=gtk.Orientation.HORIZONTAL)
        buttonbox.pack_start(addbutton, True, True, 0)
        buttonbox.pack_start(delbutton, True, True, 0)
        controlbox = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        controlbox.pack_start(stack_switcher, True, True, 0)
        controlbox.pack_start(buttonbox, False, False, 0)
        hbox.pack_start(controlbox, False, False, 0)
        hbox.pack_start(self.calstack, True, True, 0)
        return hbox

    def build_cal_menu(self, calendar):
        grid = gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(5)
        lname = gtk.Label('name')
        ename = gtk.Entry()
        ename.set_text(calendar['name'])
        ename.set_hexpand(True)
        ename.set_name(calendar['name'])
        ename.connect(
            'focus-out-event',
            lambda widget, event: self.rename_calendar(
                widget.get_name(),
                widget.get_text()
            )
        )
        lpath = gtk.Label('path')
        epath = gtk.Entry()
        epath.set_icon_from_icon_name(gtk.EntryIconPosition.SECONDARY,
                                      gtk.STOCK_OPEN
                                      )
        epath.set_icon_activatable(gtk.EntryIconPosition.SECONDARY, True)
        epath.set_icon_tooltip_text(gtk.EntryIconPosition.SECONDARY,
                                    'Open file dialog'
                                    )
        epath.connect('icon-release', self.choose_path)
        epath.set_text(calendar['path'])
        epath.set_name(calendar['name'])
        epath.connect(
            'focus-out-event',
            lambda widget, event: self.set_calendar_settings(
                widget.get_name(),
                'path',
                widget.get_text()
            )
        )
        lurl = gtk.Label('url')
        eurl = gtk.Entry()
        eurl.set_text(calendar['url'])
        eurl.set_name(calendar['name'])
        eurl.connect(
            'focus-out-event',
            lambda widget, event: self.set_calendar_settings(
                widget.get_name(),
                'url',
                widget.get_text()
            )
        )
        grid.add(lname)
        grid.attach(ename, 1, 0, 2, 1)
        grid.attach(lpath, 0, 1, 1, 1)
        grid.attach(epath, 1, 1, 2, 1)
        grid.attach(lurl, 0, 2, 1, 1)
        grid.attach(eurl, 1, 2, 2, 1)
        return grid

    def add_calendar(self, widget):
        ncalname = 'New Calendar'
        newcal = {
            'name': ncalname,
            'path': '',
            'url': ''
        }
        self.settings['calendars'] += [newcal]
        grid = self.build_cal_menu(newcal)
        self.calstack.add_titled(grid, ncalname, ncalname)
        self.show_all()
        self.calstack.set_visible_child_name(ncalname)

    def remove_calendar(self, widget):
        toremove = self.calstack.get_visible_child_name()
        self.settings['calendars'] = [
            cal for cal in self.settings['calendars']
            if cal['name'] != toremove
        ]
        self.calstack.remove(self.calstack.get_visible_child())
        self.show_all()

    def rename_calendar(self, oldname, newname):
        for i in range(len(self.settings['calendars'])):
            if self.settings['calendars'][i]['name'] == oldname:
                self.settings['calendars'][i]['name'] = newname
                self.calstack.remove(self.calstack.get_child_by_name(oldname))
                grid = self.build_cal_menu(self.settings['calendars'][i])
                self.calstack.add_titled(grid, newname, newname)
                self.show_all()
                self.calstack.set_visible_child_name(newname)

    def choose_path(self, widget, pos, event):
        dialog = gtk.FileChooserDialog(
            'Set Calendar Path',
            self,
            gtk.FileChooserAction.SAVE,
            (
                gtk.STOCK_CANCEL, gtk.ResponseType.CANCEL,
                gtk.STOCK_OK, gtk.ResponseType.OK
            )
        )
        filename = widget.get_text()
        if filename is not '':
            dialog.set_filename(filename)
        resp = dialog.run()
        if resp == gtk.ResponseType.OK:
            widget.set_text(dialog.get_filename())
            self.set_focus(widget)
        dialog.destroy()

    def set_calendar_settings(self, name, setting, value):
        for i in range(len(self.settings['calendars'])):
            if self.settings['calendars'][i]['name'] == name:
                self.settings['calendars'][i][setting] = value
                break


if __name__ == '__main__':
    aparser = argparse.ArgumentParser(description='An agenda for your menubar')
    aparser.add_argument(
        'settings',
        nargs='?',
        default=unifiedagenda.CONFIG_PATH,
        help='Path in which the settings file `settings.json` resides. If ' +
             'omitted, `~/.config/io.zjp.unifiedagenda/` is used by ' +
             'default. If `$settings/settings.json` does not exist, a ' +
             'default file is created in it\'s place.'
    )
    args = aparser.parse_args()
    indicator = agendaindicator(args)
    indicator.run()
