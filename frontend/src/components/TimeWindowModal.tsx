import React, { useState, useEffect } from 'react';
import { X, Calendar, Clock, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import type { Candidate } from '../types';
import { getAuthHeader } from '../store/AuthContext';

interface TimeWindowModalProps {
  candidate: Candidate;
  onClose: () => void;
  onSuccess: () => void;
}

export default function TimeWindowModal({ candidate, onClose, onSuccess }: TimeWindowModalProps) {
  const [startDate, setStartDate] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endDate, setEndDate] = useState('');
  const [endTime, setEndTime] = useState('');
  const [sendNotification, setSendNotification] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [removeWindow, setRemoveWindow] = useState(false);

  useEffect(() => {
    // Pre-fill with existing time window if present
    if (candidate.interview_window_start) {
      const start = new Date(candidate.interview_window_start);
      setStartDate(start.toISOString().split('T')[0]);
      setStartTime(start.toTimeString().slice(0, 5));
    }
    if (candidate.interview_window_end) {
      const end = new Date(candidate.interview_window_end);
      setEndDate(end.toISOString().split('T')[0]);
      setEndTime(end.toTimeString().slice(0, 5));
    }
  }, [candidate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      let interview_window_start = null;
      let interview_window_end = null;

      if (!removeWindow) {
        // Validate dates
        if (!startDate || !startTime || !endDate || !endTime) {
          toast.error('Please fill in all date and time fields');
          setSubmitting(false);
          return;
        }

        interview_window_start = new Date(`${startDate}T${startTime}`).toISOString();
        interview_window_end = new Date(`${endDate}T${endTime}`).toISOString();

        // Validate that start < end
        if (interview_window_start >= interview_window_end) {
          toast.error('Start time must be before end time');
          setSubmitting(false);
          return;
        }
      }

      const response = await fetch(`/api/candidates/${candidate.candidate_id}/time-window`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({
          interview_window_start,
          interview_window_end,
          send_notification: sendNotification,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update time window');
      }

      toast.success(removeWindow ? 'Time window removed' : 'Time window updated successfully');
      onSuccess();
      onClose();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update time window';
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  const hasExistingWindow = !!(candidate.interview_window_start && candidate.interview_window_end);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Manage Interview Time Window
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Candidate Info */}
          <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-200">
              <strong>Candidate:</strong> {candidate.name} ({candidate.email})
            </p>
            {hasExistingWindow && !removeWindow && (
              <div className="mt-2 text-xs text-blue-700 dark:text-blue-300">
                <p className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  Current window: {new Date(candidate.interview_window_start!).toLocaleString()} - {new Date(candidate.interview_window_end!).toLocaleString()}
                </p>
              </div>
            )}
          </div>

          {/* Remove Window Checkbox */}
          {hasExistingWindow && (
            <div className="flex items-start gap-3 p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
              <input
                type="checkbox"
                id="removeWindow"
                checked={removeWindow}
                onChange={(e) => setRemoveWindow(e.target.checked)}
                className="mt-1"
              />
              <label htmlFor="removeWindow" className="flex-1 text-sm text-yellow-800 dark:text-yellow-200 cursor-pointer">
                <strong>Remove time window restriction</strong>
                <p className="mt-1 text-xs">
                  Candidate will be able to access the interview anytime before session expiry.
                </p>
              </label>
            </div>
          )}

          {/* Time Window Fields */}
          {!removeWindow && (
            <>
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  Interview Time Window
                </h3>

                {/* Start Date/Time */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Start Date
                    </label>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="input-field w-full"
                      required={!removeWindow}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Start Time
                    </label>
                    <input
                      type="time"
                      value={startTime}
                      onChange={(e) => setStartTime(e.target.value)}
                      className="input-field w-full"
                      required={!removeWindow}
                    />
                  </div>
                </div>

                {/* End Date/Time */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      End Date
                    </label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="input-field w-full"
                      required={!removeWindow}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      End Time
                    </label>
                    <input
                      type="time"
                      value={endTime}
                      onChange={(e) => setEndTime(e.target.value)}
                      className="input-field w-full"
                      required={!removeWindow}
                    />
                  </div>
                </div>

                {/* Helper Text */}
                <div className="bg-gray-50 dark:bg-gray-700 p-3 rounded-lg text-xs text-gray-600 dark:text-gray-400 flex items-start gap-2">
                  <Clock className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <div>
                    <p>The candidate will only be able to access the interview during this time window.</p>
                    <p className="mt-1 text-gray-500 dark:text-gray-500">All times are in your local timezone and will be converted to UTC.</p>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Send Notification */}
          <div className="flex items-start gap-3">
            <input
              type="checkbox"
              id="sendNotification"
              checked={sendNotification}
              onChange={(e) => setSendNotification(e.target.checked)}
              className="mt-1"
            />
            <label htmlFor="sendNotification" className="flex-1 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <strong>Send email notification to candidate</strong>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Candidate will receive an email about the time window change.
              </p>
            </label>
          </div>

          {/* Warning if missed window */}
          {hasExistingWindow && candidate.interview_window_end && new Date(candidate.interview_window_end) < new Date() && (
            <div className="bg-red-50 dark:bg-red-900/20 p-4 rounded-lg flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1 text-sm text-red-800 dark:text-red-200">
                <strong>Time window has expired</strong>
                <p className="mt-1 text-xs">
                  The candidate's time window has already passed. Update or remove it to give them access.
                </p>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary flex-1"
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary flex-1"
              disabled={submitting}
            >
              {submitting ? 'Updating...' : removeWindow ? 'Remove Window' : 'Update Time Window'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
