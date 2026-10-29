"""Finds which Cloudflare WARP route works from this host and whether YouTube serves a video through it (GitHub
Actions diagnostic: python scripts/warp_probe.py <video id>)."""
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

VIDEO = sys.argv[1] if len(sys.argv) > 1 else "IOUExBZgm88"
WORK = Path("/tmp/warp-probe")
WORK.mkdir(exist_ok=True)
TRACE = "https://www.cloudflare.com/cdn-cgi/trace"
ENDPOINTS = ["engage.cloudflareclient.com:2408", "162.159.192.1:2408", "162.159.193.1:2408", "162.159.195.1:2408",
             "162.159.192.1:500", "162.159.192.1:1701", "162.159.192.1:4500", "[2606:4700:d0::a29f:c001]:2408"]


def fetch(url, path):
    if not path.exists():
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        if url.endswith(".tar.gz"):
            import io, tarfile
            with tarfile.open(fileobj=io.BytesIO(r.content)) as t:
                path.write_bytes(t.extractfile(next(m for m in t.getmembers() if m.name.endswith(path.name))).read())
        else:
            path.write_bytes(r.content)
        path.chmod(0o755)


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return p.returncode, (p.stdout + p.stderr).strip()[-600:]


fetch("https://github.com/ViRb3/wgcf/releases/download/v2.3.1/wgcf_2.3.1_linux_amd64", WORK / "wgcf")
fetch("https://github.com/whyvl/wireproxy/releases/download/v1.1.3/wireproxy_linux_amd64.tar.gz", WORK / "wireproxy")
fetch("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp", WORK / "yt-dlp")
print("direct trace:", re.findall(r"^(ip|colo|warp)=.*", requests.get(TRACE, timeout=10).text, re.M))
print("direct yt-dlp:", run([sys.executable, str(WORK / "yt-dlp"), "-j", "--no-warnings", VIDEO], timeout=120)[1][-200:])

for step in (["register", "--accept-tos"], ["generate"]):
    print("wgcf", step[0], run([str(WORK / "wgcf"), *step], cwd=WORK, timeout=60))
profile = (WORK / "wgcf-profile.conf").read_text()
print("profile endpoint:", re.findall(r"Endpoint.*", profile))

for i, ep in enumerate(ENDPOINTS):
    port = 25400 + i
    (WORK / f"p{i}.conf").write_text(re.sub(r"Endpoint\s*=.*", f"Endpoint = {ep}", profile))
    (WORK / f"w{i}.conf").write_text(f"WGConfig = {WORK / f'p{i}.conf'}\n\n[http]\nBindAddress = 127.0.0.1:{port}\n")
    log = open(WORK / f"w{i}.log", "w")
    proc = subprocess.Popen([str(WORK / "wireproxy"), "-c", str(WORK / f"w{i}.conf")], stdout=log, stderr=log)
    url, ok = f"http://127.0.0.1:{port}", None
    for _ in range(15):
        time.sleep(1)
        try:
            t = requests.get(TRACE, proxies={"https": url}, timeout=5).text
            if "warp=on" in t:
                ok = re.findall(r"^(?:colo|ip)=.*", t, re.M)
                break
        except requests.RequestException:
            pass
    print(f"\n== {ep}: {'CONNECTED ' + str(ok) if ok else 'no connection'}")
    if ok:
        code, out = run([sys.executable, str(WORK / "yt-dlp"), "--proxy", url, "-j", "--no-warnings", VIDEO], timeout=150)
        print("   yt-dlp through WARP:", "OK, formats served" if code == 0 else out[-250:])
    else:
        print("   wireproxy log:", (WORK / f"w{i}.log").read_text()[-400:])
    proc.kill()
    proc.wait()
