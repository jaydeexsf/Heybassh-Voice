# Heybassh

A British English teacher voice agent: Speech-to-Text → LLM → Text-to-Speech, with student progress tools.

## Configuration

- **Bot Type**: Web
- **Transport(s)**: WebSocket, SmallWebRTC
- **Pipeline**: Cascade
  - **STT**: Deepgram
  - **LLM**: Google Gemini
  - **TTS**: Self-hosted Piper HTTP API
- **Tools**: load the current 22-lesson curriculum and save scores (pass at 70+)

This is **not** production-ready until you have tested it locally and set Vercel/Railway environment variables. Progress is stored in a JSON file on the bot server (fine for testing; use a database later if you need it to survive Railway restarts).

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
   # Required: DEEPGRAM_API_KEY (STT), GOOGLE_API_KEY (LLM)
   ```

4. **Run the bot**:

   ```bash
   uv run bot.py
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
uv run python -m unittest tests.test_english_teacher
```

`server/elevenlabs_tools.json` is the webhook tool list to paste into ElevenLabs. While testing from ElevenLabs on your laptop, the webhook URL must be public (for example an ngrok tunnel to port 7860). The local Pipecat voice UI does **not** need that: it calls the tools in-process.

## Deploy

### Backend (Railway)

1. Create a Railway service from `server/`.
2. Set `DEEPGRAM_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_MODEL`, and `PIPER_TTS_BASE_URL`.
3. After you have a Vercel URL, set `PIPECAT_ALLOWED_ORIGINS` to that origin (plus `http://localhost:3000` if you still test locally).
4. Optional: `ELEVENLABS_WEBHOOK_SECRET` and send it as `Authorization: Bearer <secret>` from ElevenLabs.

### Frontend (Vercel)

1. Set the Vercel root directory to `client`.
2. Set `BOT_START_URL` to `https://<your-railway-host>/start`.

Do not deploy until the local voice session can load John's lesson and save a passing score.

## Project Structure

```
Heybassh/
├── server/              # Python bot server
│   ├── bot.py           # Voice pipeline + teacher persona
│   ├── english_teacher.py
│   ├── english_teacher_api.py
│   ├── english_teacher_tools.py
│   ├── elevenlabs_tools.json
│   └── Dockerfile
├── client/              # Next.js voice UI
└── README.md
```
