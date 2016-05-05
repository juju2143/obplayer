#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Copyright 2012-2015 OpenBroadcaster, Inc.

This file is part of OpenBroadcaster Player.

OpenBroadcaster Player is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

OpenBroadcaster Player is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with OpenBroadcaster Player.  If not, see <http://www.gnu.org/licenses/>.
"""

import obplayer

import socket
import os
import sys
import time
import signal
import subprocess


from obplayer.httpadmin import httpserver


class ObHTTPAdmin (httpserver.ObHTTPServer):
    def __init__(self):
        self.root = 'obplayer/httpadmin/http'

        self.username = obplayer.Config.setting('http_admin_username')
        self.password = obplayer.Config.setting('http_admin_password')
        self.readonly_username = obplayer.Config.setting('http_readonly_username')
        self.readonly_password = obplayer.Config.setting('http_readonly_password')
        self.readonly_allow_restart = obplayer.Config.setting('http_readonly_allow_restart')
        self.title = obplayer.Config.setting('http_admin_title')

        sslenable = obplayer.Config.setting('http_admin_secure')
        sslcert = obplayer.Config.setting('http_admin_sslcert')

        server_address = ('', obplayer.Config.setting('http_admin_port'))  # (address, port)

        httpserver.ObHTTPServer.__init__(self, server_address, sslcert if sslenable else None)

        sa = self.socket.getsockname()
        obplayer.Log.log('serving http(s) on port ' + str(sa[1]), 'admin')

        """
        if path ==   "/status_info":
        elif path == "/alerts/list":
        elif path == '/strings':
        elif path == '/command/restart':
        elif path == '/command/fstoggle':
        if path ==   "/save":
        elif path == '/import_settings':
        elif path == '/export_settings':
        elif path == "/update_player":
        elif path == "/update_check":
        elif path == "/toggle_scheduler":
        elif path == "/alerts/inject_test":
        elif path == "/alerts/cancel":
        """

    def log(self, message):
        if not "POST /status_info" in message and not "POST /alerts/list" in message:
            obplayer.Log.log(message, 'debug')

    def form_item_selected(self, setting, value):
        if obplayer.Config.setting(setting, True) == value:
            return ' selected="selected"'
        else:
            return ''

    def form_item_checked(self, setting):
        if obplayer.Config.setting(setting, True):
            return ' checked="checked"'
        else:
            return ''

    def fullscreen_status(self):
        if obplayer.Config.headless:
            return 'N/A'
        elif obplayer.Gui.gui_window_fullscreen:
            return 'On'
        else:
            return 'Off'

    def handle_post(self, path, postvars, access):
        error = None

        if path == "/status_info":
            proc = subprocess.Popen([ "uptime", "-p" ], stdout=subprocess.PIPE)
            (uptime, _) = proc.communicate()

            requests = obplayer.Player.get_requests()
            select_keys = [ 'media_type', 'end_time', 'filename', 'duration', 'media_id', 'order_num', 'artist', 'title' ]

            data = { }
            data['time'] = time.time()
            data['uptime'] = uptime.decode('utf-8')
            for stream in requests.keys():
                data[stream] = { key: requests[stream][key] for key in requests[stream].keys() if key in select_keys }
            data['audio_levels'] = obplayer.Player.get_audio_levels()
            if hasattr(obplayer, 'scheduler'):
                data['show'] = obplayer.Scheduler.get_show_info()
            data['logs'] = obplayer.Log.get_log()
            return data

        elif path == "/alerts/list":
            if hasattr(obplayer, 'alerts'):
                return obplayer.alerts.Processor.get_alerts()
            return { 'status' : False }

        elif path == '/strings':
            strings = { '': { } }

            self.load_strings('default', strings)
            self.load_strings(obplayer.Config.setting('http_admin_language'), strings)
            return strings

        elif path == '/command/restart':
            if not self.readonly_allow_restart and not access:
                return { 'status' : False, 'error' : "permissions-error-guest" }
            if 'extra' in postvars:
                if postvars['extra'][0] == 'defaults':
                    os.remove(obplayer.ObData.get_datadir() + '/settings.db')
                if postvars['extra'][0] == 'hard' or postvars['extra'][0] == 'defaults':
                    obplayer.Main.exit_code = 37
            os.kill(os.getpid(), signal.SIGINT)
            return { 'status' : True }

        elif path == '/command/fstoggle':
            if not self.readonly_allow_restart and not access:
                return { 'status' : False, 'error' : "permissions-error-guest", 'fullscreen' : 'N/A' }

            if obplayer.Config.headless:
                return { 'status' : False, 'fullscreen' : 'N/A' }
            else:
                obplayer.Gui.fullscreen_toggle(None)
                return { 'status' : True, 'fullscreen' : 'On' if obplayer.Gui.gui_window_fullscreen else 'Off' }

        else:
            if not access:
                return { 'status' : False, 'error' : "permissions-error-guest" }

            if path == "/save":
                # run through each setting and make sure it's valid. if not, complain.
                for key in postvars:
                    setting_name = key
                    setting_value = postvars[key][0]

                    error = obplayer.Config.validate_setting(setting_name, setting_value)

                    if error != None:
                        return { 'status' : False, 'error' : error }

                # we didn't get an errors on validate, so update each setting now.
                settings = { key: value[0] for (key, value) in postvars.items() }
                obplayer.Config.save_settings(settings)

                return { 'status' : True }

            elif path == '/import_settings':
                content = postvars.getvalue('importfile').decode('utf-8')

                errors = ''
                settings = { }
                for line in content.split('\n'):
                    (name, _, value) = line.strip().partition(':')
                    name = name.strip()
                    if not name:
                        continue

                    error = obplayer.Config.validate_setting(name, value)
                    if error:
                        errors += error + '<br/>'
                    else:
                        settings[name] = value
                        obplayer.Log.log("importing setting '{0}': '{1}'".format(name, value), 'config')

                if errors:
                    return { 'status' : False, 'error' : errors }

                obplayer.Config.save_settings(settings)
                return { 'status' : True, 'notice' : "settings-imported-success" }

            elif path == '/export_settings':
                settings = ''
                for (name, value) in sorted(obplayer.Config.list_settings(hidepasswords=True).items()):
                    settings += "{0}:{1}\n".format(name, value if type(value) != bool else int(value))

                res = httpserver.Response()
                res.add_header('Content-Disposition', 'attachment; filename=obsettings.txt')
                res.send_content('text/plain', settings)
                return res

            elif path == "/update_player":
                srcpath = os.path.dirname(os.path.dirname(obplayer.__file__))
                proc = subprocess.Popen('cd "' + srcpath + '" && git pull', stdout=subprocess.PIPE, shell=True)
                (output, _) = proc.communicate()
                return { 'output': output.decode('utf-8') }

            elif path == "/update_check":
                srcpath = os.path.dirname(os.path.dirname(obplayer.__file__))
                branch = subprocess.Popen('cd "{0}" && git branch'.format(srcpath), stdout=subprocess.PIPE, shell=True)
                (output, _) = branch.communicate()
                branchname = 'master'
                for name in output.decode('utf-8').split('\n'):
                    if name.startswith('*'):
                        branchname = name.strip('* ')
                        break

                diff = subprocess.Popen('cd "{0}" && git fetch && git diff origin/{1} --quiet'.format(srcpath, branchname), stdout=subprocess.PIPE, shell=True)
                (output, _) = diff.communicate()

                version = subprocess.Popen('cd "{0}" && git show origin/{1}:VERSION'.format(srcpath, branchname), stdout=subprocess.PIPE, shell=True)
                (output, _) = version.communicate()
                return { 'available': False if diff.returncode == 0 else True, 'version': output.decode('utf-8') }

            elif path == "/toggle_scheduler":
                ctrl = obplayer.Scheduler.ctrl
                if ctrl.enabled:
                    ctrl.disable()
                else:
                    ctrl.enable()
                return { 'enabled': ctrl.enabled }

            elif path == "/alerts/inject_test":
                if hasattr(obplayer, 'alerts'):
                    obplayer.alerts.Processor.inject_alert(postvars['alert'][0])
                    return { 'status' : True }
                return { 'status' : False, 'error' : "alerts-disabled-error" }

            elif path == "/alerts/cancel":
                if hasattr(obplayer, 'alerts'):
                    for identifier in postvars['identifier[]']:
                        obplayer.alerts.Processor.cancel_alert(identifier)
                    return { 'status' : True }
                return { 'status' : False, 'error' : "alerts-disabled-error" }


    @staticmethod
    def load_strings(lang, strings):
        namespace = ''
        for (dirname, dirnames, filenames) in os.walk(os.path.join('obplayer/httpadmin/strings', lang)):
            for filename in filenames:
                if filename.endswith('.txt'):
                    with open(os.path.join(dirname, filename), 'rb') as f:
                        while True:
                            line = f.readline()
                            if not line:
                                break
                            if line.startswith(b'\xEF\xBB\xBF'):
                                line = line[3:]
                            (name, _, text) = line.decode('utf-8').partition(':')
                            (name, text) = (name.strip(), text.strip())
                            if name:
                                if text:
                                    strings[namespace][name] = text
                                else:
                                    namespace = name
                                    strings[namespace] = { }
        return strings
