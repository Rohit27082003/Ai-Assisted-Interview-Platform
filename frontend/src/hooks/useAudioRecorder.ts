import { useRef, useState, useCallback } from 'react';

interface UseAudioRecorderOptions {
  onChunk?: (chunk: Blob, sequence: number) => void;
  chunkInterval?: number; // ms
}

export function useAudioRecorder({
  onChunk,
  chunkInterval = 1000,
}: UseAudioRecorderOptions = {}) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const sequenceRef = useRef(0);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : 'audio/mp4',
      });
      mediaRecorderRef.current = mediaRecorder;
      sequenceRef.current = 0;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          onChunk?.(event.data, sequenceRef.current++);
        }
      };

      mediaRecorder.start(chunkInterval);
      setRecording(true);
    } catch (err) {
      setError('Microphone access denied or unavailable');
      console.error('Audio recording error:', err);
    }
  }, [onChunk, chunkInterval]);

  const stop = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
    }
    mediaRecorderRef.current = null;
    setRecording(false);
  }, []);

  return { recording, start, stop, error };
}
