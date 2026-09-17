"""Production PWA + three isolated actors. Synthetic microphone; external providers mocked.
Run twice from the validation runner, each with clean server processes/profile/database.
"""
import json
import time
from PIL import Image
from browser_smoke import main, ARTIFACTS, Browser


def fill(browser, selector, value):
    browser.evaluate("""(() => { const e=document.querySelector(%s); if(!e)throw Error('Missing field '+%s);
      const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(e,%s);
      e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); })()""" % (json.dumps(selector), json.dumps(selector), json.dumps(str(value))))


def login(browser, username):
    browser.wait("!!document.querySelector('input[autocomplete=username]')")
    fill(browser, 'input[autocomplete=username]', username)
    fill(browser, 'input[type=password]', 'AEGIS-demo-only')
    browser.evaluate("document.querySelector('form').requestSubmit()")
    browser.wait("!document.querySelector('input[type=password]')")


def api(browser, path):
    return browser.evaluate("(async()=>{const r=await fetch('/api'+%s);return {status:r.status,body:await r.json()}})()" % json.dumps(path))


def confirm_receipt(browser):
    browser.wait("location.pathname.startsWith('/queued/') && document.body.innerText.includes('REPORT SYNCHRONIZED')", timeout=35)
    browser.wait("[...document.querySelectorAll('a')].some(a=>a.textContent==='TRACK MY REPORT')")
    browser.click('TRACK MY REPORT')
    browser.wait("location.pathname.startsWith('/track/') && document.body.innerText.includes('TRACK MY REPORT')")
    return browser.evaluate("location.pathname.split('/').at(-1)")


