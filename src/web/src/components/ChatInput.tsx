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
      textarea.style.height = `${Math.min(textarea.scrollHeight, 300)}px`;
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
      <div className="flex-1 relative group">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className={cn(
            'w-full resize-none rounded-xl border-2 border-dark-700/50 bg-dark-800/80',
            'px-4 py-3 pr-12 text-dark-100 placeholder-dark-400',
            'focus:outline-none focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10',
            'focus:bg-dark-800 transition-all duration-300',
            'group-hover:border-dark-600',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        />
        <div className="absolute right-3 bottom-3 text-xs text-dark-500 transition-opacity">
          {message.length > 0 && (
            <span className={cn(message.length > 450 && 'text-orange-400')}>
              {message.length}/500
            </span>
          )}
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={disabled || !message.trim()}
        className={cn(
          'flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center',
          'transition-all duration-300 transform',
          message.trim() && !disabled
            ? 'bg-gradient-to-br from-primary-500 to-primary-600 hover:from-primary-400 hover:to-primary-500 text-white shadow-lg shadow-primary-500/30 hover:shadow-primary-500/40 hover:scale-105 active:scale-95'
            : 'bg-dark-700/50 text-dark-500 cursor-not-allowed'
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
