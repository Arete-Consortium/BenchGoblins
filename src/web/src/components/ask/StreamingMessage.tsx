'use client';

import { useState, useEffect } from 'react';
import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StreamingMessageProps {
  content: string;
  isStreaming: boolean;
}

export function StreamingMessage({ content, isStreaming }: StreamingMessageProps) {
  const [showCursor, setShowCursor] = useState(true);

  // Blinking cursor effect while streaming
  useEffect(() => {
    if (!isStreaming) {
      setShowCursor(false);
      return;
    }

    const interval = setInterval(() => {
      setShowCursor((prev) => !prev);
    }, 500);

    return () => clearInterval(interval);
  }, [isStreaming]);

  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-full bg-primary-500/20 flex items-center justify-center flex-shrink-0">
        <Sparkles className={cn('w-5 h-5 text-primary-400', isStreaming && 'animate-pulse')} />
      </div>
      <div className="bg-dark-800 rounded-2xl rounded-bl-md px-4 py-3 max-w-[80%]">
        <p className="text-dark-100 whitespace-pre-wrap">
          {content}
          {isStreaming && showCursor && <span className="inline-block w-2 h-5 bg-primary-400 ml-0.5 animate-pulse" />}
        </p>
      </div>
    </div>
  );
}
