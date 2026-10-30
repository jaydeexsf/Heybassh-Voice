import { NextResponse } from 'next/server';

function publicBotWsUrl(fallback: string): string {
  if (process.env.BOT_WS_URL) {
    return process.env.BOT_WS_URL;
  }

  const startUrl = process.env.BOT_START_URL;
  if (!startUrl) {
    return fallback;
  }

  try {
    const parsed = new URL(startUrl);
    const wsScheme = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsScheme}//${parsed.host}/ws-client`;
  } catch {
    return fallback;
  }
}

function normalizeStartResponse(data: Record<string, unknown>) {
  if (typeof data.dailyRoom === 'string' && data.url == null) {
    data.url = data.dailyRoom;
  }
  if (typeof data.dailyToken === 'string' && data.token == null) {
    data.token = data.dailyToken;
  }
  if (data.wsUrl && typeof data.wsUrl === 'string') {
    data.wsUrl = publicBotWsUrl(data.wsUrl);
  }
  return data;
}

export async function POST(request: Request) {
  const botStartUrl =
    process.env.BOT_START_URL || 'http://localhost:7860/start';

  if (!process.env.BOT_START_URL) {
    console.warn(
      'BOT_START_URL not configured, using default: http://localhost:7860/start'
    );
  }

  try {
    const requestData = await request.json();

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (process.env.BOT_START_PUBLIC_API_KEY) {
      headers.Authorization = `Bearer ${process.env.BOT_START_PUBLIC_API_KEY}`;
    }

    const response = await fetch(botStartUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`Failed to connect to Pipecat: ${response.statusText}`);
    }

    const data = (await response.json()) as Record<string, unknown>;

    if (data.error) {
      throw new Error(String(data.error));
    }

    return NextResponse.json(normalizeStartResponse(data));
  } catch (error) {
    return NextResponse.json(
      { error: `Failed to process connection request: ${error}` },
      { status: 500 }
    );
  }
}
