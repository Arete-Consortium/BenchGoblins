'use client';

import { useRef, useState } from 'react';
import { toPng } from 'html-to-image';
import { Download, Share2, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface VerdictShareData {
  type: 'verdict';
  headline: string;
  teamName?: string;
  week?: number;
  riskMode: string;
  swaps: { bench: string; start: string; confidence: number }[];
}

interface TrashTalkShareData {
  type: 'trash-talk';
  opponent: string;
  lines: string[];
  spiceLevel: number;
}

type ShareData = VerdictShareData | TrashTalkShareData;

function VerdictCard({ data }: { data: VerdictShareData }) {
  return (
    <div className="w-[600px] bg-gradient-to-br from-[#0a0a0f] via-[#111118] to-[#0d1117] p-8 rounded-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center text-white font-black text-lg">
            BG
          </div>
          <div>
            <div className="text-white font-bold text-sm">BENCH GOBLINS</div>
            <div className="text-gray-500 text-xs">
              {data.week ? `Week ${data.week}` : ''} {data.riskMode.toUpperCase()} MODE
            </div>
          </div>
        </div>
        {data.teamName && (
          <div className="text-gray-400 text-xs">{data.teamName}</div>
        )}
      </div>

      {/* Headline */}
      <div className="text-white text-xl font-bold mb-6 leading-tight">
        {data.headline}
      </div>

      {/* Swaps */}
      <div className="space-y-3">
        {data.swaps.slice(0, 3).map((swap, i) => (
          <div
            key={i}
            className="flex items-center gap-4 bg-white/5 rounded-xl px-5 py-3 border border-white/10"
          >
            <div className="flex-1">
              <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-0.5">Bench</div>
              <div className="text-red-400 font-bold">{swap.bench}</div>
            </div>
            <div className="text-gray-600 text-lg font-bold">&rarr;</div>
            <div className="flex-1 text-right">
              <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-0.5">Start</div>
              <div className="text-green-400 font-bold">{swap.start}</div>
            </div>
            <div className="w-16 text-center">
              <div className="text-white font-bold text-lg">{swap.confidence}%</div>
              <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden mt-1">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${swap.confidence}%`,
                    backgroundColor: swap.confidence >= 75 ? '#4ade80' : swap.confidence >= 60 ? '#facc15' : '#f87171',
                  }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-6 pt-4 border-t border-white/10">
        <div className="text-gray-500 text-xs">benchgoblins.com</div>
        <div className="text-gray-600 text-xs">AI-Powered Fantasy Decisions</div>
      </div>
    </div>
  );
}

function TrashTalkCard({ data }: { data: TrashTalkShareData }) {
  const spiceEmoji = data.spiceLevel >= 4 ? '🔥🔥🔥' : data.spiceLevel >= 2 ? '🔥🔥' : '🔥';

  return (
    <div className="w-[600px] bg-gradient-to-br from-[#1a0a0a] via-[#181111] to-[#170d0d] p-8 rounded-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-red-500 to-orange-600 flex items-center justify-center text-white font-black text-lg">
            BG
          </div>
          <div>
            <div className="text-white font-bold text-sm">GOBLIN TRASH TALK</div>
            <div className="text-gray-500 text-xs">Spice Level: {spiceEmoji}</div>
          </div>
        </div>
        <div className="text-red-400 text-xs font-bold">vs {data.opponent}</div>
      </div>

      {/* Lines */}
      <div className="space-y-4">
        {data.lines.slice(0, 4).map((line, i) => (
          <div
            key={i}
            className="bg-white/5 rounded-xl px-5 py-4 border border-white/10"
          >
            <p className="text-white text-base leading-relaxed italic">
              &ldquo;{line}&rdquo;
            </p>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-6 pt-4 border-t border-white/10">
        <div className="text-gray-500 text-xs">benchgoblins.com</div>
        <div className="text-gray-600 text-xs">The Goblin Has Spoken</div>
      </div>
    </div>
  );
}

export function ShareCard({
  data,
  onClose,
}: {
  data: ShareData;
  onClose: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [downloading, setDownloading] = useState(false);
  const [shared, setShared] = useState(false);

  const generateImage = async (): Promise<Blob | null> => {
    if (!cardRef.current) return null;
    try {
      const dataUrl = await toPng(cardRef.current, {
        pixelRatio: 2,
        backgroundColor: '#000',
      });
      const res = await fetch(dataUrl);
      return res.blob();
    } catch {
      return null;
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await generateImage();
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = data.type === 'verdict' ? 'goblin-verdict.png' : 'goblin-trash-talk.png';
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };

  const handleShare = async () => {
    const blob = await generateImage();
    if (!blob) return;

    const file = new File(
      [blob],
      data.type === 'verdict' ? 'goblin-verdict.png' : 'goblin-trash-talk.png',
      { type: 'image/png' }
    );

    if (navigator.share && navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({
          title: data.type === 'verdict' ? 'Goblin Verdict' : 'Goblin Trash Talk',
          files: [file],
        });
        setShared(true);
        setTimeout(() => setShared(false), 2000);
      } catch {
        // User cancelled
      }
    } else {
      handleDownload();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-dark-900 border border-dark-700 rounded-2xl max-w-[650px] w-full max-h-[90vh] overflow-y-auto">
        {/* Preview */}
        <div className="p-4 flex justify-center overflow-x-auto">
          <div ref={cardRef} className="shrink-0">
            {data.type === 'verdict' ? (
              <VerdictCard data={data} />
            ) : (
              <TrashTalkCard data={data} />
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 p-4 border-t border-dark-700">
          <button
            onClick={handleShare}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-all',
              shared
                ? 'bg-green-600/20 text-green-400 border border-green-600/30'
                : 'bg-primary-600 text-white hover:bg-primary-500'
            )}
          >
            {shared ? <Check className="w-5 h-5" /> : <Share2 className="w-5 h-5" />}
            {shared ? 'Shared!' : 'Share'}
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-dark-600 text-dark-300 hover:text-white hover:border-dark-500 transition-all"
          >
            <Download className="w-5 h-5" />
            {downloading ? 'Saving...' : 'Save'}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-3 rounded-lg text-dark-400 hover:text-white transition-all"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export type { ShareData, VerdictShareData, TrashTalkShareData };
