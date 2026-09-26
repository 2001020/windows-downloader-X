"""Run aria2c in RPC mode and drive it over JSON-RPC on localhost."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .net import USER_AGENT, ca_file_for_aria2

EXE_NAME = "aria2c.exe" if sys.platform.startswith("win") else "aria2c"


def resource_dir():
    """Directory holding bundled files (PyInstaller) or the source tree."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def find_aria2c():
    candidates = []
    env = os.environ.get("WINISO_ARIA2C")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(resource_dir(), "aria2", EXE_NAME))
    # Development checkouts: <platform>/build/aria2/aria2c produced by the build scripts.
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    plat = "windows" if sys.platform.startswith("win") else "macos" if sys.platform == "darwin" else "linux"
    candidates.append(os.path.join(repo, plat, "build", "aria2", EXE_NAME))
    for path in candidates:
        if path and os.path.isfile(path):
            if not sys.platform.startswith("win") and not os.access(path, os.X_OK):
                try:
                    os.chmod(path, 0o755)
                except OSError:
                    continue
            return path
    return shutil.which("aria2c")


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Aria2Error(Exception):
    pass


class Aria2:
    def __init__(self, exe=None):
        self.exe = exe or find_aria2c()
        if not self.exe:
            raise Aria2Error("aria2c not found")
        self.proc = None
        self.port = None
        self.secret = None
        self.log_path = ""
        # The RPC endpoint is local; never send it through a system proxy.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def version(self):
        out = subprocess.run([self.exe, "--version"], capture_output=True, text=True, timeout=15,
                             **_hidden_window()).stdout
        return out.splitlines()[0] if out else ""

    def start(self):
        self.port = free_port()
        self.secret = secrets.token_hex(16)
        cmd = [
            self.exe,
            "--enable-rpc=true",
            "--rpc-listen-all=false",
            "--rpc-listen-port=%d" % self.port,
            "--rpc-secret=%s" % self.secret,
            "--stop-with-process=%d" % os.getpid(),
            "--check-certificate=true",
            "--console-log-level=warn",
            "--summary-interval=0",
            "--no-conf=true",
            "--daemon=false",
        ]
        ca = ca_file_for_aria2()
        if ca:
            cmd.append("--ca-certificate=%s" % ca)
        # Console output goes to a file: a pipe nobody reads would eventually
        # fill up and stall aria2c in the middle of a long download.
        self.log_path = os.path.join(tempfile.gettempdir(), "winiso-aria2-%d.log" % os.getpid())
        with open(self.log_path, "wb") as log:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                         **_hidden_window())
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise Aria2Error("aria2c exited: %s" % (self.console_output() or self.proc.returncode))
            try:
                self.call("aria2.getVersion")
                return
            except Exception:
                time.sleep(0.2)
        self.stop()
        raise Aria2Error("aria2c RPC did not start")

    def console_output(self):
        if not self.log_path:
            return ""
        try:
            with open(self.log_path, "rb") as f:
                return f.read()[-4000:].decode("utf-8", "replace").strip()
        except OSError:
            return ""

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def call(self, method, *params):
        body = json.dumps({"jsonrpc": "2.0", "id": "winiso", "method": method,
                           "params": ["token:" + self.secret] + list(params)}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/jsonrpc" % self.port, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(req, timeout=10) as resp:
                reply = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                reply = json.loads(e.read().decode())
            except Exception:
                raise Aria2Error("aria2 RPC HTTP %d" % e.code) from e
        if "error" in reply:
            raise Aria2Error(reply["error"].get("message", str(reply["error"])))
        return reply.get("result")

    def add(self, url, directory, filename, connections=16, proxy=None):
        options = {
            "dir": directory,
            "out": filename,
            "continue": "true",
            "split": str(connections),
            "max-connection-per-server": str(connections),
            "min-split-size": "4M",
            "file-allocation": "none",
            "allow-overwrite": "false",
            "auto-file-renaming": "false",
            "max-tries": "20",
            "retry-wait": "3",
            "connect-timeout": "20",
            "timeout": "30",
            "user-agent": USER_AGENT,
            "remote-time": "true",
        }
        # Set explicitly either way: aria2c also honours http(s)_proxy from the
        # environment, and the proxy field in the UI must be what is used.
        for key in ("all-proxy", "http-proxy", "https-proxy"):
            options[key] = proxy or ""
        return self.call("aria2.addUri", [url], options)

    def status(self, gid):
        return self.call("aria2.tellStatus", gid, [
            "status", "totalLength", "completedLength", "downloadSpeed", "connections",
            "errorCode", "errorMessage", "files"])

    def pause(self, gid):
        return self.call("aria2.forcePause", gid)

    def resume(self, gid):
        return self.call("aria2.unpause", gid)

    def remove(self, gid):
        try:
            self.call("aria2.forceRemove", gid)
        except Aria2Error:
            pass
        try:
            self.call("aria2.removeDownloadResult", gid)
        except Aria2Error:
            pass

    def stop(self):
        if not self.proc:
            return
        if self.proc.poll() is None:
            try:
                self.call("aria2.forceShutdown")
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None
        if self.log_path:
            try:
                os.remove(self.log_path)
            except OSError:
                pass


def _hidden_window():
    """Keep aria2c from flashing a console window on Windows."""
    if sys.platform.startswith("win"):
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
