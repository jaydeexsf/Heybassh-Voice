# Heybassh

A British English teacher voice agent: Speech-to-Text → LLM → Text-to-Speech, with student progress tools.

## Configuration

- **Bot Type**: Web
- **Transport(s)**: SmallWebRTC, WebSocket, Daily
- **Pipeline**: Cascade
  - **STT**: Local Moonshine
  - **LLM**: Google Gemini
  - **TTS**: Local Piper British voice (`en_GB-cori-medium`)
- **Tools**: load the current 22-lesson curriculum and save scores (pass at 70+)

Progress is stored in a JSON file on the bot instance (fine for testing; it will not survive Cloud instance restarts).

## Setup

### Server

1. **Navigate to server directory**:

   ```bash
   cd server
   ```

2. **Install dependencies**:

   ```bash
   uv sync
   ```

3. **Configure environment variables**:

   ```bash
   cp .env.example .env
   # Required: GOOGLE_API_KEY (LLM)
   # TTS defaults to local British Piper voice en_GB-cori-medium (downloaded on first run)
   ```

4. **Run the bot**:

   ```bash
   uv run bot.py
   ```

   For a local Daily room (needs `DAILY_API_KEY`):

   ```bash
   uv run bot.py -t daily
   ```

### Client

1. **Navigate to client directory**:

   ```bash
   cd client
   ```

2. **Install dependencies**:

   ```bash
   npm install
   ```

3. **Configure environment variables**:

   ```bash
   cp env.example .env.local
   ```

   For local WebSocket/SmallWebRTC, set `BOT_START_URL=http://localhost:7860/start` and pick that transport in the UI.

4. **Run development server**:

   ```bash
   npm run dev
   ```

5. **Open browser**: http://localhost:3000

## Local tool tests

The bot already has the same two tools the n8n/ElevenLabs workflow used:

1. `GET /webhook/english-teacher/student-lesson?student_id=john`
2. `POST /webhook/english-teacher/update-progress`

With the server running:

```bash
curl "http://localhost:7860/webhook/english-teacher/student-lesson?student_id=john"

curl -X POST "http://localhost:7860/webhook/english-teacher/update-progress" ^
  -H "Content-Type: application/json" ^
  -d "{\"student_id\":\"john\",\"lesson_number\":1,\"score\":82,\"lesson_completed\":true,\"teacher_summary\":\"Strong first lesson.\"}"
```

Unit tests:

```bash
cd server
uv run python -m unittest tests.test_english_teacher tests.test_piper_tts
```

`server/elevenlabs_tools.json` is the webhook tool list to paste into ElevenLabs. While testing from ElevenLabs on your laptop, the webhook URL must be public (for example an ngrok tunnel to port 7860). The local Pipecat voice UI does **not** need that: it calls the tools in-process.

## Deploy

### Render (bot)

This repo’s root `Dockerfile` starts the local Pipecat runner (`POST /start`, `GET /health`) so Render can host it. Use a **Docker** web service, repo root as the build context, Dockerfile path `Dockerfile`, and leave the start command empty.

1. In the Render service, set:
   - `GOOGLE_API_KEY`
   - `GOOGLE_MODEL` (`gemini-3-flash-preview`)
   - `PIPER_TTS_ENGINE=local`
   - `PIPER_TTS_VOICE=en_GB-cori-medium`
   - `DAILY_API_KEY` only if you use Daily
2. Health check path: `/health`. Use at least a Standard instance (Silero + local Piper + Moonshine need RAM/CPU).
3. Push to `main` (or click Deploy). Confirm:

   ```bash
   curl "https://YOUR-SERVICE.onrender.com/health"
   ```

   The hosted UI uses SmallWebRTC. Daily is optional and needs `DAILY_API_KEY`.

### Frontend (Vercel)

1. Set the Vercel root directory to `client`.
2. Set `BOT_START_URL` to `https://YOUR-SERVICE.onrender.com/start`.
3. Do not set `BOT_START_PUBLIC_API_KEY` unless you add matching auth on the bot.

## Project Structure

```
Heybassh/
├── Dockerfile           # Render / Docker bot server (repo root)
├── pcc-deploy.toml      # Optional Pipecat Cloud settings (not used on Render)
├── server/              # Python bot
│   ├── bot.py           # Voice pipeline + teacher persona
│   ├── english_teacher.py
│   ├── english_teacher_api.py
│   ├── english_teacher_tools.py
│   ├── piper_tts.py
│   ├── elevenlabs_tools.json
│   └── Dockerfile
├── client/              # Next.js voice UI
└── README.md
```
