# 🎤 CRITICAL: Frontend Audio Format Fix

## ⚠️ Problem Identified

**AWS Transcribe ONLY accepts these audio formats:**
```
✅ ogg-opus     (recommended - compressed, low latency)
✅ pcm          (uncompressed, guaranteed to work)
✅ flac         (lossless, larger size)
✅ g711-ulaw    (telephony)
✅ g711-alaw    (telephony)
✅ g729         (telephony)
❌ webm-opus    (NOT SUPPORTED!)
❌ mp3          (NOT SUPPORTED!)
❌ aac          (NOT SUPPORTED!)
```

**Current Issue:**
- Browser `MediaRecorder` typically outputs `webm` format
- AWS Transcribe rejects `webm-opus` with error:
  ```
  Value 'webm-opus' failed to satisfy enum value set
  ```

---

## ✅ Solution: Configure Frontend to Use OGG-OPUS

### Option 1: Use OGG-OPUS (Recommended)

**Update your frontend audio capture code:**

```javascript
// ❌ WRONG (will fail):
const mediaRecorder = new MediaRecorder(stream);

// ✅ CORRECT (AWS compatible):
const mediaRecorder = new MediaRecorder(stream, {
  mimeType: 'audio/ogg; codecs=opus',
  audioBitsPerSecond: 48000
});
```

**Full Example:**

```javascript
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,          // Mono
        sampleRate: 48000,        // Matches TRANSCRIBE_SAMPLE_RATE
        echoCancellation: true,
        noiseSuppression: true,
      }
    });

    // Check if ogg-opus is supported
    const mimeType = 'audio/ogg; codecs=opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      console.error('ogg-opus not supported, falling back to PCM');
      // Fall back to Option 2 (PCM)
      return startRecordingPCM(stream);
    }

    const mediaRecorder = new MediaRecorder(stream, {
      mimeType: mimeType,
      audioBitsPerSecond: 48000
    });

    mediaRecorder.ondataavailable = async (event) => {
      if (event.data.size > 0) {
        // Send to backend via WebSocket
        const arrayBuffer = await event.data.arrayBuffer();
        const base64 = btoa(
          String.fromCharCode(...new Uint8Array(arrayBuffer))
        );

        websocket.send(JSON.stringify({
          type: 'audio_chunk',
          data: { chunk: base64 }
        }));
      }
    };

    // Capture audio chunks every 250ms for real-time transcription
    mediaRecorder.start(250);

    console.log('✅ Recording started with ogg-opus format');
  } catch (error) {
    console.error('Failed to start recording:', error);
  }
}
```

---

### Option 2: Use PCM (Fallback - Always Works)

If `ogg-opus` is not supported (rare), use uncompressed PCM:

```javascript
async function startRecordingPCM(stream) {
  const audioContext = new AudioContext({ sampleRate: 48000 });
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);

  source.connect(processor);
  processor.connect(audioContext.destination);

  processor.onaudioprocess = (e) => {
    const inputData = e.inputBuffer.getChannelData(0);

    // Convert Float32Array to Int16Array (PCM format)
    const pcmData = new Int16Array(inputData.length);
    for (let i = 0; i < inputData.length; i++) {
      const s = Math.max(-1, Math.min(1, inputData[i]));
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Send PCM data to backend
    const base64 = btoa(
      String.fromCharCode(...new Uint8Array(pcmData.buffer))
    );

    websocket.send(JSON.stringify({
      type: 'audio_chunk',
      data: { chunk: base64 }
    }));
  };

  console.log('✅ Recording started with PCM format');
}
```

**Update backend for PCM:**
```python
# In transcribe_service.py
aws_stream = await client.start_stream_transcription(
    language_code=settings.TRANSCRIBE_LANGUAGE_CODE,
    media_sample_rate_hz=settings.TRANSCRIBE_SAMPLE_RATE,
    media_encoding="pcm",  # Use PCM instead of ogg-opus
)
```

---

## 🧪 How to Test

### 1. Check Browser Support

```javascript
console.log('Browser audio format support:');
const formats = [
  'audio/ogg; codecs=opus',
  'audio/webm; codecs=opus',
  'audio/mp4',
  'audio/wav'
];

formats.forEach(format => {
  console.log(`${format}: ${MediaRecorder.isTypeSupported(format) ? '✅' : '❌'}`);
});
```

### 2. Verify Audio Format Being Sent

