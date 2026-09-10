"""Real Chromium MediaRecorder on a synthetic microphone; HTTP providers mocked."""
import json
import time
import sys
from browser_smoke import main, ARTIFACTS
from browser_intake_smoke import SPEECH_STUB


def verify_voice(browser, base):
    checks = []
    def passed(text):
        checks.append(text)
        print('PASS voice: ' + text, flush=True)

    def fill(selector, value):
        browser.evaluate("""(() => {const e=document.querySelector(%s); const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto,'value').set.call(e,%s);e.dispatchEvent(new Event('input',{bubbles:true}));})()""" % (json.dumps(selector), json.dumps(value)))

    def navigate(path):
        browser.navigate(base + path)
        browser.wait("!!document.querySelector('#intake-text') && document.querySelector('[aria-label=Latitude]').value!==''")

    browser.send('Browser.setPermission', permission={'name': 'geolocation'}, setting='granted', origin=base)
    browser.send('Emulation.setGeolocationOverride', latitude=13.13, longitude=80.22, accuracy=20)
    browser.send('Page.addScriptToEvaluateOnNewDocument', source=SPEECH_STUB)
    navigate('/call')
    browser.evaluate("""window.voiceRequests=[];window.realFetch=window.fetch;window.fetch=(url,options)=>{
      if(String(url).includes('/intake/parse') || String(url).includes('/voice/transcribe'))window.voiceRequests.push(String(url));
      return window.realFetch(url,options);};
      window.realGetUserMedia=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia=async options=>{window.requestedAudio=options.audio;window.testStream=await window.realGetUserMedia(options);return window.testStream;};""")
    browser.click('START SPEAKING')
    browser.wait("document.querySelector('.voice-status').innerText.includes('LISTENING')")
    time.sleep(1.2)
    browser.click('STOP')
    browser.wait("document.querySelector('#intake-text').value.includes('twenty students')")
    assert browser.evaluate("window.requestedAudio.echoCancellation && window.requestedAudio.noiseSuppression && window.requestedAudio.autoGainControl")
    browser.wait("window.testStream.getTracks().every(t=>t.readyState==='ended')")
    assert browser.evaluate("window.voiceRequests.filter(u=>u.includes('/intake/parse')).length===0 && !document.querySelector('.intake-summary')")
    assert browser.evaluate("document.body.innerText.includes('te-IN')")
    passed('MediaRecorder WebM/Opus upload, preprocessing, track release, detected language and explicit Analyze gate')
    browser.click('ANALYZE EMERGENCY')
    browser.wait("document.querySelector('.intake-parse-status').innerText.includes('Details ready')")
    assert browser.evaluate("document.querySelector('.intake-review').innerText.includes('ADVANCED_NLP')")
    assert browser.evaluate("document.querySelector('.intake-confidence').innerText.includes('Unrated')")
    browser.click('EDIT DETAILS')
    fill('[aria-label="Injured"]', '2')
    browser.click('DONE EDITING')
    fill('[aria-label="Latitude"]', '13.131')
    time.sleep(.9)
    assert browser.evaluate("window.voiceRequests.filter(u=>u.includes('/intake/parse')).length===1")
    browser.send('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
    assert browser.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
    browser.screenshot('voice-multilingual-mobile')
    browser.click('SEND EMERGENCY REPORT')
    browser.wait("!!document.querySelector('.intake-receipt')")
    report_id = browser.evaluate("document.querySelector('.intake-receipt strong').innerText")
    report = browser.evaluate("(async()=> (await (await fetch('/api/reports/" + report_id + "')).json()).report)()")
    assert report['intake']['speech_provider'] == 'SARVAM'
    assert report['intake']['nlp_method'] == 'ADVANCED_NLP'
    assert report['intake']['citizen_corrections']['injured'] == {'original': None, 'reviewed': 2}
    assert report['intake']['reviewed']['trapped'] is None
    browser.click('OPEN THIS INCIDENT IN COMMAND')
    browser.wait("!!document.querySelector('.command-intake-record')")
    browser.evaluate("document.querySelector('.command-intake-record').open=true")
    assert browser.evaluate("document.querySelector('.command-intake-record').innerText.includes('SARVAM') && document.querySelector('.command-intake-record').innerText.includes('NVIDIA_NIM')")
    browser.screenshot('voice-command-provenance')
    passed('Advanced interpretation, unknowns, corrections, no GPS rebilling, persisted CALL and Command provenance')

    navigate('/call')
    browser.evaluate("""window.realFetch=window.fetch;window.fetch=(url,options)=>String(url).includes('/voice/transcribe')?Promise.resolve(new Response('{}',{status:503})):window.realFetch(url,options);""")
    browser.click('START SPEAKING')
    browser.wait("document.querySelector('.voice-status').innerText.includes('LISTENING')")
    time.sleep(.7)
    browser.click('STOP')
    browser.wait("document.body.innerText.includes('Advanced multilingual transcription unavailable')")
    browser.click('START SPEAKING')
    browser.wait("document.querySelector('#intake-text').value.includes('twenty people')")
    browser.click('STOP')
    assert browser.evaluate("!document.querySelector('.intake-summary')")
    fill('#intake-text', 'LOCAL FALLBACK Fire near the hostel. Twenty people inside.')
    browser.click('ANALYZE EMERGENCY')
    browser.wait("document.querySelector('.intake-parse-status').innerText.includes('Details ready')")
    assert browser.evaluate("document.querySelector('.intake-review').innerText.includes('LOCAL_RULE_BASED')")
    passed('Sarvam failure, explicitly labeled browser fallback, manual editing and local NLP fallback')

    navigate('/call')
    browser.evaluate("navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Denied','NotAllowedError')}")
    browser.click('START SPEAKING')
    browser.wait("document.body.innerText.includes('permission was denied')")
    assert browser.evaluate("!document.querySelector('#intake-text').readOnly")
    passed('Microphone denial leaves manual transcript available')
    navigate('/call')
    browser.evaluate("window.realGet=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=async o=>{window.testStream=await window.realGet(o);return window.testStream}")
    browser.click('START SPEAKING')
    browser.wait("document.querySelector('.voice-status').innerText.includes('LISTENING')")
    browser.evaluate("document.querySelector('.intake-methods a[href=\"/sms\"]').click()")
    browser.wait("location.pathname==='/sms'")
    browser.wait("window.testStream.getTracks().every(t=>t.readyState==='ended')")
    passed('Navigation during recording releases microphone tracks')
    (ARTIFACTS / 'voice-result.json').write_text(json.dumps({'checks': checks, 'report_id': report_id,
        'microphone': 'Chromium synthetic device, real MediaRecorder', 'providers': 'Mocked HTTP'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main(extra_flow=verify_voice, run_core='--voice-only' not in sys.argv, backend_module='scripts.browser_voice_server:app', fake_media=True)
