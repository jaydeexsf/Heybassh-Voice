# Heybassh

A British English teacher voice agent: Speech-to-Text → LLM → Text-to-Speech, with student progress tools.

## Configuration

- **Bot Type**: Web
- **Transport(s)**: Daily (Pipecat Cloud), WebSocket, SmallWebRTC
- **Pipeline**: Cascade
  - **STT**: Deepgram
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
   # Required: DEEPGRAM_API_KEY (STT), GOOGLE_API_KEY (LLM)
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

### Pipecat Cloud (agent)

1. Put these keys in secret set `heybasshvoices`:
   - `DEEPGRAM_API_KEY`
   - `GOOGLE_API_KEY`
   - `GOOGLE_MODEL` (`gemini-3-flash-preview`)
   - `PIPER_TTS_ENGINE=local`
   - `PIPER_TTS_VOICE=en_GB-cori-medium`
2. In the agent GitHub settings, use branch `main`, Dockerfile path `server/Dockerfile`, subdirectory `server`, and attach `heybasshvoices`.
3. Use profile `agent-2x` (Silero + local Piper). See `pcc-deploy.toml`.
4. Push to `main` (or click Deploy). Start a session with Daily:

   ```bash
   curl --request POST "https://api.pipecat.daily.co/v1/public/heybassh/start" \
     --header "Authorization: Bearer pk_YOUR_PUBLIC_KEY" \
     --header "Content-Type: application/json" \
     --data "{\"createDailyRoom\": true}"
   ```

### Frontend (Vercel)

1. Set the Vercel root directory to `client`.
2. Set `BOT_START_URL` to `https://api.pipecat.daily.co/v1/public/heybassh/start`.
3. Set `BOT_START_PUBLIC_API_KEY` to your Pipecat Cloud **public** API key.

## Project Structure

```
Heybassh/
├── pcc-deploy.toml      # Pipecat Cloud GitHub deploy settings
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
