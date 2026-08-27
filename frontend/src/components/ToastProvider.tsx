'use client';

import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
  confirm: (message: string) => Promise<boolean>;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

const TYPE_STYLES: Record<ToastType, { border: string; icon: string; iconBg: string }> = {
  success: { border: 'border-emerald-500/40', icon: 'text-emerald-400', iconBg: 'bg-emerald-500/10' },
  error: { border: 'border-rose-500/40', icon: 'text-rose-400', iconBg: 'bg-rose-500/10' },
  warning: { border: 'border-amber-500/40', icon: 'text-amber-400', iconBg: 'bg-amber-500/10' },
  info: { border: 'border-sky-500/40', icon: 'text-sky-400', iconBg: 'bg-sky-500/10' },
};

const TYPE_ICONS = {
  success: CheckCircle2,
  error: AlertTriangle,
  warning: AlertTriangle,
  info: Info,
};

export default function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmState, setConfirmState] = useState<{ message: string; resolve: (v: boolean) => void } | null>(null);
  const idRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++idRef.current;
    setToasts((prev) => [...prev, { id, type, message }].slice(-5));
    window.setTimeout(() => dismiss(id), 5000);
  }, [dismiss]);

  const confirm = useCallback((message: string) => {
    return new Promise<boolean>((resolve) => {
      setConfirmState({ message, resolve });
    });
  }, []);

  const resolveConfirm = (value: boolean) => {
    if (confirmState) {
      confirmState.resolve(value);
      setConfirmState(null);
    }
  };

  return (
    <ToastContext.Provider value={{ toast, confirm }}>
      {children}

      {/* Toast stack — fixed top-right */}
      <div className="fixed top-4 right-4 z-[3000] flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
        {toasts.map((t) => {
          const style = TYPE_STYLES[t.type];
          const Icon = TYPE_ICONS[t.type];
          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 p-3 rounded-lg bg-slate-900/95 backdrop-blur border ${style.border} shadow-xl animate-fade-in`}
              role="alert"
            >
              <span className={`mt-0.5 shrink-0 p-1 rounded ${style.iconBg}`}>
                <Icon className={`w-4 h-4 ${style.icon}`} />
              </span>
              <p className="flex-1 text-xs text-slate-200 leading-relaxed break-words">{t.message}</p>
              <button
                onClick={() => dismiss(t.id)}
                className="shrink-0 p-0.5 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
                aria-label="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Confirm dialog */}
      {confirmState && (
        <div className="fixed inset-0 z-[3500] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-sm glass-panel overflow-hidden border border-white/10 shadow-2xl animate-fade-in-up">
            <div className="p-4 border-b border-white/10 bg-slate-900/40">
              <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Confirm Action
              </h2>
            </div>
            <div className="p-5">
              <p className="text-xs text-slate-300 leading-relaxed">{confirmState.message}</p>
              <div className="flex gap-2 mt-5">
                <button
                  onClick={() => resolveConfirm(false)}
                  className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold rounded-lg text-xs cursor-pointer transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => resolveConfirm(true)}
                  className="flex-1 py-2 bg-rose-500 hover:bg-rose-600 text-slate-950 font-bold rounded-lg text-xs cursor-pointer transition-colors shadow-lg shadow-rose-500/20"
                >
                  Confirm
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </ToastContext.Provider>
  );
}
