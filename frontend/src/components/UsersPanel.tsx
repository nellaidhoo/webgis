'use client';

import React, { useState, useEffect } from 'react';
import { X, Users, KeyRound, RefreshCw, Search, ShieldCheck, AlertTriangle, Inbox } from 'lucide-react';
import { useToast } from './ToastProvider';

interface UsersPanelProps {
  apiBaseUrl: string;
  token: string | null;
  onClose: () => void;
}

interface UserRecord {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_superuser: boolean;
  last_login: string | null;
  date_joined: string | null;
  roles: string[];
  role: string;
  must_change_password: boolean;
}

const ROLE_BADGE: Record<string, string> = {
  'Super Admin': 'border-sky-500/30 bg-sky-500/10 text-sky-400',
  'Section Admin': 'border-violet-500/30 bg-violet-500/10 text-violet-400',
  'Council Staff': 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
  'Registered User': 'border-slate-500/30 bg-slate-500/10 text-slate-400',
};

export default function UsersPanel({ apiBaseUrl, token, onClose }: UsersPanelProps) {
  const { toast, confirm } = useToast();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [currentUsername, setCurrentUsername] = useState<string | null>(null);
  const [resettingId, setResettingId] = useState<number | null>(null);
  const [tempPasswords, setTempPasswords] = useState<Record<number, string>>({});

  const authHeaders: Record<string, string> = {};
  if (token) authHeaders['Authorization'] = `Bearer ${token}`;

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/users/`, { headers: authHeaders });
      if (res.ok) {
        setUsers(await res.json());
      } else {
        toast(`Failed to load users (HTTP ${res.status})`, 'error');
      }
    } catch {
      toast('Failed to connect to the accounts service.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const load = async () => {
      await fetchUsers();
      try {
        const me = await fetch(`${apiBaseUrl}/auth/me/`, { headers });
        if (me.ok) {
          const data = await me.json();
          setCurrentUsername(data.user?.username || null);
        }
      } catch {
        /* console only: /me is best-effort here */
      }
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, token]);

  const filtered = users.filter(
    (u) =>
      u.username.toLowerCase().includes(query.toLowerCase()) ||
      (u.email || '').toLowerCase().includes(query.toLowerCase())
  );

  const handleReset = async (user: UserRecord) => {
    const ok = await confirm(
      `Reset the password for "${user.username}"?\n\nA temporary password will be generated and the account will be forced to change it at next login.`
    );
    if (!ok) return;

    setResettingId(user.id);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/reset-password/${user.id}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
      });
      if (!res.ok) {
        throw new Error(`Reset failed (HTTP ${res.status})`);
      }
      const data: { temp_password?: string } = await res.json();
      setTempPasswords((prev) => ({ ...prev, [user.id]: data.temp_password || '' }));
      toast(`Password reset for "${user.username}".`, 'success');
      fetchUsers();
    } catch (err) {
      toast(`Reset failed: ${err instanceof Error ? err.message : 'unknown error'}`, 'error');
    } finally {
      setResettingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[2100] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl h-[70vh] flex flex-col glass-panel border border-white/10 shadow-2xl overflow-hidden animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-sky-400" />
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Account Management</h2>
            <span className="text-[9px] px-2 py-0.5 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 font-semibold uppercase">
              Super Admin
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-2 p-3 border-b border-white/5">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by username or email..."
              className="w-full pl-9 pr-3 py-2 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200"
            />
          </div>
          <span className="text-[9px] text-slate-500">{filtered.length} account(s)</span>
          <button
            onClick={fetchUsers}
            className="px-2.5 py-2 rounded bg-slate-900 border border-white/5 text-[10px] font-semibold flex items-center gap-1.5 cursor-pointer hover:bg-slate-800 transition-colors"
            title="Refresh accounts"
          >
            <RefreshCw className={`w-3 h-3 text-sky-400 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* User list */}
        <div className="flex-1 overflow-y-auto divide-y divide-white/5">
          {loading && users.length === 0 ? (
            <div className="text-center p-12 text-slate-500 text-xs">
              <RefreshCw className="w-8 h-8 text-slate-600 mx-auto mb-2 animate-spin" />
              <div>Loading accounts...</div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center p-12 text-slate-500 text-xs">
              <Inbox className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <div>No accounts match the current filter.</div>
            </div>
          ) : (
            filtered.map((user) => {
              const isSelf = user.username === currentUsername;
              const temp = tempPasswords[user.id];
              return (
                <div key={user.id} className="p-4 hover:bg-white/[0.02] transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-slate-900 border border-white/10 flex items-center justify-center text-xs font-bold text-sky-400 uppercase shrink-0">
                      {user.username.slice(0, 2)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-100 truncate">{user.username}</span>
                        {!user.is_active && (
                          <span className="text-[8px] px-1.5 py-0.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-400 font-semibold uppercase">
                            Inactive
                          </span>
                        )}
                        {user.must_change_password && (
                          <span className="text-[8px] px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 font-semibold uppercase">
                            Must change
                          </span>
                        )}
                        {isSelf && (
                          <span className="text-[8px] px-1.5 py-0.5 rounded bg-slate-500/10 border border-slate-500/30 text-slate-400 font-semibold uppercase">
                            You
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-500 truncate">{user.email || '—'}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={`text-[9px] px-2 py-0.5 rounded border font-semibold ${ROLE_BADGE[user.role] || 'border-slate-500/30 bg-slate-500/10 text-slate-400'}`}>
                        {user.role}
                      </span>
                      {temp ? (
                        <button
                          onClick={() => setTempPasswords((prev) => {
                            const next = { ...prev };
                            delete next[user.id];
                            return next;
                          })}
                          className="text-[9px] text-slate-500 hover:text-slate-300 cursor-pointer"
                        >
                          Hide temp password
                        </button>
                      ) : (
                        <button
                          onClick={() => handleReset(user)}
                          disabled={resettingId === user.id || isSelf}
                          className="px-2.5 py-1.5 rounded bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 hover:border-rose-500/50 text-[10px] font-semibold flex items-center gap-1 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                          title={isSelf ? 'You cannot reset your own password from this console.' : 'Generate a temporary password and force a change at next login'}
                        >
                          <KeyRound className={`w-3 h-3 text-rose-400 ${resettingId === user.id ? 'animate-pulse' : ''}`} />
                          <span>{resettingId === user.id ? 'Resetting...' : 'Reset Password'}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {temp && (
                    <div className="mt-2.5 rounded-lg border border-amber-500/25 bg-amber-500/5 p-3">
                      <div className="flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                        <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">Temporary password</span>
                      </div>
                      <div className="mt-1.5 font-mono text-sm text-amber-200 bg-slate-950/70 border border-white/5 rounded px-2 py-1.5 select-all">
                        {temp}
                      </div>
                      <p className="text-[9px] text-slate-500 mt-1.5 leading-relaxed">
                        Share this privately with <b className="text-slate-300">{user.username}</b>. The account must change its
                        password at first login — it cannot edit the map until then.
                      </p>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="p-3 border-t border-white/10 bg-slate-900/40 flex items-start gap-2 text-[9px] text-slate-500 leading-relaxed">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-600 shrink-0 mt-0.5" />
          <span>
            Password resets are restricted to Super Admin, are recorded in the audit log, and flag the target account for a
            forced password change on next login.
          </span>
        </div>
      </div>
    </div>
  );
}