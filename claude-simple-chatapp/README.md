# Claude Chat

Browser chat for Claude with a React frontend, an Express server, and live conversation threads.

## Local Run

```bash
npm install
ANTHROPIC_API_KEY=your_key npm run dev
```

This starts:

- the backend on `http://localhost:3001`
- the frontend on `http://localhost:5173`

Open `http://localhost:5173` in your browser.

## Notes

- Chat history is kept in memory for the current process.
- If you extend this app for production, add persistence and authentication.
