# Sky Guide Chat

Streaming browser chat about the night sky, weather, and account questions.

The main route shows rich streaming output with tool calls and reasoning. The `/text` route is a lighter text-only version of the same assistant.

## Local Run

```bash
npm install
OPENAI_API_KEY=your_key npm run build
OPENAI_API_KEY=your_key npm start
```

Open `http://localhost:3000` for the main chat UI or `http://localhost:3000/text` for the simpler text view.
