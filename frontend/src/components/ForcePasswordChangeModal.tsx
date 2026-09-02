'use client';

import React, { useState } from 'react';
import { X, KeyRound, Lock, AlertCircle, LogOut, Save } from 'lucide-react';

interface ForcePasswordChangeModalProps {
  apiBaseUrl: string;
  token: string;
  onSuccess: () => void;
  onLogout: () => void;
}

export default function ForcePasswordChangeModal({ apiBaseUrl, token, onSuccess, onLogout }: ForcePasswordChangeModalProps) {
  const [current, setCurrent] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!newPw) {
      setError('New password is required.');
      return;
    }
    if (newPw.length < 8) {
      setError('New password must be at least 8 characters long.');
      return;
    }
    if (newPw !== confirmPw) {
      setError('New passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/change-password/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          current_password: current,
          new_password: newPw,
          confirm_password: confirmPw
        })
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        if (data.errors && Array.isArray(data.errors)) {
          setError(data.errors.join(' '));
        } else {
          setError(data.error || data.detail || "Could not update password.");
        }
        setLoading(false);
        return;
      }

      setLoading(false);
      onSuccess();
    } catch (err: any) {
      setError(err.message || "Network error updating password.");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[2500] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-sm glass-panel overflow-hidden border border-amber-500/25 shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Password Change Required</h2>
          </div>
          <button
            onClick={onLogout}
            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
            title="Log out"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={submit} className="p-5 space-y-4">
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Your password was reset by a council administrator. For security, you must set a new
            password before continuing to use the platform.
          </p>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Current Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
              <input
                type="password"
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                placeholder="Temporary password"
                className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-amber-400 focus:outline-none rounded-lg text-xs text-slate-200"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">New Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
              <input
                type="password"
                required
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                placeholder="Minimum 8 characters"
                className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-amber-400 focus:outline-none rounded-lg text-xs text-slate-200"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Confirm New Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
              <input
                type="password"
                required
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-amber-400 focus:outline-none rounded-lg text-xs text-slate-200"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-700 text-slate-950 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 cursor-pointer transition-colors shadow-lg shadow-amber-500/20"
          >
            <Save className="w-3.5 h-3.5" />
            {loading ? "Updating..." : "Update Password"}
          </button>

          <button
            type="button"
            onClick={onLogout}
            className="w-full py-2 bg-slate-900 hover:bg-slate-800 border border-white/5 text-slate-400 font-semibold rounded-lg text-xs flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Log out instead</span>
          </button>
        </form>

      </div>
    </div>
  );
}