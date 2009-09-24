"""Provides the main application controller."""

import os
import sys
import glob

from PyQt4 import QtGui
from PyQt4 import QtCore

import cola
from cola import core
from cola import utils
from cola import qtutils
from cola import version
from cola import inotify
from cola import difftool
from cola import settings
from cola.qobserver import QObserver
from cola.views import log


class MainController(QObserver):
    """Manage interactions between models and views."""

    def __init__(self, model, view):
        """Initializes the MainController's internal data."""
        QObserver.__init__(self, model, view)

        # Binds model params to their equivalent view widget
        self.add_observables('commitmsg')

        # When a model attribute changes, this runs a specific action
        self.add_actions(global_cola_fontdiff = self.update_diff_font)
        self.add_actions(global_cola_tabwidth = self.update_tab_width)

        self.add_callbacks(#TODO factor out of this class
                           menu_quit = self.quit_app,
                           # TODO move selection into the model
                           #stage_button = self.stage_selected,
                           )
        # Route events here
        view.closeEvent = self.quit_app
        self._init_log_window()
        self.refresh_view('global_cola_fontdiff') # Update the diff font
        self.start_inotify_thread()
        if self.has_inotify():
            self.view.rescan_button.hide()

    def event(self, msg):
        """Overrides event() to handle custom inotify events."""
        if not inotify.AVAILABLE:
            return
        if msg.type() == inotify.INOTIFY_EVENT:
            cola.notifier().broadcast(signals.rescan)
            return True
        else:
            return False

    def tr(self, fortr):
        """Translates strings."""
        return qtutils.tr(fortr)

    def mergetool(self):
        """Launch git-mergetool on a file path."""
        return#TODO
        filename = self.selected_filename(staged=False)
        if not filename or filename not in self.model.unmerged:
            return
        if version.check('mergetool-no-prompt',
                         self.model.git.version().split()[2]):
            utils.fork(['git', 'mergetool', '--no-prompt', '--', filename])
        else:
            utils.fork(['xterm', '-e', 'git', 'mergetool', '--', filename])

    def has_inotify(self):
        """Return True if pyinotify is available."""
        return self.inotify_thread and self.inotify_thread.isRunning()

    def quit_app(self, *args):
        """Save config settings and cleanup inotify threads."""
        if self.model.remember_gui_settings():
            settings.SettingsManager.save_gui_state(self.view)

        # Remove any cola temp files
        pattern = self.model.tmp_file_pattern()
        for filename in glob.glob(pattern):
            os.unlink(filename)

        # Stop inotify threads
        if self.has_inotify():
            self.inotify_thread.set_abort(True)
            self.inotify_thread.quit()
            self.inotify_thread.wait()
        self.view.close()

    def update_diff_font(self):
        """Updates the diff font based on the configured value."""
        qtutils.set_diff_font(qtutils.logger())
        qtutils.set_diff_font(self.view.display_text)
        qtutils.set_diff_font(self.view.commitmsg)
        self.update_tab_width()

    def update_tab_width(self):
        """Implement the variable-tab-width setting."""
        tab_width = self.model.cola_config('tabwidth')
        display_font = self.view.display_text.font()
        space_width = QtGui.QFontMetrics(display_font).width(' ')
        self.view.display_text.setTabStopWidth(tab_width * space_width)

    def _init_log_window(self):
        """Initialize the logging subwindow."""
        branch = self.model.currentbranch
        qtutils.log(0, self.model.git_version +
                    '\ncola version ' + version.version() +
                    '\nCurrent Branch: ' + branch)

    def start_inotify_thread(self):
        """Start an inotify thread if pyinotify is installed."""
        # Do we have inotify?  If not, return.
        # Recommend installing inotify if we're on Linux.
        self.inotify_thread = None
        if not inotify.AVAILABLE:
            if not utils.is_linux():
                return
            msg = self.tr('inotify: disabled\n'
                          'Note: To enable inotify, '
                          'install python-pyinotify.\n')

            if utils.is_debian():
                msg += self.tr('On Debian systems, '
                               'try: sudo apt-get install '
                               'python-pyinotify')
            qtutils.log(0, msg)
            return

        # Start the notification thread
        qtutils.log(0, self.tr('inotify support: enabled'))
        self.inotify_thread = inotify.GitNotifier(self, self.model.git)
        self.inotify_thread.start()
