# Unified Agenda #

A simple Unity Top Bar widget for displaying iCal events, written in python.

Never fumble with calendar apps again! This widget will display exactly how
much time you have until your next appointment, at a glance. Pull down the menu
to get a full list of the current day's events.

Web calendar sources can be specified by a URL from which they can be fetched,
such as the private address provided by Google Calendar. Prefer to live
off-the-grid? Unified Agenda supports local-only calendars as well: simply point
the path field to your iCal file, and leave the URL field blank.

Don't like something about this widget? Change it! All flavor text and icons can
be modified.

To run the widget, make the script executable with `chmod +x unifiedagenda.py`
and execute with `./unifiedagenda.py`. If you prefer the settings to be stored
somewhere other than `~/.config/io.zjp.unifiedagenda/`, just specify the path
as the first argument: `./unifiedagenda.py [path]`.

## TODO ##

+ <del>Add a preferences menu</del>
+ <del>Customizable settings path</del>
+ Customizable Formatting of Display Text
+ Support for Full-Day and Multi-Day Events
+ Support for events in different timezones
  + Detect current timezone
+ <del>Manual Web Calendar Sync</del>
+ Automatic Web Calendar Sync
  + Customizable Frequency
  + Based on datestamp on calendar file
+ Indication that an event is complete in the menu
+ Notification System
  + Based on VALARM components?
  + Based on customizable rules
+ Customizable Indicator Icon
+ Add Mac OS Support with [rumps](https://github.com/jaredks/rumps)
+ Turn this into a fully-fledged package and sumbit to the PyPi?
+ </del>Basic Functionality</del>
