'use client';

import React, { useState } from 'react';
import { X, Shield, Lock, User, AlertCircle, Play, UserPlus, LogIn, Mail } from 'lucide-react';

interface AdminPanelProps {
  apiBaseUrl: string;
  onClose: () => void;
  onLoginSuccess: (token: string, role: string) => void;
}

export default function AdminPanel({ apiBaseUrl, onClose, onLoginSuccess }: AdminPanelProps) {
  const [tab, setTab] = useState<'login' | 'register'>('login');

  // Login fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Register fields
  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regConfirm, setRegConfirm] = useState('');
  const [registering, setRegistering] = useState(false);

  // Resolve the UI role from the authenticated user's /me profile
  const completeAuth = async (token: string, fallbackRole = 'Super Admin') => {
    try {
      const res = await fetch(`${apiBaseUrl}/auth/me/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        onLoginSuccess(token, data.role || fallbackRole);
        return;
      }
    } catch (err) {
      console.warn("Could not fetch user profile, using fallback role.", err);
    }
    onLoginSuccess(token, fallbackRole);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${apiBaseUrl}/auth/token/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      if (!res.ok) {
        throw new Error("Invalid username or password credentials.");
      }

      const data = await res.json();
      await completeAuth(data.access);
    } catch (err: any) {
      setError(err.message || "Failed to connect to authentication server.");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (regPassword !== regConfirm) {
      setError("Passwords do not match.");
      return;
    }
    if (regPassword.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    setRegistering(true);

    try {
      const res = await fetch(`${apiBaseUrl}/auth/register/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: regUsername,
          email: regEmail,
          password: regPassword
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Registration failed.");
      }

      // Auto-login the newly created Registered User account
      onLoginSuccess(data.access, data.role || 'Registered User');
    } catch (err: any) {
      setError(err.message || "Failed to connect to registration server.");
    } finally {
      setRegistering(false);
    }
  };

  // Helper to bypass real login during quick local/front-end demos
  const handleBypass = () => {
    onLoginSuccess("mocked_jwt_token_for_presentation_mode", "Super Admin");
  };

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fade-in">
      
      {/* Modal Container */}
      <div className="w-full max-w-sm glass-panel overflow-hidden border border-white/10 shadow-2xl">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-sky-400" />
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Council Access</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b border-white/10 text-xs font-semibold">
          <button
            type="button"
            onClick={() => { setTab('login'); setError(null); }}
            className={`flex-1 py-2.5 text-center flex items-center justify-center gap-1.5 cursor-pointer transition-colors ${tab === 'login' ? 'bg-white/5 text-white border-b-2 border-sky-400' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>Login</span>
          </button>
          <button
            type="button"
            onClick={() => { setTab('register'); setError(null); }}
            className={`flex-1 py-2.5 text-center flex items-center justify-center gap-1.5 cursor-pointer transition-colors ${tab === 'register' ? 'bg-white/5 text-white border-b-2 border-sky-400' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>Create Account</span>
          </button>
        </div>

        {/* Body */}
        {tab === 'login' ? (
          <form onSubmit={handleLogin} className="p-5 space-y-4">
            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {/* Username Input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Username</label>
              <div className="relative">
                <User className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. admin"
                  className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200"
                />
              </div>
            </div>

            {/* Password Input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200"
                />
              </div>
            </div>

            {/* Action button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-sky-500 hover:bg-sky-600 disabled:bg-sky-700 text-slate-950 font-bold rounded-lg text-xs cursor-pointer transition-colors shadow-lg shadow-sky-500/20"
            >
              {loading ? "Authenticating..." : "Login"}
            </button>

            {/* Separator */}
            <div className="relative flex py-2 items-center">
              <div className="flex-grow border-t border-white/5"></div>
              <span className="flex-shrink mx-3 text-[9px] font-mono uppercase text-slate-600 tracking-wider">or test locally</span>
              <div className="flex-grow border-t border-white/5"></div>
            </div>

            {/* Bypass Button */}
            <button
              type="button"
              onClick={handleBypass}
              className="w-full py-2.5 bg-slate-900 hover:bg-slate-800 border border-white/5 text-amber-400 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
            >
              <Play className="w-3.5 h-3.5 fill-amber-400" />
              <span>Simulate Admin Mode (Bypass)</span>
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister} className="p-5 space-y-4">
            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <p className="text-[11px] text-slate-500 leading-relaxed">
              Self-registration creates a <b className="text-sky-400">Registered User</b> account with read-only map access. Staff accounts are provisioned by the council.
            </p>

            {/* Username Input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Username</label>
              <div className="relative">
                <User className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
                <input
                  type="text"
                  required
                  value={regUsername}
                  onChange={(e) => setRegUsername(e.target.value)}
                  placeholder="e.g. resident"
                  className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200"
                />
              </div>
            </div>

            {/* Email Input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Email (optional)</label>
              <div className="relative">
                <Mail className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
                <input
                  type="email"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  placeholder="e.g. resident@island.mv"
                  className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200"
                />
              </div>
            </div>

            {/* Password Input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
                <input
                  type="password"
                  required
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  placeholder="Minimum 8 characters"
                  className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200"
                />
              </div>
            </div>

            {/* Confirm Password Input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Confirm Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 w-4.5 h-4.5 text-slate-500" />
                <input
                  type="password"
                  required
                  value={regConfirm}
                  onChange={(e) => setRegConfirm(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200"
                />
              </div>
            </div>

            {/* Action button */}
            <button
              type="submit"
              disabled={registering}
              className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-800 disabled:text-slate-600 text-slate-950 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 cursor-pointer transition-colors shadow-lg shadow-emerald-500/20"
            >
              <UserPlus className="w-3.5 h-3.5" />
              <span>{registering ? "Creating Account..." : "Create Account"}</span>
            </button>
          </form>
        )}

      </div>
    </div>
  );
}
