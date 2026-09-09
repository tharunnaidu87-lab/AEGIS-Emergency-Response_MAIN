# AEGIS frontend

React, TypeScript and Vite implement citizen, command, intake and responder views. MapLibre owns the operational map; FastAPI supplies shared analysis.

See the project [README](../README.md) for setup and configuration. From the project root, use `npm.cmd --prefix frontend run dev`, `run build`, `run lint`, or `test`.

The API base defaults to `/api`. Vite forwards it to backend port 8001. Production hosting must provide a reverse proxy and SPA fallback.
