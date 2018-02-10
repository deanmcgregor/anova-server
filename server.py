from flask import Flask, request, jsonify, abort, make_response
from pycirculate.anova import AnovaController
from threading import Timer
import logging
import json
import os
import sys
import warnings
import datetime

app = Flask(__name__)

ANOVA_MAC_ADDRESS = "20:C3:8F:F6:2C:99"

class RESTAnovaController(AnovaController):
    """
    This version of the Anova Controller will keep a connection open over bluetooth
    until the timeout has been reach.

    NOTE: Only a single BlueTooth connection can be open to the Anova at a time.
    """

    TIMEOUT = 5 * 60 # Keep the connection open for this many seconds.
    TIMEOUT_HEARTBEAT = 20

    def __init__(self, mac_address, connect=True, logger=None):
        self.last_command_at = datetime.datetime.now()
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger()
        AnovaController.__init__(self, mac_address, connect=connect)

    def set_timeout(self, timeout):
        """
        Adjust the timeout period (in seconds).
        """
        self.TIMEOUT = timeout

    def timeout(self, seconds=None):
        """
        Determines whether the Bluetooth connection should be timed out
        based on the timestamp of the last exectuted command.
        """
        if not seconds:
            seconds = self.TIMEOUT
        timeout_at = self.last_command_at + datetime.timedelta(seconds=seconds)
        if datetime.datetime.now() > timeout_at:
            self.close()
            self.logger.info('Timeout bluetooth connection. Last command ran at {0}'.format(self.last_command_at))
        else:
            self._timeout_timer = Timer(self.TIMEOUT_HEARTBEAT, lambda: self.timeout())
            self._timeout_timer.setDaemon(True)
            self._timeout_timer.start()
            self.logger.debug('Start connection timeout monitor. Will idle timeout in {0} seconds.'.format(
                (timeout_at - datetime.datetime.now()).total_seconds())) 

    def connect(self):
        super(RESTAnovaController, self).connect()
        self.last_command_at = datetime.datetime.now()
        self.timeout()

    def close(self):
        super(RESTAnovaController, self).close()
        try:
            self._timeout_timer.cancel()
        except AttributeError:
            pass

    def _send_command(self, command):
        if not self.is_connected:
            self.connect()
        self.last_command_at = datetime.datetime.now()
        return super(RESTAnovaController, self)._send_command(command)


# Error handlers

@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': 'Bad request.'}), 400)

@app.errorhandler(404)
def timeout_atnot_found(error):
    return make_response(jsonify({'error': 'Not found.'}), 404)

@app.errorhandler(500)
def server_error(error):
    return make_response(jsonify({'error': 'Server error.'}), 500)

def make_error(status_code, message, sub_code=None, action=None, **kwargs):
    """
    Error with custom message.
    """
    data = {
        'status': status_code,
        'message': message,
    }
    if action:
        data['action'] = action
    if sub_code:
        data['sub_code'] = sub_code
    data.update(kwargs)
    response = jsonify(data)
    response.status_code = status_code
    return response

# REST endpoints

@app.route('/', methods=["GET"])
def index():
    try:
        output = {
            'status' : {
                'temp_unit' : app.anova_controller.read_unit(),
                'current_temp' : app.anova_controller.read_temp(),
                'target_temp' : float(app.anova_controller.read_set_temp()),
                'is_running' : app.anova_controller.anova_status() == 'running'
            }
        }
    except Exception as exc:
        app.logger.error(exc)
        return make_error(500, "{0}: {1}".format(repr(exc), str(exc)))

    return jsonify(output)

@app.route('/', methods=["POST"])
def handle_request():
    try:
        req = request.get_json()
        if type(req) is not dict:
            req = json.loads(req)
        if 'is_running' in req:
            if req["is_running"]:
                app.anova_controller.start_anova()
            else:
                app.anova_controller.stop_anova()
        elif 'target_temp' in req:
            temp = req["target_temp"]
            app.anova_controller.set_temp(int(temp))

    except Exception as exc:
        app.logger.error(exc)
        return make_error(500, "{0}: {1}".format(repr(exc), str(exc)))

    return index() 

class AuthMiddleware(object):
    """
    HTTP Basic Auth wsgi middleware.  Must be used in conjunction with SSL.
    """

    def __init__(self, app, username, password):
        self._app = app
        self._username = username
        self._password = password

    def __call__(self, environ, start_response):
        if self._authenticated(environ.get('HTTP_AUTHORIZATION')):
            return self._app(environ, start_response)
        return self._login(environ, start_response)

    def _authenticated(self, header):
        from base64 import b64decode
        if not header:
            return False
        _, encoded = header.split(None, 1)
        decoded = b64decode(encoded).decode('UTF-8')
        username, password = decoded.split(':', 1)
        return (self._username == username) and (self._password == password)

    def _login(self, environ, start_response):
        start_response('401 Authentication Required',
            [('Content-Type', 'application/json'),
             ('WWW-Authenticate', 'Basic realm="Login"')])
        output = {"error": "Login"}
        return [json.dumps(output)]


def main():
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    app.anova_controller = RESTAnovaController(ANOVA_MAC_ADDRESS, logger=app.logger)

    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    main()
