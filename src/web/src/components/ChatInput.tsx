'use client';

import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';
import { Send, Loader2 } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Ask about any fantasy decision...',
}: ChatInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [message]);

  const handleSubmit = () => {
    const trimmed = message.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setMessage('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex gap-3 items-end">
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className={cn(
            'w-full resize-none rounded-xl border-2 border-dark-700 bg-dark-800',
            'px-4 py-3 pr-12 text-dark-100 placeholder-dark-500',
            'focus:outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20',
            'transition-all duration-200',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        />
        <div className="absolute right-2 bottom-2 text-xs text-dark-500">
          {message.length > 0 && `${message.length}/500`}
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={disabled || !message.trim()}
        className={cn(
          'flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center',
          'transition-all duration-200',
          message.trim() && !disabled
            ? 'bg-primary-600 hover:bg-primary-500 text-white shadow-lg shadow-primary-500/25'
            : 'bg-dark-700 text-dark-500 cursor-not-allowed'
        )}
      >
        {disabled ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : (
          <Send className="w-5 h-5" />
        )}
      </button>
    </div>
  );
}

export default ChatInput;
