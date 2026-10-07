# Frontend: AI Meeting Assistant

React + Vite + TypeScript + Tailwind CSS. See the [main README](../README.md) for the whole project.

```bash
npm install
npm run dev        # http://localhost:5173 (expects the backend on http://localhost:8000)
npm test           # Vitest + React Testing Library (fake backend, no real API calls)
npm run build      # type-check and production build
npm run lint       # oxlint
```

The dev server forwards `/api/...` to the backend (see `vite.config.ts`), so the code never hardcodes the server address. No API keys are used or stored in the frontend.

| File | Purpose |
|---|---|
| `src/App.tsx` | Upload form → job view, upload errors |
| `src/api.ts`, `src/types.ts` | Backend calls and TypeScript versions of its JSON |
| `src/useJobPolling.ts` | Polls job progress every second until done or failed |
| `src/fileChecks.ts` | Instant browser-side checks (format, empty, size); the backend checks everything again |
| `src/components/` | `UploadForm`, `ProgressSteps`, `JobView`, `Results`, `RecordView`, `TranscriptView`, `ErrorMessage` |
