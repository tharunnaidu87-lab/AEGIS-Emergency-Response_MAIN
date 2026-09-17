from pathlib import Path
from datetime import datetime
import re
import shutil

ROOT = Path.cwd().resolve()
if ROOT.name != 'AEGIS-MAIN':
    raise SystemExit(f'Run this from AEGIS-MAIN. Current folder: {ROOT}')

app_path = ROOT / 'frontend' / 'src' / 'App.tsx'
if not app_path.exists():
    raise SystemExit('frontend/src/App.tsx was not found.')

stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
backup = ROOT / '.cache' / f'batch1-v4-backup-{stamp}' / 'frontend' / 'src' / 'App.tsx'
backup.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(app_path, backup)
print(f'Backup created: {backup}')

text = app_path.read_text(encoding='utf-8').replace('\r\n', '\n')

ack_pattern = re.compile('\\n\\s*async function acknowledge\\(\\)\\s*\\{\\s*if \\(selected\\)\\s+await commandAction\\(\\(\\)\\s*=>\\s*updateReportStatus\\(selected\\.id,\\s*"ACKNOWLEDGED"\\)\\);\\s*\\}\\s*', re.S)
text, ack_count = ack_pattern.subn('\n', text, count=1)
print('[APPLY] Removed leftover acknowledge() function' if ack_count else '[KEEP] acknowledge() already absent')

button_pattern = re.compile('<div\\s+className="status-buttons">\\s*<button\\s+type="button"\\s+disabled=\\{actionBusy\\s*\\|\\|\\s*selected\\.status\\s*!==\\s*"REPORTED"\\}\\s+onClick=\\{\\(\\)\\s*=>\\s*\\{\\s*void\\s+acknowledge\\(\\);\\s*\\}\\}>\\s*ACKNOWLEDGE\\s*</button>\\s*<button\\s+type="button"\\s+disabled=\\{actionBusy\\s*\\|\\|\\s*selected\\.status\\s*===\\s*"RESOLVED"\\s*\\|\\|\\s*selectedAssignments\\.length\\s*>\\s*0\\}\\s+onClick=\\{\\(\\)\\s*=>\\s*\\{\\s*void\\s+dispatch\\(\\);\\s*\\}\\}>\\s*DISPATCH\\s+RECOMMENDED\\s+UNITS\\s*</button>', re.S)
replacement = '<div className="status-buttons">\n\n                    <button\n                      type="button"\n                      className="dispatch-button"\n                      disabled={actionBusy || selected.status === "RESOLVED" || selectedAssignments.length > 0}\n                      onClick={() => { void dispatch(); }}\n                    >\n                      {selectedAssignments.length > 0\n                        ? "RESPONSE DISPATCHED"\n                        : actionBusy\n                          ? "APPROVING RESPONSE..."\n                          : "APPROVE RESPONSE & DISPATCH"}\n                    </button>'
text, button_count = button_pattern.subn(replacement, text, count=1)
if button_count:
    print('[APPLY] Replaced ACKNOWLEDGE + DISPATCH with APPROVE RESPONSE & DISPATCH')
elif 'APPROVE RESPONSE & DISPATCH' in text and 'void acknowledge();' not in text:
    print('[KEEP] Approval gate already correct')
else:
    print('[REVIEW] Could not safely match the old Command button block; no blind replacement was made.')

text = text.replace(', updateReportStatus,', ',')
text = text.replace(' updateReportStatus,', ' ')
text = text.replace(', updateReportStatus ', ' ')

problems = []
if 'void acknowledge();' in text: problems.append('ACKNOWLEDGE button call still exists')
if 'async function acknowledge()' in text: problems.append('acknowledge() function still exists')
if 'updateReportStatus(selected.id, "ACKNOWLEDGED")' in text: problems.append('legacy acknowledge status update still exists')
if 'APPROVE RESPONSE & DISPATCH' not in text: problems.append('approval gate text is missing')

app_path.write_text(text, encoding='utf-8', newline='\n')

if problems:
    print('\nNEEDS MANUAL REVIEW:')
    for item in problems: print('  !', item)
else:
    print('\n[OK] Command workflow now has one approval gate and no acknowledge step.')

print('\nRun these next:')
print('  npm --prefix frontend run typecheck')
print('  npm --prefix frontend run build')
print(r'  backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p "test_*.py"')
