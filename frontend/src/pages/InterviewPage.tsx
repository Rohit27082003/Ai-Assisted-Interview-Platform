import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Mic, MicOff, Clock, AlertTriangle, CheckCircle, Send
} from 'lucide-react';
import toast from 'react-hot-toast';
import type { InterviewQuestion, WSMessage } from '../types';

type Phase = 'idle' | 'reading' | 'answering' | 'processing' | 'complete';

export default function InterviewPage() {
  const { interviewId } = useParams<{ interviewId: string }>();
  const navigate = useNavigate();
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const sequenceRef = useRef(0);

  const [connected, setConnected] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [currentQuestion, setCurrentQuestion] = useState<InterviewQuestion | null>(null);
  const [timeLeft, setTimeLeft] = useState(0);
  const [recording, setRecording] = useState(false);
  const [answerText, setAnswerText] = useState('');
  const [cheatingWarnings, setCheatingWarnings] = useState<string[]>([]);
  const [questionsAnswered, setQuestionsAnswered] = useState(0);
  const [transcript, setTranscript] = useState<Array<{ q: string; a: string }>>([]);

  const connectWebSocket = useCallback(() => {
    if (!interviewId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/interviews/ws/${interviewId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      toast.success('Connected to interview session');
    };

    ws.onmessage = (event) => {
      const msg: WSMessage = JSON.parse(event.data);
      handleWSMessage(msg);
    };

    ws.onclose = () => {
      setConnected(false);
    };

    ws.onerror = () => {
      toast.error('WebSocket connection error');
    };
  }, [interviewId]);

  const handleWSMessage = (msg: WSMessage) => {
    switch (msg.type) {
      case 'question':
        setCurrentQuestion({
          question_text: msg.data.question_text,
          pillar: msg.data.pillar,
          question_number: msg.data.question_number,
          is_follow_up: msg.data.is_follow_up,
          reading_time_seconds: msg.data.reading_time_seconds,
          answer_time_seconds: msg.data.answer_time_seconds,
        });
        setPhase('reading');
        setTimeLeft(msg.data.reading_time_seconds);
        setAnswerText('');
        break;

      case 'timer':
        setTimeLeft(msg.data.seconds_left);
        if (msg.data.phase === 'answering' && msg.data.seconds_left > 0) {
          setPhase('answering');
          setTimeLeft(msg.data.seconds_left);
        }
        if (msg.data.auto_closed) {
          submitAnswer();
        }
        break;

      case 'cheating_warning':
        setCheatingWarnings((prev) => [...prev, msg.data.message]);
        toast.error(`Warning: ${msg.data.message}`, { duration: 5000 });
        break;

      case 'complete':
        setPhase('complete');
        toast.success(msg.data.message);
        break;

      case 'error':
        toast.error(msg.data.message);
        break;
    }
  };

  useEffect(() => {
    connectWebSocket();
    return () => {
      wsRef.current?.close();
      stopRecording();
    };
  }, [connectWebSocket]);

  // Timer countdown
  useEffect(() => {
    if (timeLeft <= 0 || phase === 'idle' || phase === 'complete') return;
    const timer = setInterval(() => {
      setTimeLeft((t) => Math.max(0, t - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [timeLeft, phase]);

  const startInterview = () => {
    wsRef.current?.send(JSON.stringify({ type: 'start', data: {} }));
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
          // Send chunk to server
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64 = (reader.result as string).split(',')[1];
            wsRef.current?.send(JSON.stringify({
              type: 'audio_chunk',
              data: { chunk: base64, sequence: sequenceRef.current++ },
            }));
          };
          reader.readAsDataURL(event.data);
        }
      };

      mediaRecorder.start(1000); // 1 second chunks
      setRecording(true);
    } catch {
      toast.error('Microphone access denied');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
    }
    setRecording(false);
  };

  const submitAnswer = () => {
    stopRecording();
    setPhase('processing');
    setQuestionsAnswered((q) => q + 1);

    if (currentQuestion) {
      setTranscript((prev) => [...prev, { q: currentQuestion.question_text, a: answerText }]);
    }

    wsRef.current?.send(JSON.stringify({
      type: 'answer_complete',
      data: { text: answerText },
    }));
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (phase === 'complete') {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <CheckCircle className="w-20 h-20 text-green-500 mx-auto mb-6" />
        <h1 className="text-3xl font-bold mb-4">Interview Complete</h1>
        <p className="text-gray-600 mb-2">
          {questionsAnswered} questions answered across multiple topics
        </p>
        {cheatingWarnings.length > 0 && (
          <p className="text-yellow-600 mb-4">
            {cheatingWarnings.length} integrity warning(s) recorded
          </p>
        )}
        <p className="text-gray-500 mb-8">
          The AI evaluation system will now analyze your responses.
        </p>
        <div className="flex gap-4 justify-center">
          <button className="btn-primary" onClick={() => navigate('/candidates')}>
            Back to Candidates
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Live Interview</h1>
          <p className="text-gray-600">
            {connected ? (
              <span className="text-green-600 flex items-center gap-1">
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                Connected
              </span>
            ) : (
              <span className="text-red-600">Disconnected</span>
            )}
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-500">Questions Answered</p>
          <p className="text-2xl font-bold">{questionsAnswered}</p>
        </div>
      </div>

      {/* Cheating Warnings */}
      {cheatingWarnings.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
          <div className="flex items-center gap-2 text-yellow-800 font-medium mb-2">
            <AlertTriangle className="w-5 h-5" />
            Integrity Warnings ({cheatingWarnings.length})
          </div>
          {cheatingWarnings.map((w, i) => (
            <p key={i} className="text-sm text-yellow-700">{w}</p>
          ))}
        </div>
      )}

      {/* Main Interview Area */}
      {phase === 'idle' && (
        <div className="card text-center py-16">
          <Mic className="w-16 h-16 text-primary-500 mx-auto mb-6" />
          <h2 className="text-2xl font-bold mb-4">Ready to Begin?</h2>
          <p className="text-gray-600 mb-8 max-w-md mx-auto">
            The AI interviewer will ask questions across multiple technical topics.
            You will have time to read each question before answering.
          </p>
          <button className="btn-primary text-lg px-8 py-3" onClick={startInterview}>
            Start Interview
          </button>
        </div>
      )}

      {(phase === 'reading' || phase === 'answering' || phase === 'processing') && currentQuestion && (
        <div className="space-y-6">
          {/* Timer Bar */}
          <div className={`rounded-xl p-4 flex items-center justify-between ${
            phase === 'reading' ? 'bg-blue-50 border border-blue-200' :
            phase === 'answering' ? 'bg-green-50 border border-green-200' :
            'bg-gray-50 border border-gray-200'
          }`}>
            <div className="flex items-center gap-3">
              <Clock className="w-5 h-5" />
              <span className="font-medium">
                {phase === 'reading' ? 'Reading Time' :
                 phase === 'answering' ? 'Answer Time' : 'Processing...'}
              </span>
            </div>
            <span className={`text-2xl font-bold font-mono ${
              timeLeft <= 10 ? 'text-red-600' : ''
            }`}>
              {formatTime(timeLeft)}
            </span>
          </div>

          {/* Question Card */}
          <div className="card">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-3">
              <span className="badge-blue">{currentQuestion.pillar}</span>
              <span>Question {currentQuestion.question_number}</span>
              {currentQuestion.is_follow_up && (
                <span className="badge-yellow">Follow-up</span>
              )}
            </div>
            <p className="text-xl font-medium leading-relaxed">
              {currentQuestion.question_text}
            </p>
          </div>

          {/* Answer Area */}
          {phase === 'answering' && (
            <div className="card space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">Your Answer</h3>
                <div className="flex gap-2">
                  {!recording ? (
                    <button
                      className="btn-secondary flex items-center gap-2"
                      onClick={startRecording}
                    >
                      <Mic className="w-4 h-4" /> Start Recording
                    </button>
                  ) : (
                    <button
                      className="btn-danger flex items-center gap-2"
                      onClick={stopRecording}
                    >
                      <MicOff className="w-4 h-4" /> Stop Recording
                    </button>
                  )}
                </div>
              </div>

              {recording && (
                <div className="flex items-center gap-3 bg-red-50 p-3 rounded-lg">
                  <span className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                  <span className="text-red-700 font-medium">Recording audio...</span>
                </div>
              )}

              <textarea
                className="input-field min-h-[120px]"
                placeholder="Type your answer here (or use voice recording above)..."
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
              />

              <button
                className="btn-primary flex items-center gap-2"
                onClick={submitAnswer}
              >
                <Send className="w-4 h-4" /> Submit Answer
              </button>
            </div>
          )}

          {phase === 'processing' && (
            <div className="card text-center py-8">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600 mx-auto mb-4" />
              <p className="text-gray-600">AI is analyzing your answer...</p>
            </div>
          )}
        </div>
      )}

      {/* Transcript History */}
      {transcript.length > 0 && (
        <div className="card">
          <h3 className="font-semibold mb-4">Session History</h3>
          <div className="space-y-4">
            {transcript.map((t, i) => (
              <div key={i} className="border-l-4 border-primary-200 pl-4">
                <p className="text-sm text-gray-500">Q{i + 1}</p>
                <p className="font-medium">{t.q}</p>
                <p className="text-gray-600 mt-1">{t.a || '(Voice response)'}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
