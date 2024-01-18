from flask import Flask, request, jsonify
import os
import shlex
import subprocess
import base64
import logging
import secrets
import time

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Flask app initialization
app = Flask(__name__)

# Set environment flag of MAX_EXECUTABLE, MAX_DATA_SIZE
runtime_version = "google-cloud-function:2.0.4"

def get_env(env, flag):
    if flag not in env:
        raise Exception(flag + " is missing")
    return int(env[flag])

def success(returncode, stdout, stderr, err):
    return jsonify({
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "err": err,
        "version": runtime_version,
    }), 200

def bad_request(err):
    return jsonify({"error": err}), 400

@app.route('/', methods=['POST'])
def execute():
    env = os.environ.copy()

    MAX_EXECUTABLE = get_env(env, "MAX_EXECUTABLE")
    MAX_DATA_SIZE = get_env(env, "MAX_DATA_SIZE")

    request_json = request.get_json(force=True)
    if "executable" not in request_json:
        return bad_request("Missing executable value")
    executable = base64.b64decode(request_json["executable"])
    if len(executable) > MAX_EXECUTABLE:
        return bad_request("Executable exceeds max size")
    if "calldata" not in request_json:
        return bad_request("Missing calldata value")
    if len(request_json["calldata"]) > MAX_DATA_SIZE:
        return bad_request("Calldata exceeds max size")
    if "timeout" not in request_json:
        return bad_request("Missing timeout value")
    try:
        timeout = int(request_json["timeout"])
    except ValueError:
        return bad_request("Timeout format invalid")
    unique_token = secrets.token_hex(15)
    path = '/tmp/execute-%s.sh' % unique_token
    with open(path, "w") as f:
        f.write(executable.decode())

    os.chmod(path, 0o775)
    try:
        env = os.environ.copy()
        for key, value in request_json.get("env", {}).items():
            env[key] = value

        time.sleep(0.002)

        proc = subprocess.Popen(
            [path] + shlex.split(request_json["calldata"]),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        proc.wait(timeout=(timeout / 1000))
        returncode = proc.returncode
        stdout = proc.stdout.read(MAX_DATA_SIZE).decode()
        stderr = proc.stderr.read(MAX_DATA_SIZE).decode()
        if returncode != 0:
            app.logger.error(stderr)
        return success(returncode, stdout, stderr, "")
    except OSError as err:
        app.logger.error(err)
        return success(126, "", "", "Execution fail")
    except subprocess.TimeoutExpired as err:
        app.logger.error(err)
        return success(111, "", "", "Execution time limit exceeded")

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
