"""Preserved 2026-08-25 from /tmp/t001i before that scratch dir was purged.
Written for T-001 request *capture*, not generation; T-012 needs a generation
harness and must not assume this one is fit for that without checking whether
pty geometry or timing perturbs a request surface (untested).

Drive the *interactive* (non-print, non-SDK) Claude Code CLI under a pty.

Mirrors drive2.mjs's env hygiene exactly: loopback ANTHROPIC_BASE_URL, dummy
API key, every real auth path deleted from the child env.
Types one short prompt, waits for the loopback capture, then terminates.
"""
import os, sys, pty, select, signal, time, fcntl, termios, struct, errno

CWD   = os.environ["CAP_CWD"]
BIN   = os.environ["CAP_BIN"]
MODEL = os.environ["CAP_MODEL"]
PORT  = os.environ["CAP_PORT"]
CFG   = os.environ["CAP_CFG"]
OUTDIR= os.environ["CAP_OUTDIR"]
LOG   = os.environ["CAP_TTYLOG"]
PROMPT= os.environ.get("CAP_PROMPT", "ping")
EXTRA = [a for a in os.environ.get("CAP_EXTRA_ARGS", "").split() if a]
DEADLINE = float(os.environ.get("CAP_DEADLINE", "120"))

env = dict(os.environ)
env["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:%s" % PORT
env["ANTHROPIC_API_KEY"]  = "sk-ant-dummy-capture-not-a-real-key"
for k in ("CLAUDE_CODE_OAUTH_TOKEN","ANTHROPIC_AUTH_TOKEN","ANTHROPIC_API_URL",
          "CLAUDE_CODE_USE_BEDROCK","CLAUDE_CODE_USE_VERTEX","AWS_ACCESS_KEY_ID",
          "AWS_SECRET_ACCESS_KEY","AWS_SESSION_TOKEN","GOOGLE_APPLICATION_CREDENTIALS",
          "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR","CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
          "ANTHROPIC_FEDERATION_RULE_ID","ANTHROPIC_ORGANIZATION_ID",
          "CLAUDECODE","CLAUDE_CODE_ENTRYPOINT","CLAUDE_CODE_SSE_PORT",
          "ANTHROPIC_MODEL","ANTHROPIC_SMALL_FAST_MODEL"):
    env.pop(k, None)
env["DISABLE_TELEMETRY"]="1"; env["DISABLE_ERROR_REPORTING"]="1"
env["DISABLE_AUTOUPDATER"]="1"; env["DISABLE_NON_ESSENTIAL_MODEL_CALLS"]="1"
env["CLAUDE_CONFIG_DIR"]=CFG
env["TERM"]="xterm-256color"; env["COLUMNS"]="120"; env["LINES"]="40"
env["CI"]=""; env.pop("CI", None)

argv = [BIN, "--model", MODEL] + EXTRA

pid, fd = pty.fork()
if pid == 0:
    os.chdir(CWD)
    os.execve(BIN, argv, env)
    os._exit(127)

fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))

log = open(LOG, "wb")
start = time.time()
sent = False
def captured():
    try:
        for f in os.listdir(OUTDIR):
            if f.startswith("req-"):
                return True
    except FileNotFoundError:
        pass
    return False

status = "unknown"
try:
    while True:
        if time.time() - start > DEADLINE:
            status = "deadline"; break
        r, _, _ = select.select([fd], [], [], 0.25)
        if r:
            try:
                data = os.read(fd, 65536)
            except OSError as e:
                if e.errno == errno.EIO:
                    status = "child-exited"; break
                raise
            if not data:
                status = "child-eof"; break
            log.write(data); log.flush()
        # send the prompt once the TUI has had time to mount
        if not sent and time.time() - start > 8:
            os.write(fd, PROMPT.encode())
            time.sleep(0.6)
            os.write(fd, b"\r")
            sent = True
        if sent and captured() and time.time() - start > 12:
            time.sleep(3)          # let any follow-up request land
            status = "captured"; break
finally:
    log.close()
    try: os.kill(pid, signal.SIGTERM)
    except OSError: pass
    time.sleep(0.5)
    try: os.kill(pid, signal.SIGKILL)
    except OSError: pass
    try: os.waitpid(pid, os.WNOHANG)
    except OSError: pass
    os.close(fd)

print("pty_drive status=%s sent=%s elapsed=%.1f" % (status, sent, time.time()-start))
