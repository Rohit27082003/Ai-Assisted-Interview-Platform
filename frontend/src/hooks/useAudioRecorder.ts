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

      // CRITICAL: Use ogg-opus format (AWS Transcribe compatible)
      // AWS only accepts: ogg-opus, pcm, flac, g711-ulaw, g711-alaw, g729
      // Browser default webm-opus is NOT supported by AWS!
      const mimeType = 'audio/ogg; codecs=opus';

      if (!MediaRecorder.isTypeSupported(mimeType)) {
        console.warn('ogg-opus not supported, browser may not be compatible');
        setError('Browser does not support required audio format. Please use Chrome, Firefox, or Edge.');
        stream.getTracks().forEach(t => t.stop());
        return;
      }

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: mimeType,
        audioBitsPerSecond: 48000,
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
      console.log('✅ Recording started with ogg-opus format');
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
