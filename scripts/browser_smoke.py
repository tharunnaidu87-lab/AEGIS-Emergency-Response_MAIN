"""Headless Chrome smoke test through CDP; profile and artifacts stay in the project."""
import base64
import json
import os
import subprocess
import time
import uuid
import sys
import urllib.request
from pathlib import Path
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".cache" / "verification"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


class Browser:
    def __init__(self, fake_media=False):
        self.events = []
        import socket
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            self.port = port_socket.getsockname()[1]
        self.counter = 0
        profile = ROOT / ".cache" / ("browser-profile-" + uuid.uuid4().hex[:8])
        environment = dict(os.environ, TEMP=str(ROOT / ".cache" / "tmp"), TMP=str(ROOT / ".cache" / "tmp"))
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.log = (ARTIFACTS / (profile.name + ".log")).open("w", encoding="utf-8")
        self.process = subprocess.Popen([chrome, "--headless=new", "--no-sandbox", "--disable-gpu-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows", "--disable-component-update", "--disable-breakpad",
            "--disable-crash-reporter", "--remote-debugging-port=" + str(self.port),
            "--user-data-dir=" + str(profile), "--disk-cache-dir=" + str(profile / "cache"),
            "--crash-dumps-dir=" + str(profile / "crashes"), "--window-size=1440,1000", "about:blank"] +
            (["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] if fake_media else []),
            cwd=ROOT, env=environment, stdout=self.log, stderr=self.log, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.time() + 25
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=2) as response:
                    targets = json.load(response)
                target = next(t for t in targets if t["type"] == "page")
                self.target_id = target["id"]
                self.socket = connect(target["webSocketDebuggerUrl"], open_timeout=5, max_size=20_000_000, max_queue=None, ping_interval=None, close_timeout=2, legacy=True)
                break
            except Exception:
                if time.time() > deadline:
                    self.close()
                    raise
                time.sleep(.2)
        self.send("Runtime.enable")
        self.send("Page.enable")
        self.send("Log.enable")
        self.send("Network.enable")
        # Keep UI regression deterministic when public map services are unreachable.
        # The application must exercise its honest offline-map/routing fallback.
        self.send("Network.setBlockedURLs", urls=["https://*.tile.openstreetmap.org/*", "https://tile.openstreetmap.org/*", "https://router.project-osrm.org/*"])
        self.send("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)

    def service_worker_session(self):
        if not hasattr(self, 'browser_socket'):
            with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json/version', timeout=5) as response:
                endpoint = json.load(response)['webSocketDebuggerUrl']
            self.browser_socket = connect(endpoint, open_timeout=5, max_size=20_000_000, max_queue=None, ping_interval=None, close_timeout=2, legacy=True)
        context = self.send('Target.getTargetInfo', targetId=self.target_id)['targetInfo'].get('browserContextId')
        targets = self.send('Target.getTargets')['targetInfos']
        worker = next(t for t in targets if t['type'] == 'service_worker' and t.get('browserContextId') == context)
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=5) as response:
            endpoint = next(t['webSocketDebuggerUrl'] for t in json.load(response) if t['id'] == worker['targetId'])
        session = Browser.__new__(Browser); session.events = []; session.counter = 0
        session.socket = connect(endpoint, open_timeout=5, max_size=20_000_000, max_queue=None, ping_interval=None, close_timeout=2, legacy=True)
        session.send('Network.enable')
        return session

    def isolated(self):
        if not hasattr(self, 'browser_socket'):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=5) as response:
                endpoint = json.load(response)['webSocketDebuggerUrl']
            self.browser_socket = connect(endpoint, open_timeout=5, max_size=20_000_000, max_queue=None, ping_interval=None, close_timeout=2, legacy=True)
        context = self.send("Target.createBrowserContext")["browserContextId"]
        target = self.send("Target.createTarget", url="about:blank", browserContextId=context)["targetId"]
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=5) as response:
            targets = json.load(response)
        endpoint = next(t["webSocketDebuggerUrl"] for t in targets if t["id"] == target)
        child = Browser.__new__(Browser)
        child.events = []; child.counter = 0; child.context = context
        child.socket = connect(endpoint, open_timeout=5, max_size=20_000_000, max_queue=None, ping_interval=None, close_timeout=2, legacy=True)
        for domain in ["Runtime", "Page", "Log", "Network"]:
            child.send(domain + ".enable")
        child.send("Network.setBlockedURLs", urls=["https://*.tile.openstreetmap.org/*", "https://tile.openstreetmap.org/*", "https://router.project-osrm.org/*"])
        child.send("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
        return child

    def send(self, method, **params):
        self.counter += 1
        identifier = self.counter
        channel = self.browser_socket if method.startswith("Target.") and hasattr(self, "browser_socket") else self.socket
        channel.send(json.dumps(dict(id=identifier, method=method, params=params)))
        deadline = time.monotonic() + 35
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("CDP command timed out: " + method)
            message = json.loads(channel.recv(timeout=remaining))
            if message.get("id") == identifier:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression):
        response = self.send("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if response.get("exceptionDetails"):
            raise RuntimeError(response["exceptionDetails"])
        return response.get("result", {}).get("value")

    def wait(self, expression, timeout=25):
        deadline = time.time() + timeout
        while time.time() < deadline:
            # A selector may be absent between navigation and React's first render.
            # Retry that assertion; actual application runtime exceptions remain logged.
            condition = "(() => { try { return Boolean(document.body) && (" + expression + "); } catch(e) { if(e instanceof TypeError) return false; throw e; } })()"
            if self.evaluate(condition):
                return
            time.sleep(.15)
        raise AssertionError("Browser timed out: " + expression)

    def navigate(self, url):
        # Observe the committed document rather than blocking on Chrome's navigation
        # acknowledgement (which may arrive late while a service worker is active).
        self.counter += 1
        self.socket.send(json.dumps(dict(id=self.counter, method="Page.navigate", params={"url": url})))
        target = "location.href === " + json.dumps(url)
        if url.endswith(('/simulate', '/relocation')):
            target = "(" + target + " || location.pathname === '/command')"
        self.wait(target + " && document.readyState === 'complete'")

    def click(self, text):
        expression = """(() => { const e=[...document.querySelectorAll('button,a')].find(e=>e.textContent.trim()===%s); if(!e) throw Error('Missing action'); if(e.disabled) throw Error('Disabled action'); e.click(); return true; })()""" % json.dumps(text)
        return self.evaluate(expression)

    def screenshot(self, name):
        data = self.send("Page.captureScreenshot", format="png", captureBeyondViewport=False)["data"]
        (ARTIFACTS / (name + ".png")).write_bytes(base64.b64decode(data))

    def close(self):
        if hasattr(self, "socket"):
            try:
                self.send("Browser.close")
            except Exception:
                pass
            self.socket.close()
        if hasattr(self, "browser_socket"):
            self.browser_socket.close()
        if hasattr(self, "process"):
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        if hasattr(self, "log"):
            self.log.close()


def main(extra_flow=None, run_core=True, backend_module="main:app", fake_media=False, production=False):
    import uuid
    servers = []
    logs = []
    browser = None
    env = dict(os.environ, PYTHONUTF8="1", AEGIS_DB_PATH=".cache/browser-" + uuid.uuid4().hex[:8] + ".sqlite",
               AEGIS_BACKEND_URL="http://127.0.0.1:8002", PYTHONDONTWRITEBYTECODE="1",
               TEMP=str(ROOT / ".cache" / "tmp"), TMP=str(ROOT / ".cache" / "tmp"),
               AEGIS_COMMAND_USERNAME="demo-command", AEGIS_COMMAND_PASSWORD="AEGIS-demo-only", AEGIS_COMMAND_AUTH_SECRET="isolated-browser-test-secret",
               AEGIS_RESPONDER_ACCOUNTS=json.dumps({r["id"]: "AEGIS-demo-only" for r in json.loads((ROOT / 'data/resources.json').read_text())}),
               npm_config_cache=str(ROOT / ".cache" / "npm"), SARVAM_API_KEY="", NVIDIA_API_KEY="")
    commands = [
        [str(ROOT / "backend/.venv/Scripts/python.exe"), "-B", "-m", "uvicorn", backend_module, "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8002"],
        [r"C:\Program Files\nodejs\node.exe", str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5174", "--strictPort"],
    ]
    if production:
        commands[1].insert(2, "preview")
    try:
        for index, command in enumerate(commands):
            log = (ARTIFACTS / ("server-" + str(index) + ".log")).open("w", encoding="utf-8")
            logs.append(log)
            servers.append(subprocess.Popen(command, cwd=ROOT if index == 0 else ROOT / "frontend",
                env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
        for url in ["http://127.0.0.1:8002/health", "http://127.0.0.1:5174/report"]:
            deadline = time.time() + 25
            while True:
                try:
                    with urllib.request.urlopen(url, timeout=2) as r:
                        assert r.status == 200
                    break
                except Exception:
                    if time.time() > deadline:
                        raise
                    time.sleep(.2)
        if any(server.poll() is not None for server in servers):
            raise RuntimeError("A test server exited; refusing to use an unrelated server on these ports.")
        browser = Browser(fake_media=fake_media)
        base = "http://127.0.0.1:5174"
        report_id, route_status, scenario_text = None, "NOT_EXERCISED", ""
        if run_core:
            browser.navigate(base + "/command")
            browser.wait("document.body.innerText.includes('OPS / STANDBY')")
            assert browser.evaluate("document.querySelectorAll('canvas').length === 0")
            print("PASS command standby without a preloaded incident", flush=True)
            browser.navigate(base + "/report")
            browser.wait("!!document.querySelector('.demo-fill')")
            browser.screenshot("citizen-desktop")
            browser.click("FILL FLOOD DEMO SCENARIO")
            browser.click("SEND EMERGENCY REPORT")
            browser.wait("location.pathname.startsWith('/track/') && document.body.innerText.includes('TRACK MY REPORT')")
            report_id = browser.evaluate("location.pathname.split('/').at(-1)")
            print("PASS report submission and persisted receipt", report_id, flush=True)
            browser.click("TRACK MY REPORT")
            browser.wait("document.body.innerText.includes('BACKEND ANALYSIS RECEIVED')")
            assert browser.evaluate("new URLSearchParams(location.search).get('report')") == report_id
            # Cold dev-module transforms can be slow on a synced Windows workspace.
            browser.wait("document.querySelectorAll('.operation-map-marker').length >= 4", timeout=60)
            browser.evaluate("window.testCanvas=document.querySelector('canvas')")
            browser.screenshot("command-desktop")
            print("PASS selected incident, pipeline and independent map layers", flush=True)
            browser.click("ACKNOWLEDGE")
            browser.wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='DISPATCH RECOMMENDED UNITS' && !b.disabled)")
            browser.click("DISPATCH RECOMMENDED UNITS")
            browser.wait("document.querySelectorAll('.aegis-resource-marker').length >= 4")
            browser.wait("!document.querySelector('.route-status-panel').innerText.includes('CALCULATING ROAD ROUTES')", timeout=20)
            route_status = browser.evaluate("document.querySelector('.route-panel-heading strong').innerText")
            print("PASS dispatch and routing: " + route_status, flush=True)
            browser.click("SIMULATE BLOCKED ROAD")
            browser.wait("document.querySelector('.route-status-panel').innerText.toLowerCase().includes('simulated blocked') || document.querySelector('.route-status-panel').innerText.includes('cannot be evaluated')")
            browser.click("START DEMO MOVEMENT")
            browser.wait("[...document.querySelectorAll('[data-resource-id]')].some(e => Number(e.dataset.progress) > 0.01)")
            browser.evaluate("window.testMarker=document.querySelector('[data-resource-id]'); window.firstProgress=Number(testMarker.dataset.progress);")
            browser.wait("Number(testMarker.dataset.progress) > firstProgress + .03")
            assert browser.evaluate("testMarker === document.querySelector('[data-resource-id]') && testCanvas === document.querySelector('canvas')")
            browser.evaluate("document.querySelector('.operation-map').scrollIntoView(); window.scrollBy(0,-80)")
            browser.screenshot("moving-units")
            print("PASS route-following movement; marker and canvas identity stable", flush=True)
            browser.wait("document.querySelectorAll('[data-resource-id]').length >= 4 && [...document.querySelectorAll('[data-resource-id]')].every(e=>Number(e.dataset.progress)>=.999)", timeout=60)
            browser.wait("document.body.innerText.includes('ON_SCENE')", timeout=10)
            stored = browser.evaluate("(async()=> (await (await fetch('/api/reports/" + report_id + "')).json()).report)()")
            print("PASS simulated arrival synchronized to backend", flush=True)

            def tab(label):
                browser.evaluate("(()=>{const b=[...document.querySelectorAll('.command-module-tabs button')].find(b=>b.textContent.includes(" + json.dumps(label) + ")); if(!b)throw Error('Missing tab');b.click()})()")

            tab("WHAT-IF")
            browser.wait("!!document.querySelector('[aria-label=\"Shelter capacity retained\"]')")
            for label in ["Shelter capacity retained", "Hospital capacity retained"]:
                browser.evaluate("(()=>{const e=document.querySelector('[aria-label=" + json.dumps(label) + "]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'0');e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()")
            browser.click("RUN WHAT-IF SCENARIO")
            browser.wait("[...document.querySelectorAll('.scenario-result')].at(-1).innerText.includes('No safe hospital available')")
            scenario_text = browser.evaluate("[...document.querySelectorAll('.scenario-result')].at(-1).innerText")
            assert "0 / " in scenario_text
            after = browser.evaluate("(async()=> (await (await fetch('/api/reports/" + report_id + "')).json()).report)()")
            assert after == stored, "What-if must not mutate the saved incident"
            browser.evaluate("document.querySelector('.integrated-command-module').scrollIntoView(); window.scrollBy(0,-80)")
            browser.screenshot("what-if")
            print("PASS shelter/hospital What-If recalculation; saved operation unchanged", flush=True)

            tab("PREDICTIVE")
            browser.wait("document.body.innerText.includes('FUTURE RESOURCE DEMAND')")
            browser.click("RECALCULATE WITH SHELTER CLOSED")
            browser.wait("document.querySelector('.scenario-stress').innerText.includes('people allocated')")
            tab("INTELLIGENCE")
            browser.wait("document.body.innerText.includes('PRE-POSITION SPARE RESOURCES')")
            tab("RELOCATION")
            browser.wait("document.body.innerText.includes('POPULATION ALLOCATION')")
            tab("AUDIT")
            browser.wait("document.body.innerText.includes('ASSIGNMENT_CREATED') || document.body.innerText.includes('assigned.')")
            print("PASS prediction, spare staging, shelter closure, relocation and audit modules", flush=True)

            assignments = browser.evaluate("(async()=> (await (await fetch('/api/assignments')).json()).assignments)()")
            unit = assignments[0]["resource_id"]
            browser.send("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=1, mobile=True)
            browser.navigate(base + "/responder?unit=" + unit)
            browser.wait("document.body.innerText.includes('CURRENT MISSION') && document.body.innerText.includes('ON_SCENE')")
            assert browser.evaluate("document.querySelector('.responder-detail-grid')?.innerText.includes('0 MIN') || [...document.querySelectorAll('strong')].some(e => e.textContent.trim() === '0 MIN')")
            browser.screenshot("responder-mobile")
            assert browser.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "Responder horizontal overflow"
            browser.click("RESOLVED")
            browser.wait("document.body.innerText.includes('UNIT AVAILABLE')")
            print("PASS mobile responder and persisted completion status", flush=True)
            browser.navigate(base + "/report")
            browser.wait("!!document.querySelector('.demo-fill')")
            browser.screenshot("citizen-mobile")
            assert browser.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "Citizen horizontal overflow"
            print("PASS mobile citizen layout", flush=True)
            browser.navigate(base + "/command?report=DOES-NOT-EXIST")
            browser.wait("document.body.innerText.includes('Selected report is unavailable')")
            assert browser.evaluate("document.querySelectorAll('canvas').length === 0")
            print("PASS missing report does not select unrelated incidents", flush=True)
            for route in ["/sms", "/call", "/responder", "/simulate", "/relocation"]:
                browser.navigate(base + route)
                browser.wait("document.readyState === 'complete' && document.body.innerText.length > 40")
                assert not browser.evaluate("document.body.innerText.includes('AEGIS view could not load')")
            browser.navigate(base + "/command?report=" + report_id)
            browser.wait("document.body.innerText.includes('" + report_id + "')")
            print("PASS legacy URLs and report refresh persistence", flush=True)
        if extra_flow:
            extra_flow(browser, base)
        exceptions = [e for e in browser.events if e.get("method") == "Runtime.exceptionThrown"]
        (ARTIFACTS / "browser-events.json").write_text(json.dumps(browser.events, indent=2), encoding="utf-8")
        (ARTIFACTS / "browser-result.json").write_text(json.dumps({"passed": not exceptions, "core_flow": run_core, "report_id": report_id,
            "routing": route_status, "runtime_exceptions": exceptions, "scenario_text": scenario_text}, indent=2), encoding="utf-8")
        assert not exceptions, exceptions
        print("PASS zero uncaught browser runtime exceptions", flush=True)
    except Exception:
        if browser:
            browser.screenshot("failure")
            (ARTIFACTS / "browser-failure-events.json").write_text(json.dumps(browser.events, indent=2), encoding="utf-8")
            print(browser.evaluate("document.body.innerText.slice(0,12000)"), flush=True)
        raise
    finally:
        if browser:
            browser.close()
        for server in servers:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        for log in logs:
            log.close()



if __name__ == "__main__":
    main(production='--production' in sys.argv)
