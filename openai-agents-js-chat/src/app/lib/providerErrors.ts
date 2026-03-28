function asMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return String(error || '').trim();
}

export function looksLikePlaceholderSecret(value: string | undefined): boolean {
  const normalized = (value || '').trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  return [
    'dummy',
    'test',
    'placeholder',
    'your_key',
    'your-api-key',
    'changeme',
    'example',
  ].some((marker) => normalized.includes(marker));
}

export function normalizeOpenAIProviderError(error: unknown): string {
  const message = asMessage(error);
  const lower = message.toLowerCase();

  if (
    lower.includes('api key')
    || lower.includes('authentication')
    || lower.includes('unauthorized')
    || lower.includes('incorrect api key')
    || lower.includes('invalid api key')
    || lower.includes('missing authentication')
  ) {
    return 'OpenAI credentials are invalid or missing for this deployment. Add a valid OPENAI_API_KEY and redeploy.';
  }

  if (
    lower.includes('proxy error')
    || lower.includes('server disconnected')
    || lower.includes('socket hang up')
    || lower.includes('connection reset')
  ) {
    return 'The OpenAI provider closed the request before returning a response. Verify the deployment credentials and try again.';
  }

  if (lower.includes('timeout') || lower.includes('timed out')) {
    return 'The OpenAI provider took too long to respond. Try again in a moment.';
  }

  return 'The OpenAI request failed for this deployment. Verify the configured credentials and try again.';
}
