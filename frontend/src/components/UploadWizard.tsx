'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, FileText, CheckCircle2, AlertTriangle, XCircle, RefreshCw, Layers, Image as ImageIcon, Loader2 } from 'lucide-react';
import { useToast } from './ToastProvider';

interface UploadWizardProps {
  apiBaseUrl: string;
  token: string | null;
  onUploaded: () => void;
}

interface PrecheckResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  is_duplicate: boolean;
  duplicate_session_id: string | null;
  duplicate_file_name: string | null;
  session_type: string | null;
  md5_checksum: string;
  file_size_bytes: number;
  file_extension: string;
  estimated_feature_count: number;
  predicted_layers: string[];
}

const resolveImportBaseUrl = (apiBaseUrl: string) =>
  process.env.NEXT_PUBLIC_IMPORT_URL || apiBaseUrl.replace('/api', '/api/import');

export default function UploadWizard({ apiBaseUrl, token, onUploaded }: UploadWizardProps) {
  const { toast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [notes, setNotes] = useState('');
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [precheck, setPrecheck] = useState<PrecheckResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [statusLabel, setStatusLabel] = useState('');
  const [logLines, setLogLines] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const importBase = resolveImportBaseUrl(apiBaseUrl);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // Map a session status / job to a progress percentage + label
  const deriveProgress = (status: string, job?: any) => {
    if (job?.status === 'FAILED' || status === 'ERROR') return { pct: 100, label: 'Failed' };
    if (job?.status === 'SUCCESS' || status === 'STAGED' || status === 'COMPLETED' || status === 'APPROVED')
      return { pct: 100, label: status === 'STAGED' || status === 'COMPLETED' ? 'Staged & Ready for Review' : status === 'APPROVED' ? 'Approved' : 'Complete' };
    if (status === 'PROCESSING' || job?.status === 'PROCESSING') return { pct: 45, label: 'Processing...' };
    return { pct: 5, label: 'Queued...' };
  };

  const pollStatus = useCallback(async (sid: string) => {
    try {
      const res = await fetch(`${importBase}/import/status/${sid}`);
      if (!res.ok) return;
      const data = await res.json();
      const { status } = data;
      const job = data.job;
      const { pct, label } = deriveProgress(status, job);
      setProgress(pct);
      setStatusLabel(label);

      // Surface job log (only new content)
      if (job?.log_output) {
        const lines = String(job.log_output).split('\n').filter(Boolean);
        setLogLines((prev) => (prev.length ? prev : lines.slice(-15)));
      }

      // Terminal states (ingestion is done once staged/complete; approval is a separate human step)
      const terminalStatuses = ['STAGED', 'COMPLETED', 'APPROVED', 'ERROR', 'REJECTED'];
      if (pct === 100 || terminalStatuses.includes(status) || job?.status === 'SUCCESS' || job?.status === 'FAILED') {
        stopPolling();
        if (status === 'ERROR' || job?.status === 'FAILED') {
          toast('Processing failed. Check the session logs for details.', 'error');
          setStatusLabel('Failed');
        } else {
          toast('Ingestion completed — staged and ready for review!', 'success');
        }
        onUploaded();
      }
    } catch (err) {
      // transient poll failure — keep polling
    }
  }, [importBase, onUploaded, stopPolling, toast]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const runPrecheck = async (f: File) => {
    setValidating(true);
    try {
      const formData = new FormData();
      formData.append('file', f);
      const res = await fetch(`${importBase}/import/precheck/`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData
      });
      const data = await res.json();
      setPrecheck(data);
      if (data.valid) {
        setStep(2);
      } else {
        setStep(2); // still show the report so errors are visible
      }
    } catch (err: any) {
      toast(`Pre-validation failed: ${err.message || err}`, 'error');
      setPrecheck({ valid: false, errors: ['Could not reach validation service.'], warnings: [], is_duplicate: false, duplicate_session_id: null, duplicate_file_name: null, session_type: null, md5_checksum: '', file_size_bytes: 0, file_extension: f.name.split('.').pop() || '', estimated_feature_count: 0, predicted_layers: [] });
      setStep(2);
    } finally {
      setValidating(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) selectFile(f);
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) selectFile(f);
  };

  const selectFile = (f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase() || '';
    if (!['dxf', 'tif', 'tiff'].includes(ext)) {
      toast(`Unsupported file: ${f.name}. Use .dxf or .tif/.tiff.`, 'error');
      return;
    }
    setFile(f);
    setNotes('');
    setPrecheck(null);
    setStep(1);
    runPrecheck(f);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(0);
    setLogLines([]);
    setStep(3);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('notes', notes);

    try {
      const res = await fetch(`${importBase}/import/`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Upload failed.' }));
        throw new Error(errData.detail || `Upload failed with status ${res.status}`);
      }
      const result = await res.json();
      const sid = result.survey_session_id;
      setSessionId(sid);
      setStatusLabel('Queued...');
      setProgress(5);
      toast('Ingestion initiated! The file is processing in the background queue.', 'success');
      pollRef.current = setInterval(() => pollStatus(sid), 2000);
    } catch (err: any) {
      toast(err.message || 'Failed to upload drawing package.', 'error');
      setUploading(false);
      setStep(2);
    }
  };

  const fmtSize = (b: number) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${(b / 1024).toFixed(0)} KB`);

  return (
    <div className="w-full">
      {/* Stepper */}
      <div className="flex items-center gap-1 mb-4">
        {['Select File', 'Validate & Preview', 'Upload & Process'].map((label, i) => {
          const n = (i + 1) as 1 | 2 | 3;
          const active = step === n;
          const done = step > n;
          return (
            <React.Fragment key={label}>
              {i > 0 && <div className="flex-1 h-px bg-white/10" />}
              <div className={`flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-wider ${active ? 'text-sky-400' : done ? 'text-emerald-400' : 'text-slate-600'}`}>
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[8px] ${active ? 'bg-sky-500 text-slate-950' : done ? 'bg-emerald-500 text-slate-950' : 'bg-slate-800 text-slate-500'}`}>
                  {done ? <CheckCircle2 className="w-3 h-3" /> : n}
                </span>
                <span className="hidden sm:inline">{label}</span>
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {/* Step 1: Select */}
      {step === 1 && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${dragging ? 'border-sky-400 bg-sky-500/10' : 'border-slate-700 hover:border-sky-400/60 bg-slate-950/40'}`}
        >
          <input ref={fileInputRef} type="file" accept=".dxf,.tif,.tiff" onChange={onPick} className="hidden" />
          <Upload className="w-8 h-8 text-slate-500 mx-auto mb-2" />
          <p className="text-xs font-semibold text-slate-200">Drag & drop your CAD package, or click to browse</p>
          <p className="text-[9px] text-slate-500 mt-1">DXF drawings (.dxf) or Orthophotos (.tif, .tiff) up to 100MB</p>
        </div>
      )}

      {/* Step 2: Validate & Preview */}
      {step === 2 && precheck && (
        <div className="space-y-4">
          {/* File summary */}
          <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-950/40 border border-white/10">
            {precheck.file_extension === '.tif' || precheck.file_extension === '.tiff'
              ? <ImageIcon className="w-6 h-6 text-sky-400 shrink-0" />
              : <FileText className="w-6 h-6 text-amber-400 shrink-0" />}
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-slate-200 truncate">{file?.name}</div>
              <div className="text-[9px] text-slate-500">
                {precheck.session_type || 'INVALID'} • {fmtSize(precheck.file_size_bytes)}{precheck.file_extension === '.dxf' ? ` • ${precheck.estimated_feature_count} features` : ''}
              </div>
            </div>
            {validating && <Loader2 className="w-4 h-4 animate-spin text-sky-400" />}
            {!validating && (precheck.valid ? <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" /> : <XCircle className="w-5 h-5 text-rose-400 shrink-0" />)}
          </div>

          {/* Validation report */}
          {!validating && (
            <div className="space-y-2">
              {precheck.errors.length > 0 && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 space-y-1">
                  {precheck.errors.map((e, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-rose-300">
                      <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                      <span>{e}</span>
                    </div>
                  ))}
                </div>
              )}

              {precheck.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>{w}</span>
                </div>
              ))}

              {precheck.is_duplicate && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-sky-500/10 border border-sky-500/30 text-xs text-sky-300">
                  <Layers className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>This file matches session <b className="font-mono">{precheck.duplicate_session_id?.slice(0, 8)}</b>. Continuing may create a duplicate survey session.</span>
                </div>
              )}

              {precheck.errors.length === 0 && precheck.warnings.length === 0 && !precheck.is_duplicate && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>File looks good — ready to ingest.</span>
                </div>
              )}
            </div>
          )}

          {/* Layer preview (DXF only) */}
          {!validating && precheck.file_extension === '.dxf' && precheck.predicted_layers.length > 0 && (
            <div className="p-3 rounded-lg bg-slate-950/40 border border-white/10">
              <div className="text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-2">Detected Layers</div>
              <div className="flex flex-wrap gap-1.5">
                {precheck.predicted_layers.map((l) => (
                  <span key={l} className="px-2 py-0.5 rounded bg-sky-500/10 border border-sky-500/30 text-[9px] text-sky-300 font-mono">{l}</span>
                ))}
              </div>
            </div>
          )}

          {/* Notes */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Upload Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Describe this survey update batch..."
              rows={3}
              className="w-full p-2.5 bg-slate-950 border border-white/10 focus:border-sky-400 focus:outline-none rounded-lg text-xs text-slate-200 resize-none"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="px-4 py-2 rounded-lg border border-white/10 text-slate-300 text-xs hover:bg-white/5 cursor-pointer"
            >
              Back
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={!precheck.valid || uploading}
              className="flex-1 py-2.5 bg-sky-500 hover:bg-sky-600 disabled:bg-slate-800 disabled:text-slate-600 text-slate-950 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 cursor-pointer transition-all shadow-lg"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload & Process</span>
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Processing */}
      {step === 3 && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <Loader2 className="w-5 h-5 animate-spin text-sky-400" />
            <span className="text-xs font-semibold text-slate-200">{statusLabel}</span>
            {sessionId && <span className="text-[9px] font-mono text-slate-500 ml-auto">#{sessionId.slice(0, 8)}</span>}
          </div>

          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${progress === 100 ? 'bg-emerald-500' : (statusLabel === 'Failed' ? 'bg-rose-500' : 'bg-sky-500')}`}
              style={{ width: `${progress ?? 0}%` }}
            />
          </div>
          <div className="text-[9px] text-slate-500 text-right">{progress ?? 0}%</div>

          {logLines.length > 0 && (
            <div className="p-2.5 rounded-lg bg-slate-950/60 border border-white/10 font-mono text-[9px] text-emerald-400/80 max-h-32 overflow-y-auto space-y-0.5">
              {logLines.map((l, i) => <div key={i}>{l}</div>)}
            </div>
          )}

          {statusLabel === 'Complete' || statusLabel === 'Failed' ? (
            <button
              type="button"
              onClick={() => { setStep(1); setFile(null); setPrecheck(null); }}
              className="w-full py-2 rounded-lg border border-white/10 text-xs text-slate-300 hover:bg-white/5 cursor-pointer"
            >
              Upload Another File
            </button>
          ) : (
            <div className="flex items-center gap-2 text-[9px] text-slate-500">
              <RefreshCw className="w-3 h-3 animate-spin" />
              Polling processing status...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
