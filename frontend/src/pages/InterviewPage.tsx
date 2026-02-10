import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  MicOff, Clock, AlertTriangle, CheckCircle, AlertCircle,
  XCircle, Radio, Play
} from 'lucide-react';
import toast from 'react-hot-toast';
import type { InterviewQuestion, WSMessage } from '../types';
import { getCandidateSession } from './candidate/CandidateLoginPage';
import { Badge, Button, Card, Loader } from '../components/ui';

type Phase = 'idle' | 'reading' | 'answering' | 'processing' | 'complete' | 'terminated';

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
  const [permissionStatus, setPermissionStatus] = useState<'checking' | 'granted' | 'denied'>('checking');
  const [showFinishModal, setShowFinishModal] = useState(false);

  const phaseRef = useRef(phase);
  const currentQuestionRef = useRef(currentQuestion);
  const answerTextRef = useRef(answerText);

  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { currentQuestionRef.current = currentQuestion; }, [currentQuestion]);
  useEffect(() => { answerTextRef.current = answerText; }, [answerText]);

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
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 48000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });

      const mimeType = 'audio/ogg; codecs=opus';

      if (!MediaRecorder.isTypeSupported(mimeType)) {
        toast.error('Browser does not support required audio format (ogg-opus). Please use Chrome, Firefox, or Edge.');
        stream.getTracks().forEach(t => t.stop());
        return;
      }

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 48000,
      });

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
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
        setTimeout(() => {
          finalizeSubmission();
        }, 500);
      };

      mediaRecorder.start(250);
      setRecording(true);
    } catch (err) {
      toast.error('Microphone access denied');
      console.error('Recording error:', err);
    }
  }, [finalizeSubmission]);

  const submitAnswer = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      stopRecording();
    } else {
      finalizeSubmission();
    }
  }, [stopRecording, finalizeSubmission]);

  const handleFinishInterview = () => {
    setShowFinishModal(true);
  };

  const handleFinishConfirm = () => {
    setShowFinishModal(false);
    stopRecording();

    if (phase === 'answering') {
      wsRef.current?.send(JSON.stringify({
        type: 'answer_complete',
        data: { text: answerText },
      }));
    }

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

      case 'warning':
        toast.error(msg.data.message, { duration: 4000 });
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

      case 'restore_state': {
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

      case 'transcript_partial':
        setAnswerText(msg.data.text);
        break;
    }
  }, [startRecording, submitAnswer]);

  useEffect(() => {
    if (permissionStatus !== 'granted' || !interviewId) return;

    const candidateSession = getCandidateSession();
    let wsUrl = '';

    if (candidateSession) {
      wsUrl = `ws://127.0.0.1:8000/api/candidate-portal/ws/${interviewId}?session=${candidateSession.sessionToken}`;
    } else {
      wsUrl = `ws://127.0.0.1:8000/api/interviews/ws/${interviewId}`;
    }

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
      setConnected(false);

      if (event.code === 4003) {
        toast.error('Session expired or invalid. Please login again.');
        navigate('/candidate/login');
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket Error:', error);
    };

    return () => {
      ws.close();
    };
  }, [interviewId, permissionStatus, handleWSMessage, navigate]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && connected && phase !== 'complete' && phase !== 'idle') {
        wsRef.current?.send(JSON.stringify({
          type: 'violation',
          data: { reason: 'tab_switch' }
        }));
        toast.error('Warning: Tab switching is monitored and counts as a violation.');
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [connected, phase]);

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
        console.error('Full screen denied:', err);
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
      <div className="min-h-screen bg-slate-100 px-4 py-10">
        <div className="mx-auto max-w-2xl">
          <Card className="text-center">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
              <CheckCircle className="h-8 w-8 text-emerald-600" />
            </div>
            <h1 className="text-3xl font-semibold text-slate-900">Interview complete</h1>
            <p className="mt-3 text-slate-600">
              You answered <span className="font-semibold text-slate-900">{questionsAnswered}</span> questions.
            </p>
            {cheatingWarnings.length > 0 ? (
              <p className="mt-2 text-sm text-amber-700">
                {cheatingWarnings.length} integrity warning(s) were recorded.
              </p>
            ) : null}
            <p className="mt-2 text-sm text-slate-500">Your responses are now being evaluated.</p>
            <div className="mt-8">
              <Button onClick={() => navigate('/candidate/portal')}>Back to portal</Button>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  if (phase === 'terminated') {
    return (
      <div className="min-h-screen bg-slate-100 px-4 py-10">
        <div className="mx-auto max-w-2xl">
          <Card className="text-center">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-rose-100">
              <XCircle className="h-8 w-8 text-rose-600" />
            </div>
            <h1 className="text-3xl font-semibold text-rose-700">Interview terminated</h1>
            <p className="mt-3 text-slate-600">This session ended due to multiple integrity violations.</p>
            <div className="mt-8">
              <Button variant="danger" onClick={() => navigate('/candidate/portal')}>Return to portal</Button>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  if (permissionStatus === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <Loader label="Checking microphone permissions" />
      </div>
    );
  }

  if (permissionStatus === 'denied') {
    return (
      <div className="min-h-screen bg-slate-100 px-4 py-10">
        <div className="mx-auto max-w-md">
          <Card className="text-center">
            <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-rose-100">
              <MicOff className="h-7 w-7 text-rose-600" />
            </div>
            <h2 className="text-xl font-semibold text-slate-900">Microphone access required</h2>
            <p className="mt-2 text-sm text-slate-600">
              Enable microphone permissions in your browser and try again.
            </p>
            <div className="mt-6">
              <Button className="w-full" onClick={() => window.location.reload()}>Try Again</Button>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-6 lg:py-8">
      {showFinishModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <Card className="w-full max-w-md">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-100">
                <AlertCircle className="h-5 w-5 text-rose-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">End interview early?</h3>
            </div>
            <p className="text-sm text-slate-600">
              This will submit your current response and end the session. This action cannot be undone.
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <Button variant="secondary" onClick={() => setShowFinishModal(false)}>Cancel</Button>
              <Button variant="danger" onClick={handleFinishConfirm}>Finish now</Button>
            </div>
          </Card>
        </div>
      ) : null}

      <div className="mx-auto max-w-5xl space-y-4">
        <Card>
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-slate-900">Interview Session</h1>
              <div className="mt-2 flex items-center gap-3 text-sm text-slate-600">
                <span className="inline-flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  {connected ? 'Connected' : 'Disconnected'}
                </span>
                <span>•</span>
                <span>Question {phase === 'idle' ? questionsAnswered : questionsAnswered + 1}</span>
                <span>•</span>
                <span>{transcript.length} submitted</span>
              </div>
            </div>
            <Button
              variant="danger"
              onClick={handleFinishInterview}
              disabled={!connected || phase === 'idle'}
            >
              Finish Interview Early
            </Button>
          </div>
        </Card>

        {cheatingWarnings.length > 0 ? (
          <Card className="border-amber-200 bg-amber-50">
            <div className="mb-2 flex items-center gap-2 text-amber-700">
              <AlertTriangle className="h-4 w-4" />
              <p className="text-sm font-semibold">Integrity warnings ({cheatingWarnings.length})</p>
            </div>
            <div className="space-y-1.5 pl-6 text-sm text-amber-800">
              {cheatingWarnings.map((warning, index) => (
                <p key={index}>{warning}</p>
              ))}
            </div>
          </Card>
        ) : null}

        {phase === 'idle' ? (
          <Card className="py-14 text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-primary-100">
              <Play className="h-8 w-8 text-primary-700" />
            </div>
            <h2 className="text-2xl font-semibold text-slate-900">Ready to begin?</h2>
            <p className="mx-auto mt-3 max-w-xl text-sm text-slate-600">
              You will receive AI-generated questions one by one. Read carefully, then answer clearly when recording starts.
            </p>
            <div className="mt-8">
              <Button onClick={startInterview} disabled={!connected}>
                {connected ? 'Start interview' : 'Connecting...'}
              </Button>
            </div>
          </Card>
        ) : null}

        {(phase === 'reading' || phase === 'answering' || phase === 'processing') && currentQuestion ? (
          <>
            <Card className={phase === 'answering' ? 'border-secondary-200 bg-secondary-50/50' : phase === 'reading' ? 'border-blue-200 bg-blue-50/50' : ''}>
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100">
                    <Clock className="h-5 w-5 text-slate-700" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {phase === 'reading' ? 'Reading time' : phase === 'answering' ? 'Answer time' : 'Processing'}
                    </p>
                    <p className="text-sm text-slate-700">
                      {phase === 'reading' ? 'Read the question before answering.' : phase === 'answering' ? 'Speak your response clearly.' : 'Analyzing your response...'}
                    </p>
                  </div>
                </div>
                <p className={`text-4xl font-semibold tabular-nums ${timeLeft <= 10 ? 'text-rose-600' : 'text-slate-900'}`}>
                  {formatTime(timeLeft)}
                </p>
              </div>
            </Card>

            <Card>
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Badge variant="info">{currentQuestion.pillar}</Badge>
                <Badge variant="neutral">Question {currentQuestion.question_number}</Badge>
                {currentQuestion.is_follow_up ? <Badge variant="warning">Follow-up</Badge> : null}
              </div>
              <p className="text-xl font-medium leading-relaxed text-slate-900">{currentQuestion.question_text}</p>
            </Card>

            {phase === 'answering' ? (
              <Card>
                {!recording ? (
                  <div className="py-10 text-center">
                    <Loader className="justify-center" label="Starting microphone recording" />
                  </div>
                ) : (
                  <>
                    <div className="mb-5 flex items-center justify-center gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3">
                      <span className="relative flex h-3 w-3">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-500 opacity-75" />
                        <span className="relative inline-flex h-3 w-3 rounded-full bg-rose-600" />
                      </span>
                      <p className="text-sm font-semibold text-rose-700">Recording in progress • {formatTime(timeLeft)} remaining</p>
                    </div>

                    <div className="min-h-[140px] rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                        <Radio className="h-3.5 w-3.5" />
                        Live transcript
                      </div>
                      <p className="text-sm leading-relaxed text-slate-700">{answerText || 'Listening...'}</p>
                    </div>

                    <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <Button onClick={submitAnswer}>
                        <CheckCircle className="h-4 w-4" />
                        Submit Answer
                      </Button>
                      <Button variant="secondary" onClick={handleFinishInterview}>
                        <XCircle className="h-4 w-4" />
                        End Interview
                      </Button>
                    </div>
                  </>
                )}
              </Card>
            ) : null}

            {phase === 'processing' ? (
              <Card className="py-10 text-center">
                <Loader className="justify-center" label="AI is analyzing your answer" />
              </Card>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
