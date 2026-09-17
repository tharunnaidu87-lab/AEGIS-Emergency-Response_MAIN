"""Small local-demo abuse guards; not a substitute for a production gateway."""
import time
from collections import defaultdict, deque
from starlette.responses import JSONResponse


class RequestGuard:
    def __init__(self, app):
        self.app = app
        self.attempts = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path'].rstrip('/')
        if path.endswith('/login'):
            now = time.monotonic()
            key = (scope.get('client') or ('local',))[0]
            attempts = self.attempts[key]
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 20:
                return await JSONResponse({'detail': 'Too many sign-in attempts. Wait a minute and retry.'}, 429,
                                          headers={'Retry-After': '60'})(scope, receive, send)
            attempts.append(now)
            if len(self.attempts) > 1000:
                self.attempts = defaultdict(deque, {k: v for k, v in self.attempts.items() if v and v[-1] > now - 60})
        if scope['method'] not in {'POST', 'PATCH'}:
            return await self.app(scope, receive, send)
        limit = 8 * 1024 * 1024 if path == '/distress' else 5 * 1024 * 1024 + 1024
        headers = dict(scope.get('headers', []))
        try:
            if int(headers.get(b'content-length', b'0')) > limit:
                return await JSONResponse({'detail': 'Use a shorter recording or smaller photos.'}, 413)(scope, receive, send)
        except ValueError:
            return await JSONResponse({'detail': 'Invalid request length.'}, 400)(scope, receive, send)
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > limit:
                return await JSONResponse({'detail': 'Use a shorter recording or smaller photos.'}, 413)(scope, receive, send)
            chunks.append(message.get('body', b''))
            if not message.get('more_body'):
                break
        body = b''.join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)
