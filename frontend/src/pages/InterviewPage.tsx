import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Mic, MicOff, Clock, AlertTriangle, CheckCircle, AlertCircle
} from 'lucide-react';
import toast from 'react-hot-toast';
import type { InterviewQuestion, WSMessage } from '../types';

type Phase = 'idle' | 'reading' | 'answering' | 'processing' | 'complete' | 'terminated';

export default function InterviewPage() {
  const { interviewId } = useParams<{ interviewId: string }>();
  const navigate = useNavigate();
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const sequenceRef = useRef(0);

  // State
  const [connected, setConnected] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [currentQuestion, setCurrentQuestion] = useState<InterviewQuestion | null>(null);
  const [timeLeft, setTimeLeft] = useState(0);
  const [recording, setRecording] = useState(false);
  const [answerText, setAnswerText] = useState('');
  const [cheatingWarnings, setCheatingWarnings] = useState<string[]>([]);
  const [questionsAnswered, setQuestionsAnswered] = useState(0);
  const [transcript, setTranscript] = useState<Array<{ q: string; a: string }>>([]);
  const [permissionStatus, setPermissionStatus] = useState<'checking' | 'granted' | 'denied'>('checking');
  const [showFinishModal, setShowFinishModal] = useState(false);

  // Refs for callbacks to avoid closure staleness
  const phaseRef = useRef(phase);
  const currentQuestionRef = useRef(currentQuestion);
  const answerTextRef = useRef(answerText);

  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { currentQuestionRef.current = currentQuestion; }, [currentQuestion]);
  useEffect(() => { answerTextRef.current = answerText; }, [answerText]);

  // Permission check
  useEffect(() => {
    checkMicrophonePermission();
  }, []);

  const checkMicrophonePermission = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(t => t.stop());
      setPermissionStatus('granted');
    } catch (err) {
      console.error('Microphone permission denied:', err);
      setPermissionStatus('denied');
    }
  };

  // Helper Functions
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
    }
    setRecording(false);
  }, []);

  const finalizeSubmission = useCallback(() => {
    setPhase('processing');
    setQuestionsAnswered((q) => q + 1);

    if (currentQuestionRef.current) {
      setTranscript((prev) => [...prev, { q: currentQuestionRef.current!.question_text, a: answerTextRef.current }]);
    }

    wsRef.current?.send(JSON.stringify({
      type: 'answer_complete',
      data: { text: answerTextRef.current },
    }));
  }, []);

  const startRecording = useCallback(async () => {
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
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({
                type: 'audio_chunk',
                data: { chunk: base64, sequence: sequenceRef.current++ },
              }));
            }
          };
          reader.readAsDataURL(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        // When recording stops, ensure last chunk is processed, then submit
        setTimeout(() => {
          // Only finalize if we are still in an active answering phase (or user initiated finish)
          // We rely on the caller to change phase if needed, mostly this is for auto-submit
          finalizeSubmission();
        }, 500);
      };

      mediaRecorder.start(1000); // 1 second chunks
      setRecording(true);
    } catch {
      toast.error('Microphone access denied');
    }
  }, [finalizeSubmission]);

  const submitAnswer = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      stopRecording();
    } else {
      finalizeSubmission();
    }
  }, [stopRecording, finalizeSubmission]);

  const handleFinishConfirm = () => {
    setShowFinishModal(false);
    stopRecording();
    // Send current partial answer if any (only if answering)
    if (phase === 'answering') {
      wsRef.current?.send(JSON.stringify({
        type: 'answer_complete',
        data: { text: answerText },
      }));
    }
    // Send finish signal
    setTimeout(() => {
      wsRef.current?.send(JSON.stringify({
        type: 'request_finish',
        data: {}
      }));
    }, 500);
  };

  const handleWSMessage = useCallback((msg: WSMessage) => {
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
        if (msg.data.phase === 'answering') {
          if (phaseRef.current !== 'answering') {
            setPhase('answering');
            startRecording();
          }
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

      case 'terminated':
        setPhase('terminated');
        toast.error(msg.data.message, { duration: 6000 });
        break;

      case 'restore_state':
        const state = msg.data;
        if (state.question) {
          setCurrentQuestion(state.question);
          setQuestionsAnswered(state.question.question_number - 1);
        }

        if (state.transcript) {
          setTranscript(state.transcript);
        }

        if (state.phase === 'reading') {
          setPhase('reading');
          setTimeLeft(state.time_left);
        } else if (state.phase === 'answering') {
          setPhase('answering');
          setTimeLeft(state.time_left);
          startRecording();
        } else {
          setPhase('idle');
        }
        toast.success('Session restored');
        break;
    }
  }, [startRecording, submitAnswer]);

  // WebSocket Connection
  useEffect(() => {
    if (permissionStatus !== 'granted' || !interviewId) return;

    // Use direct connection to backend
    const wsUrl = `ws://127.0.0.1:8000/api/interviews/ws/${interviewId}`;
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

    ws.onclose = (event) => {
      console.warn('WebSocket Closed:', event.code, event.reason);
      setConnected(false);
      // Only show error if not normal closure or page navigation
      if (event.code !== 1000 && event.code !== 1001) {
        // toast.error(`Connection lost (${event.code})`);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket Error:', error);
      // toast.error('WebSocket connection error');
    };

    return () => {
      ws.close();
    };
  }, [interviewId, permissionStatus, handleWSMessage]);

  // Tab Visibility Tracking
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && connected && phase !== 'complete' && phase !== 'idle') {
        wsRef.current?.send(JSON.stringify({
          type: 'violation',
          data: { reason: 'tab_switch' }
        }));
        toast.error("Warning: Tab switching is monitored and counts as a violation.");
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [connected, phase]);

  // Timer Actions (Client-side backup)
  useEffect(() => {
    if (phase === 'idle' || phase === 'complete' || phase === 'processing' || phase === 'terminated') return;

    if (timeLeft === 0) {
      if (phase === 'reading') {
        setPhase('answering');
        setTimeLeft(currentQuestion?.answer_time_seconds || 60);
        startRecording();
      } else if (phase === 'answering') {
        submitAnswer();
      }
      return;
    }

    const timer = setInterval(() => {
      setTimeLeft((t) => t - 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [timeLeft, phase, currentQuestion, startRecording, submitAnswer]);

  const startInterview = async () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        await document.documentElement.requestFullscreen();
      } catch (err) {
        console.error("Full screen denied:", err);
      }
      wsRef.current.send(JSON.stringify({ type: 'start', data: {} }));
    } else {
      toast.error('WebSocket not connected');
    }
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

  if (phase === 'terminated') {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <AlertTriangle className="w-20 h-20 text-red-500 mx-auto mb-6" />
        <h1 className="text-3xl font-bold mb-4 text-red-600">Interview Terminated</h1>
        <p className="text-gray-600 mb-2">
          This session has been terminated due to multiple integrity violations.
        </p>
        <p className="text-gray-500 mb-8">
          A report has been generated and sent to the recruitment team.
        </p>
        <div className="flex gap-4 justify-center">
          <button className="btn-primary bg-gray-600 hover:bg-gray-700" onClick={() => navigate('/candidates')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (permissionStatus === 'checking') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mb-4" />
        <p className="text-gray-600">Checking microphone permissions...</p>
      </div>
    );
  }

  if (permissionStatus === 'denied') {
    return (
      <div className="max-w-md mx-auto text-center py-20 px-4">
        <MicOff className="w-16 h-16 text-red-500 mx-auto mb-6" />
        <h2 className="text-2xl font-bold mb-4">Microphone Access Required</h2>
        <p className="text-gray-600 mb-8">
          To proceed with the interview, we need access to your microphone.
          Please enable microphone permissions in your browser settings and refresh the page.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="btn-primary"
        >
          Try Again
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 relative">
      {/* Finish Confirmation Modal */}
      {showFinishModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 animate-in fade-in zoom-in duration-200">
            <div className="flex items-center gap-3 text-red-600 mb-4">
              <div className="p-3 bg-red-100 rounded-full">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold">End Interview?</h3>
            </div>

            <p className="text-gray-600 mb-6">
              Are you sure you want to finish the interview now?
              Any incomplete answer will be submitted as-is.
              This action cannot be undone.
            </p>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowFinishModal(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleFinishConfirm}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium shadow-sm transition-colors flex items-center gap-2"
              >
                Yes, Finish Interview
              </button>
            </div>
          </div>
        </div>
      )}

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
        <div className="text-right flex items-center gap-4">
          <button
            onClick={() => setShowFinishModal(true)}
            className="text-red-600 hover:text-red-700 font-medium text-sm px-3 py-2 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
            disabled={!connected}
          >
            Finish Interview
          </button>
          <div>
            <p className="text-sm text-gray-500">Questions Answered</p>
            <p className="text-2xl font-bold">{questionsAnswered}</p>
          </div>
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
          <button
            className="btn-primary text-lg px-8 py-3 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={startInterview}
            disabled={!connected}
          >
            {connected ? 'Start Interview' : 'Connecting...'}
          </button>
        </div>
      )}

      {(phase === 'reading' || phase === 'answering' || phase === 'processing') && currentQuestion && (
        <div className="space-y-6">
          {/* Timer Bar */}
          <div className={`rounded-xl p-4 flex items-center justify-between ${phase === 'reading' ? 'bg-blue-50 border border-blue-200' :
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
            <span className={`text-2xl font-bold font-mono ${timeLeft <= 10 ? 'text-red-600' : ''
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

          {/* Answer Area - Voice Only */}
          {phase === 'answering' && (
            <div className="card flex flex-col items-center justify-center py-10 space-y-6">

              {!recording ? (
                <div className="flex flex-col items-center gap-2">
                  <span className="relative flex h-6 w-6">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-6 w-6 bg-green-500"></span>
                  </span>
                  <p className="text-gray-600 font-medium">Recording will start automatically...</p>
                </div>
              ) : (
                <>
                  <div className="flex flex-col items-center gap-2">
                    <span className="relative flex h-6 w-6">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-6 w-6 bg-red-500"></span>
                    </span>
                    <p className="text-red-600 font-medium animate-pulse">Recording ({formatTime(timeLeft)})...</p>
                  </div>

                  <button
                    className="btn-primary bg-green-600 hover:bg-green-700 flex items-center gap-2 px-8 py-4 text-lg"
                    onClick={() => {
                      // Explicitly stop and submit
                      stopRecording();
                      setPhase('processing');
                      setQuestionsAnswered((q) => q + 1);
                      if (currentQuestion) {
                        setTranscript((p) => [...p, { q: currentQuestion.question_text, a: answerText }]);
                      }
                      wsRef.current?.send(JSON.stringify({
                        type: 'answer_complete',
                        data: { text: '' },
                      }));
                    }}
                  >
                    <CheckCircle className="w-6 h-6" /> Submit & Next
                  </button>
                </>
              )}
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
