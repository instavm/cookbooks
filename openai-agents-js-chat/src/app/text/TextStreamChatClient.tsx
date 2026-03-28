'use client';

import { useMemo } from 'react';
import { TextStreamChatTransport, type UIMessage } from 'ai';
import ChatView from '../components/ChatView';

type TextStreamChatClientProps = {
  sessionId: string;
  initialMessages: UIMessage[];
};

export default function TextStreamChatClient({
  sessionId,
  initialMessages,
}: TextStreamChatClientProps) {
  const transport = useMemo(
    () => new TextStreamChatTransport({ api: '/api/chat/text' }),
    [],
  );

  return (
    <ChatView
      title="Sky Guide Lite"
      description="A text-first version of the same assistant for faster, simpler chat."
      placeholder="Ask about tonight's best constellations..."
      sessionId={sessionId}
      initialMessages={initialMessages}
      transport={transport}
    />
  );
}