```javascript
mediaRecorder.ondataavailable = async (event) => {
  console.log('Audio chunk:', {
    size: event.data.size,
    type: event.data.type,  // Should be "audio/ogg; codecs=opus"
  });

  // Send to backend...
};
```

### 3. Check Backend Logs

```bash
# Backend should show:
✅ Initialized singleton TranscribeStreamService
✅ Transcription stream started: stream-{interview_id}
✅ Transcription stream stopped: stream-{interview_id}

# NOT this error:
❌ AWS Transcribe stream error: Value 'webm-opus' failed to satisfy enum
```

---

## 📝 Complete Working Example

```javascript
class InterviewRecorder {
  constructor(websocket) {
    this.ws = websocket;
    this.mediaRecorder = null;
    this.stream = null;
  }

  async start() {
    try {
      // Request microphone access
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 48000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      // Configure MediaRecorder with AWS-compatible format
      const mimeType = 'audio/ogg; codecs=opus';

      if (!MediaRecorder.isTypeSupported(mimeType)) {
        throw new Error('Browser does not support ogg-opus format');
      }

      this.mediaRecorder = new MediaRecorder(this.stream, {
        mimeType: mimeType,
        audioBitsPerSecond: 48000
      });

      // Handle audio chunks
      this.mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0) {
          const arrayBuffer = await event.data.arrayBuffer();
          const base64 = btoa(
            String.fromCharCode(...new Uint8Array(arrayBuffer))
          );

          this.ws.send(JSON.stringify({
            type: 'audio_chunk',
            data: { chunk: base64 }
          }));
        }
      };

      // Start recording with 250ms intervals
      this.mediaRecorder.start(250);

      console.log('✅ Recording started');
      return true;
    } catch (error) {
      console.error('Failed to start recording:', error);
      throw error;
    }
  }

  stop() {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }

    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }

    console.log('✅ Recording stopped');
  }
}

// Usage:
const recorder = new InterviewRecorder(websocket);
await recorder.start();

// Later...
recorder.stop();
```

---

## 🔧 Backend Configuration

**Ensure `.env` has:**
```bash
# Audio format configuration
TRANSCRIBE_LANGUAGE_CODE=en-US
TRANSCRIBE_SAMPLE_RATE=48000

# AWS credentials
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
```

**Backend already configured for `ogg-opus`:**
```python
# app/services/aws/transcribe_service.py:159
media_encoding="ogg-opus"  # ✅ Correct!
```

---

## ⚡ Quick Fix Checklist

- [ ] Update frontend MediaRecorder to use `'audio/ogg; codecs=opus'`
- [ ] Verify browser support with `MediaRecorder.isTypeSupported()`
- [ ] Set audio constraints: `sampleRate: 48000`, `channelCount: 1`
- [ ] Send audio chunks every 250ms for real-time transcription
- [ ] Test in browser console - check `event.data.type` is correct
- [ ] Backend `.env` has `TRANSCRIBE_SAMPLE_RATE=48000`
- [ ] Check backend logs - no "webm-opus failed" errors
- [ ] Test transcription - speak and see text appear

---

## 🎯 Expected Behavior After Fix

1. **Browser Console:**
   ```
   ✅ Recording started with ogg-opus format
   Audio chunk: { size: 12345, type: "audio/ogg; codecs=opus" }
   ```

2. **Backend Logs:**
   ```
   INFO: Initialized singleton TranscribeStreamService
   INFO: Transcription stream started: stream-abc123
   DEBUG: Feeding audio chunk: 12345 bytes
   INFO: Partial transcription: "Hello this is a test..."
   INFO: Transcription stream stopped: stream-abc123
   ```

3. **UI:**
   - Real-time transcription appears as you speak
   - No errors in console
   - Audio submission works correctly

---

## 🆘 Troubleshooting

### Error: "ogg-opus not supported"

**Solution:** Use PCM fallback (Option 2 above) or update browser

### Error: "Sample rate mismatch"

**Solution:** Ensure frontend uses `sampleRate: 48000` to match backend

### Error: "Stream not found"

**Solution:** Transcription service singleton issue - restart backend

### No transcription appearing

**Check:**
1. Browser is sending audio chunks (check Network tab)
2. Backend receiving chunks (check logs)
3. AWS credentials are valid
4. Audio format is `ogg-opus` not `webm`

---

**This is the CRITICAL fix needed for transcription to work!** 🎤✅
