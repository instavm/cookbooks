import { query } from "@anthropic-ai/claude-agent-sdk";
import path from "path";
import { fileURLToPath } from "url";

const SYSTEM_PROMPT = `You are a helpful AI assistant. You can help users with a wide variety of tasks including:
- Answering questions
- Writing and editing text
- Coding and debugging
- Analysis and research
- Creative tasks

Be concise but thorough in your responses.`;

type UserMessage = {
  type: "user";
  message: { role: "user"; content: string };
};

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CLAUDE_CODE_WRAPPER = path.join(__dirname, "claude-code-wrapper.mjs");

function looksLikePlaceholderSecret(value: string | undefined): boolean {
  const normalized = (value || "").trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  return ["dummy", "test", "placeholder", "your_key", "your-api-key", "changeme", "example"].some(
    (marker) => normalized.includes(marker),
  );
}

export function normalizeClaudeError(error: unknown): string {
  const message = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : String(error || '').trim();
  const lower = message.toLowerCase();

  if (
    lower.includes('/login')
    || lower.includes('not logged in')
    || lower.includes('api key')
    || lower.includes('authentication')
    || lower.includes('unauthorized')
    || (lower.includes('invalid') && lower.includes('key'))
  ) {
    return 'Claude credentials are invalid or missing for this deployment. Add a valid ANTHROPIC_API_KEY and redeploy.';
  }

  if (lower.includes('timeout') || lower.includes('timed out')) {
    return 'Claude took too long to respond. Try again in a moment.';
  }

  if (lower.includes('server disconnected') || lower.includes('connection') || lower.includes('proxy error')) {
    return 'Claude closed the request before returning a response. Verify the deployment credentials and try again.';
  }

  return 'The Claude request failed for this deployment. Verify the configured credentials and try again.';
}

// Simple async queue - messages go in via push(), come out via async iteration
class MessageQueue {
  private messages: UserMessage[] = [];
  private waiting: ((msg: UserMessage) => void) | null = null;
  private closed = false;

  push(content: string) {
    const msg: UserMessage = {
      type: "user",
      message: {
        role: "user",
        content,
      },
    };

    if (this.waiting) {
      // Someone is waiting for a message - give it to them
      this.waiting(msg);
      this.waiting = null;
    } else {
      // No one waiting - queue it
      this.messages.push(msg);
    }
  }

  async *[Symbol.asyncIterator](): AsyncIterableIterator<UserMessage> {
    while (!this.closed) {
      if (this.messages.length > 0) {
        yield this.messages.shift()!;
      } else {
        // Wait for next message
        yield await new Promise<UserMessage>((resolve) => {
          this.waiting = resolve;
        });
      }
    }
  }

  close() {
    this.closed = true;
  }
}

export class AgentSession {
  private queue = new MessageQueue();
  private outputIterator: AsyncIterator<any> | null = null;

  constructor() {
    if (looksLikePlaceholderSecret(process.env.ANTHROPIC_API_KEY)) {
      throw new Error("Claude credentials are invalid or missing for this deployment. Add a valid ANTHROPIC_API_KEY and redeploy.");
    }
    // Start the query immediately with the queue as input
    // Cast to any - SDK accepts simpler message format at runtime
    this.outputIterator = query({
      prompt: this.queue as any,
      options: {
        maxTurns: 100,
        model: "opus",
        allowedTools: [
          "Bash",
          "Read",
          "Write",
          "Edit",
          "Glob",
          "Grep",
          "WebSearch",
          "WebFetch",
        ],
        systemPrompt: SYSTEM_PROMPT,
        pathToClaudeCodeExecutable: CLAUDE_CODE_WRAPPER,
      },
    })[Symbol.asyncIterator]();
  }

  // Send a message to the agent
  sendMessage(content: string) {
    this.queue.push(content);
  }

  // Get the output stream
  async *getOutputStream() {
    if (!this.outputIterator) {
      throw new Error("Session not initialized");
    }
    while (true) {
      const { value, done } = await this.outputIterator.next();
      if (done) break;
      yield value;
    }
  }

  close() {
    this.queue.close();
  }
}
