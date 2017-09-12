#!/usr/bin/env python3
"""Testing AppIndicator python Hooks"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk as gtk
from gi.repository import AppIndicator3 as appind
from gi.repository import Notify as notify
import signal
import threading

APPINDICATOR_ID = 'myappindicator'


def build_menu():
    """Populate the Indicator Menu."""
    menu = gtk.Menu()
    item_quit = gtk.MenuItem('Quit')
    item_quit.connect('activate', quit)
    menu.append(item_quit)
    menu.show_all()
    return menu


def quit(source):
    """Stop the GTK loop."""
    global running
    running = False
    notify.uninit()
    gtk.main_quit()


def update():
    global indicator, n, running
    if running:
        indicator.set_label('Iteration {}'.format(n), 'This is a guide')
        if n % 10 == 0:
            notify.Notification.new('<b>Notification</b>',
                                    'Iteration {}'.format(n),
                                    None
                                    ).show()
        n += 1
        threading.Timer(1, update).start()


def main():
    """Begin the main indicator loop."""
    global indicator, n, running
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    indicator = appind.Indicator.new(APPINDICATOR_ID,
                                     gtk.STOCK_INFO,
                                     appind.IndicatorCategory.SYSTEM_SERVICES
                                     )
    indicator.set_label('testing!', 'This is a guide')
    indicator.set_status(appind.IndicatorStatus.ACTIVE)
    indicator.set_menu(build_menu())
    n = 0
    running = True
    notify.init(APPINDICATOR_ID)
    update()
    gtk.main()


if __name__ == "__main__":
    main()