def verify(browser, base):
    checks = []
    command = Browser()
    responder = Browser()
    actors = [browser, command, responder]

    def passed(name):
        checks.append(name); print('PASS final: ' + name, flush=True)

    def tab(label):
        command.evaluate("[...document.querySelectorAll('.command-module-tabs button')].find(b=>b.textContent.includes(%s)).click()" % json.dumps(label))

    try:
        command.navigate(base + '/command')
        login(command, 'demo-command')
        command.wait("document.body.innerText.includes('OPS / STANDBY')")
        assert api(command, '/reports')['body']['total'] == 0
        assert command.evaluate("document.querySelectorAll('canvas').length===0")
        browser.navigate(base + '/report')
        browser.wait("!!document.querySelector('.sos-button')")
        browser.evaluate("navigator.serviceWorker.ready.then(()=>true)")
        browser.navigate(base + '/report')
        browser.wait("!!navigator.serviceWorker.controller && !!document.querySelector('.sos-button')")
        assert browser.evaluate("sessionStorage.getItem('aegis_command_token')===null")
        assert api(browser, '/reports')['status'] == 401
        passed('Separate citizen and authority sessions; genuine empty standby; installed production shell')

        browser.send('Browser.setPermission', permission={'name': 'geolocation'}, setting='denied', origin=base)
        browser.click('SOS'); browser.wait("document.body.innerText.includes('SOS ACTIVATING')")
        browser.click('CANCEL SOS'); time.sleep(3.2)
        assert api(command, '/distress')['body'] == []
        assert browser.evaluate("location.pathname==='/report'")
        passed('SOS cancellation leaves no server event or navigation')

        photo = ARTIFACTS / 'test-photo.png'
        Image.new('RGB', (160, 120), (40, 120, 65)).save(photo)
        doc = browser.send('DOM.getDocument')['root']['nodeId']
        node = browser.send('DOM.querySelector', nodeId=doc, selector='.photo-picker input[type=file]')['nodeId']
        browser.send('DOM.setFileInputFiles', nodeId=node, files=[str(photo)])
        browser.wait("document.querySelectorAll('.photo-previews img').length===1")
        browser.click('Remove photo 1')
        assert browser.evaluate("document.querySelectorAll('.photo-previews img').length===0")
        browser.send('DOM.setFileInputFiles', nodeId=node, files=[str(photo)])
        browser.wait("document.querySelectorAll('.photo-previews img').length===1")
        passed('Photo gallery selection, browser compression, preview and removal')

        browser.click('FILL FLOOD DEMO SCENARIO')
        offline_worker = browser.service_worker_session()
        offline_worker.send('Network.emulateNetworkConditions', offline=True, latency=0, downloadThroughput=-1, uploadThroughput=-1)
        browser.send('Network.emulateNetworkConditions', offline=True, latency=0, downloadThroughput=-1, uploadThroughput=-1)
        browser.click('SEND EMERGENCY REPORT')
        browser.wait("location.pathname.startsWith('/queued/') && document.body.innerText.includes('REPORT SAVED ON THIS DEVICE')")
        local_id = browser.evaluate("location.pathname.split('/').at(-1)")
        assert api(command, '/reports')['body']['total'] == 0
        browser.navigate(base + '/queued/' + local_id)
        browser.wait("document.body.innerText.includes('REPORT SAVED ON THIS DEVICE')")
        assert browser.evaluate("document.body.innerText.includes('Delivery is not confirmed')")
        passed('Offline report and photo survive a full refresh; no false delivery receipt')
        offline_worker.send('Network.emulateNetworkConditions', offline=False, latency=0, downloadThroughput=-1, uploadThroughput=-1)
        offline_worker.socket.close()
        browser.send('Network.emulateNetworkConditions', offline=False, latency=0, downloadThroughput=-1, uploadThroughput=-1)
        report_id = confirm_receipt(browser)
        assert api(command, '/reports')['body']['total'] == 1
        report = api(browser, '/reports/' + report_id)['body']['report']
        assert len(report['photo_ids']) == 1
        # Resend the exact saved outbox request to model an acknowledged-write/lost-response race.
        retry = browser.evaluate("""(async()=>{const db=await new Promise(r=>{const q=indexedDB.open('aegis-outbox',1);q.onsuccess=()=>r(q.result)});
          const items=await new Promise(r=>{const q=db.transaction('queue').objectStore('queue').getAll();q.onsuccess=()=>r(q.result)});db.close();
          const item=items.find(i=>i.id===%s); return (await (await fetch('/api/reports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item.payload)})).json()).report.id;})()""" % json.dumps(local_id))
        assert retry == report_id and api(command, '/reports')['body']['total'] == 1
        passed('Automatic reconnect, private tracking receipt and server idempotency prevent duplicates')

        command.navigate(base + '/command?report=' + report_id)
        command.wait("document.body.innerText.includes('BACKEND ANALYSIS RECEIVED')")
        command.wait("document.querySelectorAll('.operation-map-marker').length>=4", timeout=45)
        command.wait("document.querySelectorAll('.photo-picker img').length===1")
        assert api(command, '/assignments')['body']['total'] == 0
        assert command.evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='APPROVE RESPONSE & DISPATCH'&&!b.disabled)")
        command.screenshot('final-command-decision')
        passed('Automatic progressive analysis, hazard/exposure/capacity explanation and protected photo evidence before approval')
        command.click('APPROVE RESPONSE & DISPATCH')
        command.wait("document.querySelectorAll('.aegis-resource-marker').length>=4")
        assignments = api(command, '/assignments')['body']['assignments']
        own = assignments[0]
        responder.navigate(base + '/responder')
        login(responder, own['resource_id'])
        responder.wait("document.body.innerText.includes('CURRENT MISSION')", timeout=50)
        assert responder.evaluate("sessionStorage.getItem('aegis_command_token')===null")
        assert api(responder, '/reports')['status'] == 401
        assert api(responder, '/assignments?resource_id=' + assignments[1]['resource_id'])['status'] == 403
        responder.click('ACCEPTED'); responder.wait("document.querySelector('.responder-device-head').innerText.includes('ACCEPTED')")
        responder.click('EN ROUTE'); responder.wait("document.querySelector('.responder-device-head').innerText.includes('EN_ROUTE')")
        command.wait("document.body.innerText.includes('EN_ROUTE')")
        passed('Authority approval dispatches; independent responder sees only its mission and updates shared state')

        command.wait("!document.querySelector('.route-status-panel').innerText.includes('CALCULATING ROAD ROUTES')", timeout=20)
        command.click('START DEMO MOVEMENT')
        command.wait("[...document.querySelectorAll('[data-resource-id]')].some(e=>Number(e.dataset.progress)>.01)")
        command.evaluate("window.testCanvas=document.querySelector('canvas');window.testMarker=document.querySelector('[data-resource-id]');window.firstProgress=Number(testMarker.dataset.progress)")
        command.wait("Number(testMarker.dataset.progress)>firstProgress+.03")
        assert command.evaluate("testCanvas===document.querySelector('canvas') && testMarker===document.querySelector('[data-resource-id]')")
        command.screenshot('final-moving-units')
        command.wait("[...document.querySelectorAll('[data-resource-id]')].length>=4 && [...document.querySelectorAll('[data-resource-id]')].every(e=>Number(e.dataset.progress)>=.999)", timeout=60)
        responder.wait("document.querySelector('.responder-device-head').innerText.includes('ON_SCENE')")
        passed('Stable map canvas/markers, labelled route fallback, common movement timeline and synchronized arrival')
        stored = api(command, '/reports/' + report_id)['body']['report']
        tab('WHAT-IF')
        command.wait("!!document.querySelector('[aria-label=\"Shelter capacity retained\"]')")
        for label in ['Shelter capacity retained', 'Hospital capacity retained']:
            fill(command, '[aria-label="' + label + '"]', '0')
        command.click('RUN WHAT-IF SCENARIO')
        command.wait("[...document.querySelectorAll('.scenario-result')].at(-1).innerText.includes('No safe hospital available')")
        assert api(command, '/reports/' + report_id)['body']['report'] == stored
        tab('PREDICTIVE'); command.wait("document.body.innerText.includes('FUTURE RESOURCE DEMAND')")
        command.click('RECALCULATE WITH SHELTER CLOSED')
        command.wait("document.querySelector('.scenario-stress').innerText.includes('people allocated')")
        tab('RELOCATION'); command.wait("document.body.innerText.includes('POPULATION ALLOCATION')")
        tab('AUDIT'); command.wait("document.body.innerText.includes('ASSIGNMENT_CREATED') || document.body.innerText.includes('assigned.')")
        passed('What-If zero hospital/shelter capacity, prediction and closure recalculate without changing live operations')
        responder.send('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
        assert responder.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
        responder.screenshot('final-responder-mobile')
        responder.click('RESOLVED'); responder.wait("document.body.innerText.includes('UNIT AVAILABLE')")
        passed('Mobile responder completion releases its mission')

        browser.send('Browser.setPermission', permission={'name':'geolocation'}, setting='granted', origin=base)
        browser.send('Emulation.setGeolocationOverride', latitude=13.13, longitude=80.22, accuracy=15)
        browser.navigate(base + '/report'); browser.wait("!!document.querySelector('.sos-button')")
        browser.click('SOS')
        browser.wait("location.pathname.startsWith('/queued/') && document.body.innerText.includes('REPORT SYNCHRONIZED')", timeout=25)
        sos_id = browser.evaluate("location.pathname.split('/').at(-1)")
        signal = next(s for s in api(command, '/distress')['body'] if s['id'] == sos_id)
        assert signal['status'] == 'DEMO_MISSION_ASSIGNED', signal
        missions = [a for a in api(command, '/assignments')['body']['assignments'] if a['report_id'] == signal['report_id']]
        assert len(missions) == 1 and missions[0]['resource_type'] == 'POLICE'
        command.wait("document.querySelector('.distress-panel').innerText.includes('SOS')")
        passed('Three-second SOS creates a high-priority signal and one available demo police mission')

        browser.send('Browser.setPermission', permission={'name':'geolocation'}, setting='denied', origin=base)
        browser.navigate(base + '/report'); browser.wait("!!document.querySelector('.sos-button')"); browser.click('SOS')
        browser.wait("location.pathname.startsWith('/queued/') && document.body.innerText.includes('REPORT SYNCHRONIZED')", timeout=25)
        unknown_id = browser.evaluate("location.pathname.split('/').at(-1)")
        signal = next(s for s in api(command, '/distress')['body'] if s['id'] == unknown_id)
        assert signal['status'] == 'LOCATION_NEEDED' and signal['context']['latitude'] is None
        passed('GPS denial never blocks SOS; Command receives an honest location-needed signal')

        browser.navigate(base + '/call'); browser.wait("!!document.querySelector('#intake-text')")
        browser.click('START SPEAKING'); browser.wait("document.querySelector('.voice-status').innerText.includes('LISTENING')"); time.sleep(1.1); browser.click('STOP')
        browser.wait("document.querySelector('#intake-text').value.includes('twenty students')")
        assert browser.evaluate("!document.querySelector('.intake-summary')")
        fill(browser, '[aria-label=Latitude]', '13.131'); fill(browser, '[aria-label=Longitude]', '80.22')
        browser.click('ANALYZE EMERGENCY'); browser.wait("document.querySelector('.intake-parse-status').innerText.includes('Details ready')")
        browser.click('EDIT DETAILS'); fill(browser, '[aria-label=Injured]', '2'); browser.click('DONE EDITING')
        browser.click('SEND EMERGENCY REPORT'); voice_id = confirm_receipt(browser)
        voice_report = api(browser, '/reports/' + voice_id)['body']['report']
        assert voice_report['intake']['speech_provider'] == 'SARVAM' and voice_report['injured'] == 2
        assert voice_report['intake']['nlp_method'] == 'ADVANCED_NLP'
        passed('Real MediaRecorder WebM capture, mocked multilingual providers, explicit analysis, reviewed corrections and provenance')

        browser.navigate(base + '/call'); browser.wait("!!document.querySelector('#intake-text')")
        browser.send('Network.setBlockedURLs', urls=['*voice/transcribe*', 'https://*.tile.openstreetmap.org/*', 'https://router.project-osrm.org/*'])
        browser.click('START SPEAKING'); browser.wait("document.querySelector('.voice-status').innerText.includes('LISTENING')"); time.sleep(1.1); browser.click('STOP')
        browser.wait("document.body.innerText.includes('retained recording') && !document.querySelector('.voice-status').innerText.includes('PROCESSING')")
        browser.navigate(base + '/call'); browser.wait("document.body.innerText.includes('Recording retained in this browser')")
        browser.click('SEND ORIGINAL FOR REVIEW')
        browser.wait("document.body.innerText.includes('REPORT SYNCHRONIZED')")
        deferred_id = browser.evaluate("location.pathname.split('/').at(-1)")
        deferred = next(s for s in api(command, '/distress')['body'] if s['id'] == deferred_id)
        assert deferred['has_audio'] and not deferred['report_id']
        browser.send('Network.setBlockedURLs', urls=['https://*.tile.openstreetmap.org/*', 'https://router.project-osrm.org/*'])
        passed('Failed transcription preserves audio across refresh and submits a deferred review receipt')

        browser.navigate(base + '/sms'); browser.wait("!!document.querySelector('#intake-text')")
        fill(browser, '#intake-text', 'Flood near Anna Nagar bridge. Around thirty people are trapped and elderly people are present.')
        fill(browser, '[aria-label=Latitude]', '13.14'); fill(browser, '[aria-label=Longitude]', '80.22')
        browser.wait("document.querySelector('.intake-parse-status').innerText.includes('Details ready') && !document.querySelector('.intake-send').disabled")
        browser.click('EDIT DETAILS'); fill(browser, '[aria-label="People affected"]', '34'); browser.click('DONE EDITING')
        browser.send('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
        assert browser.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
        browser.screenshot('final-intake-mobile')
        browser.click('SEND EMERGENCY REPORT'); sms_id = confirm_receipt(browser)
        sms = api(browser, '/reports/' + sms_id)['body']['report']
        assert sms['source'] == 'SMS' and sms['people_affected'] == 34 and sms['trapped'] == 30
        assert sms['intake']['nlp_method'] == 'LOCAL_RULE_BASED'
        passed('Basic text fallback, reviewed counts, mobile layout and shared normal report storage')
        browser.navigate(base + '/report'); browser.wait("!!document.querySelector('.sos-button')")
        assert browser.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
        assert browser.evaluate("document.querySelector('.sos-button').getBoundingClientRect().width>=150")
        browser.evaluate("document.querySelector('.sos-button').focus()")
        assert browser.evaluate("document.activeElement.className==='sos-button'")
        browser.screenshot('final-citizen-mobile')
        passed('Mobile SOS prominence, keyboard focus, readable body and no horizontal overflow')

        exceptions = [e for actor in actors for e in actor.events if e.get('method') == 'Runtime.exceptionThrown']
        assert not exceptions, exceptions
        passed('Zero uncaught runtime exceptions across three independent browser contexts')
        (ARTIFACTS / 'final-browser-result.json').write_text(json.dumps({'passed': True, 'checks': checks, 'actors': 3,
            'report_id': report_id, 'voice_id': voice_id, 'sms_id': sms_id, 'runtime_exceptions': exceptions,
            'providers': 'Mocked HTTP; no real provider credits or emergency services', 'mode': 'production PWA'}, indent=2), encoding='utf-8')
    except Exception:
        import traceback
        traceback.print_exc()
        for index, actor in enumerate(actors):
            try:
                actor.screenshot('final-failure-' + str(index))
                (ARTIFACTS / ('final-failure-' + str(index) + '.txt')).write_text(actor.evaluate('document.body.innerText'), encoding='utf-8')
            except Exception:
                pass
        raise
    finally:
        for child in [command, responder]:
            child.close()


if __name__ == '__main__':
    main(extra_flow=verify, run_core=False, production=True, backend_module='scripts.browser_voice_server:app', fake_media=True)
