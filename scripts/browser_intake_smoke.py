"""Full existing demo regression plus intake flow. Speech events are test doubles;
GPS is Chrome's geolocation API with an emulated fix/permission, not real hardware.
"""
import json
import sys
from browser_smoke import main, ARTIFACTS

SMS = "Flood near Anna Nagar bridge. Water is increasing quickly. Around thirty people are trapped and elderly people are present."
VOICE = "There is a fire near the college hostel. The fire is spreading. Around twenty people are inside and two people are injured."
SPEECH_STUB = """(() => {
  window.intakeSpeechAborts = 0;
  if (location.search.includes('speech=unsupported')) {
    Object.defineProperty(window, 'SpeechRecognition', {configurable:true, value:undefined});
    Object.defineProperty(window, 'webkitSpeechRecognition', {configurable:true, value:undefined});
    return;
  }
  class TestRecognition {
    start() {
      window.intakeRecognition = this;
      setTimeout(() => {
        if (window.intakeSpeechError) {
          this.onerror?.({error:window.intakeSpeechError}); this.onend?.(); return;
        }
        this.onresult?.({results:[{0:{transcript:%s},isFinal:true}]});
      }, 100);
    }
    stop() { this.onend?.(); }
    abort() { window.intakeSpeechAborts++; this.onend?.(); }
  }
  Object.defineProperty(window,'SpeechRecognition',{configurable:true,value:TestRecognition});
})();
""" % json.dumps(VOICE)


