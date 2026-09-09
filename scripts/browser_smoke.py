"""Headless Chrome smoke test through CDP; profile and artifacts stay in the project."""
import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".cache" / "verification"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


class Browser:
    def __init__(self):
        self.events = []
        self.counter = 0
        profile = ROOT / ".cache" / "browser-profile"
        environment = dict(os.environ, TEMP=str(ROOT / ".cache" / "tmp"), TMP=str(ROOT / ".cache" / "tmp"))
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.log = (ARTIFACTS / "chrome.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen([chrome, "--headless=new", "--no-sandbox", "--disable-gpu-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-component-update", "--disable-breakpad",
            "--disable-crash-reporter", "--remote-debugging-port=9222",
            "--user-data-dir=" + str(profile), "--disk-cache-dir=" + str(profile / "cache"),
            "--crash-dumps-dir=" + str(profile / "crashes"), "--window-size=1440,1000", "about:blank"],
            cwd=ROOT, env=environment, stdout=self.log, stderr=self.log, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.time() + 25
        while True:
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=2) as response:
                    targets = json.load(response)
                target = next(t for t in targets if t["type"] == "page")
                self.socket = connect(target["webSocketDebuggerUrl"], open_timeout=5, max_size=20_000_000, legacy=True)
                break
            except Exception:
                if time.time() > deadline:
                    self.close()
                    raise
                time.sleep(.2)
        self.send("Runtime.enable")
        self.send("Page.enable")
        self.send("Log.enable")
        self.send("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)

    def send(self, method, **params):
        self.counter += 1
        identifier = self.counter
        self.socket.send(json.dumps(dict(id=identifier, method=method, params=params)))
        while True:
            message = json.loads(self.socket.recv(timeout=35))
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
        self.send("Page.navigate", url=url)
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
        if hasattr(self, "process"):
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        if hasattr(self, "log"):
            self.log.close()


def main(extra_flow=None, run_core=True):
    import uuid
    servers = []
    logs = []
    browser = None
    env = dict(os.environ, AEGIS_DB_PATH=".cache/browser-" + uuid.uuid4().hex[:8] + ".sqlite",
               AEGIS_BACKEND_URL="http://127.0.0.1:8002", PYTHONDONTWRITEBYTECODE="1",
               TEMP=str(ROOT / ".cache" / "tmp"), TMP=str(ROOT / ".cache" / "tmp"),
               npm_config_cache=str(ROOT / ".cache" / "npm"))
    commands = [
        [str(ROOT / "backend/.venv/Scripts/python.exe"), "-B", "-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8002"],
        [r"C:\Program Files\nodejs\node.exe", str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5174", "--strictPort"],
    ]
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
        browser = Browser()
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
            browser.wait("document.querySelectorAll('.operation-map-marker').length >= 4")
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
    main()
