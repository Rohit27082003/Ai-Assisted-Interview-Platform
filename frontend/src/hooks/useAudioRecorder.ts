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

      // Request microphone with optimal settings for AWS Transcribe
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,          // Mono audio
          sampleRate: 48000,        // 48kHz - matches backend TRANSCRIBE_SAMPLE_RATE
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });

      // Choose best audio format for AWS Transcribe compatibility
      // Priority: ogg-opus (ideal for AWS) → webm-opus (Chrome fallback) → any available
      const formatCandidates = [
        'audio/ogg; codecs=opus',    // Firefox — directly compatible with AWS Transcribe
        'audio/webm; codecs=opus',   // Chrome, Edge — most common browser format
        'audio/webm',                // Fallback
      ];

      const mimeType = formatCandidates.find(fmt => MediaRecorder.isTypeSupported(fmt));

      if (!mimeType) {
        console.warn('No supported audio format found');
        setError('Browser does not support required audio format. Please use Chrome, Firefox, or Edge.');
        stream.getTracks().forEach(t => t.stop());
        return;
      }

      console.log(`Using audio format: ${mimeType}`);

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 128000,
      });

      mediaRecorderRef.current = mediaRecorder;
      sequenceRef.current = 0;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          console.log(`Audio chunk: ${event.data.size} bytes, type: ${event.data.type}`);
          onChunk?.(event.data, sequenceRef.current++);
        }
      };

      mediaRecorder.start(chunkInterval);
      setRecording(true);
      console.log(`✅ Recording started with format: ${mimeType}`);
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
