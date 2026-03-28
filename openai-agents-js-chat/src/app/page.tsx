import { redirect } from 'next/navigation';
import ChatView from '@/app/components/ChatView';
import { toUiMessages } from '@/app/lib/messageConverters';
import { createSession, findSession } from '@/app/lib/session';

export const dynamic = 'force-dynamic';

const SESSION_QUERY_KEY = 'session';

type PageProps = {
  searchParams?:
    | Record<string, string | string[] | undefined>
    | Promise<Record<string, string | string[] | undefined>>;
};

function readSessionId(
  searchParams: Record<string, string | string[] | undefined> | undefined,
): string | undefined {
  const value = searchParams?.[SESSION_QUERY_KEY];
  return typeof value === 'string' && value.trim() ? value : undefined;
}

export default async function Page({ searchParams }: PageProps) {
  const resolvedSearchParams = await Promise.resolve(searchParams);
  const sessionId = readSessionId(resolvedSearchParams);

  if (!sessionId) {
    const nextSessionId = crypto.randomUUID();
    await createSession(nextSessionId);
    redirect(`/?${SESSION_QUERY_KEY}=${nextSessionId}`);
  }

  const entry = findSession(sessionId);
  if (!entry) {
    const fallbackSessionId = crypto.randomUUID();
    await createSession(fallbackSessionId);
    redirect(`/?${SESSION_QUERY_KEY}=${fallbackSessionId}`);
  }

  const historyItems = await entry.session.getItems(10);
  const initialMessages = toUiMessages(historyItems);

  return (
    <ChatView
      title="Sky Guide"
      description="Ask about the night sky, weather conditions, or account issues. The assistant can use tools and hand off support questions when needed."
      placeholder="Ask about tonight's best constellations..."
      sessionId={sessionId}
      initialMessages={initialMessages}
    />
  );
}