def verify_intake(browser, base):
    completed = []

    def passed(name):
        completed.append(name)
        print("PASS intake: " + name, flush=True)

    def navigate(path):
        browser.navigate(base + path)
        browser.wait("document.readyState === 'complete' && !!document.querySelector('.intake-methods')")

    def fill(selector, value):
        browser.evaluate("""(() => { const e=document.querySelector(%s); if(!e)throw Error('Missing field '+%s);
        const prototype=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(prototype,'value').set.call(e,%s);
        e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true})); })()""" % (json.dumps(selector), json.dumps(selector), json.dumps(str(value))))

    def ready():
        if browser.evaluate("location.pathname==='/call' && !document.querySelector('.intake-parse-status').innerText.includes('Details ready') && [...document.querySelectorAll('button')].some(b=>b.textContent==='ANALYZE EMERGENCY' && !b.disabled)"):
            browser.click('ANALYZE EMERGENCY')
        browser.wait("document.querySelector('.intake-parse-status').innerText.includes('Details ready')")

    def report_count():
        return browser.evaluate("(async()=> (await (await fetch('/api/reports')).json()).total)()")

    def saved_report():
        browser.wait("!!document.querySelector('.intake-receipt')")
        identifier = browser.evaluate("document.querySelector('.intake-receipt strong').innerText")
        return browser.evaluate("(async()=> (await (await fetch('/api/reports/" + identifier + "')).json()).report)()")

    def inspect_command(report):
        browser.click('TRACK MY REPORT')
        browser.wait("location.pathname.startsWith('/track/') && document.body.innerText.includes('TRACK MY REPORT')")
        browser.click('TRACK MY REPORT')
        browser.wait("!!document.querySelector('.command-intake-record')")
        browser.evaluate("document.querySelector('.command-intake-record').open=true")
        assert browser.evaluate("document.querySelector('.command-intake-record').innerText.includes(" + json.dumps('SOURCE: ' + report['source']) + ")")
        assert browser.evaluate("document.querySelector('.command-intake-record blockquote').innerText === " + json.dumps(report['raw_content']))
        assert browser.evaluate("document.querySelector('.command-intake-record').innerText.includes('Extraction confidence:')")

    browser.send("Page.addScriptToEvaluateOnNewDocument", source=SPEECH_STUB)
    browser.send("Page.addScriptToEvaluateOnNewDocument", source="Object.defineProperty(window,'MediaRecorder',{configurable:true,value:undefined})")
    browser.send("Browser.setPermission", permission={"name": "geolocation"}, setting="granted", origin=base)
    browser.send("Emulation.setGeolocationOverride", latitude=13.13, longitude=80.22, accuracy=20)
    browser.send("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=1, mobile=True)
    navigate('/report')
    assert browser.evaluate("document.querySelectorAll('.intake-methods a').length === 3")
    browser.evaluate("[...document.querySelectorAll('.intake-methods a')].find(a=>a.textContent.includes('TEXT / SMS')).click()")
    browser.wait("location.pathname==='/sms' && document.querySelector('[aria-label=Latitude]').value!==''")
    before = report_count()
    fill('#intake-text', SMS)
    ready()
    assert browser.evaluate("document.querySelector('.intake-summary').innerText.includes('Anna Nagar bridge')")
    assert report_count() == before
    browser.click('EDIT DETAILS')
    fill('[aria-label="People affected"]', '34')
    fill('[aria-label="Injured"]', '2')
    browser.click('DONE EDITING')
    assert browser.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1")
    browser.evaluate("document.querySelector('.intake-review').scrollIntoView()")
    browser.screenshot('intake-sms-mobile')
    browser.click('SEND EMERGENCY REPORT')
    sms = saved_report()
    assert sms['source'] == 'SMS' and sms['raw_content'] == SMS and sms['gps_verified']
    assert sms['people_affected'] == 34 and sms['injured'] == 2 and sms['trapped'] == 30
    assert sms['intake']['extraction']['people_affected'] == 30
    assert sms['intake']['reviewed']['people_affected'] == 34
    inspect_command(sms)
    passed('SMS review/corrections, GPS, persistence, tracking and Command source/original text')

    navigate('/call')
    browser.wait("document.querySelector('[aria-label=Latitude]').value!==''")
    before = report_count()
    browser.click('START SPEAKING')
    browser.wait("document.querySelector('#intake-text').value.includes('twenty people')")
    assert browser.evaluate("document.body.innerText.includes('LISTENING') && !document.querySelector('.intake-summary')")
    assert report_count() == before
    browser.click('STOP')
    ready()
    assert browser.evaluate("document.querySelector('.intake-summary').innerText.includes('20')")
    browser.click('EDIT TRANSCRIPT')
    assert browser.evaluate("document.activeElement.id==='intake-text'")
    browser.click('EDIT DETAILS')
    fill('[aria-label="Injured"]', '3')
    browser.click('DONE EDITING')
    assert browser.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1")
    browser.evaluate("window.scrollTo(0,0)")
    browser.screenshot('intake-voice-mobile')
    browser.click('SEND EMERGENCY REPORT')
    call = saved_report()
    assert call['source'] == 'CALL' and call['raw_content'] == VOICE and call['injured'] == 3
    assert call['intake']['extraction']['injured'] == 2
    inspect_command(call)
    browser.send("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
    browser.evaluate("document.querySelector('.command-intake-record').scrollIntoView();window.scrollBy(0,-60)")
    browser.screenshot('intake-command-source')
    passed('voice event lifecycle, no automatic send, review, CALL persistence and Command transcript')

    browser.send("Browser.setPermission", permission={"name": "geolocation"}, setting="denied", origin=base)
    navigate('/sms')
    browser.wait("document.querySelector('.intake-location').innerText.includes('denied')")
    assert browser.evaluate("document.querySelector('[aria-label=Latitude]').value==='' && document.querySelector('[aria-label=Longitude]').value===''")
    fill('#intake-text', 'Please help here.')
    ready()
    assert browser.evaluate("document.body.innerText.includes('Where is the emergency?') && document.querySelector('.intake-send').disabled")
    fill('[aria-label="Incident type"]', 'Fire')
    fill('[aria-label="Where is the emergency?"]', 'ABC school')
    fill('[aria-label=Latitude]', '13.15')
    fill('[aria-label=Longitude]', '80.22')
    ready()
    assert browser.evaluate("document.querySelector('.intake-summary').innerText.includes('ABC school')")
    assert browser.evaluate("!document.querySelector('.intake-send').disabled")
    # Corrections survive the GPS/coordinate-triggered re-analysis.
    browser.click('SEND EMERGENCY REPORT')
    unknown = saved_report()
    assert not unknown['gps_verified']
    assert unknown['people_affected'] == 0
    assert unknown['intake']['reviewed']['people_affected'] is None
    passed('GPS denial/manual coordinates, unknown fields and correction preservation')

    navigate('/sms')
    browser.evaluate("window.originalFetch=window.fetch;window.fetch=(url,options)=>String(url).includes('/intake/parse')?Promise.reject(new TypeError('test offline')):originalFetch(url,options)")
    fill('#intake-text', SMS)
    browser.wait("document.querySelector('.intake-parse-status').innerText.includes('could not process')")
    assert browser.evaluate("document.querySelector('#intake-text').value === " + json.dumps(SMS))
    browser.evaluate("window.fetch=window.originalFetch")
    browser.click('RETRY ANALYSIS')
    ready()
    fill('[aria-label=Latitude]', '13.13')
    fill('[aria-label=Longitude]', '80.22')
    ready()
    browser.evaluate("window.fetch=(url,options)=>String(url).endsWith('/reports')&&options?.method==='POST'?Promise.resolve(new Response('{}',{status:503})):originalFetch(url,options)")
    browser.click('SEND EMERGENCY REPORT')
    browser.wait("document.body.innerText.includes('could not confirm delivery')")
    assert browser.evaluate("document.querySelector('#intake-text').value === " + json.dumps(SMS))
    browser.evaluate("window.fetch=window.originalFetch")
    passed('NLP and submission network failures retain input and support retry')

    # Delay one parse to exercise the Render-waking message; edit before it finishes.
    browser.evaluate("window.fetch=(url,options)=>String(url).includes('/intake/parse')?new Promise(resolve=>setTimeout(resolve,9000)).then(()=>originalFetch(url,options)):originalFetch(url,options)")
    fill('#intake-text', 'Fire at the old school. Two injured.')
    browser.wait("document.body.innerText.includes('may be waking up')", timeout=15)
    browser.evaluate("window.fetch=window.originalFetch")
    fill('#intake-text', 'Accident near New Road. Five people.')
    ready()
    browser.wait("document.querySelector('.intake-summary').innerText.includes('Accident')")
    browser.evaluate("new Promise(resolve=>setTimeout(resolve,1500))")
    assert browser.evaluate("document.querySelector('.intake-summary').innerText.includes('New Road')")
    passed('cold-start feedback and stale parse cancellation')

    navigate('/call?speech=unsupported')
    browser.wait("document.body.innerText.includes('Speech recognition is unavailable')")
    fill('#intake-text', VOICE)
    ready()
    assert browser.evaluate("document.querySelector('.intake-summary').innerText.includes('Fire')")
    passed('unsupported speech browser can type/paste a CALL transcript')

    navigate('/call')
    for code, message in [('not-allowed', 'Microphone permission was denied'), ('no-speech', 'No speech was heard'), ('network', 'could not connect')]:
        browser.evaluate('window.intakeSpeechError=' + json.dumps(code))
        browser.click('RETRY')
        browser.wait('document.body.innerText.includes(' + json.dumps(message) + ')')
    browser.evaluate('window.intakeSpeechError=null')
    browser.click('RETRY')
    browser.wait("document.querySelector('#intake-text').value.includes('twenty people')")
    browser.evaluate("[...document.querySelectorAll('.intake-methods a')].find(a=>a.textContent.includes('REPORT ONLINE')).click()")
    browser.wait("location.pathname==='/report'")
    assert browser.evaluate('window.intakeSpeechAborts>0')
    passed('microphone denial, no speech, speech network error, retry and recorder cleanup')

    (ARTIFACTS / 'intake-result.json').write_text(json.dumps({
        'passed': True, 'checks': completed, 'sms_report': sms['id'], 'call_report': call['id'],
        'speech_test_mode': 'SIMULATED_BROWSER_EVENTS_NOT_REAL_MICROPHONE',
        'gps_test_mode': 'CHROME_GEOLOCATION_EMULATION_AND_PERMISSION_CONTROLS',
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main(extra_flow=verify_intake, run_core='--intake-only' not in sys.argv)
