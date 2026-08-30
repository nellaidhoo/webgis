'use client';

import { useState } from 'react';
import { Download, FileJson, FileSpreadsheet, FolderArchive, X, Loader2 } from 'lucide-react';
import { useToast } from './ToastProvider';

interface ExportModalProps {
  apiBaseUrl: string;
  isOpen: boolean;
  onClose: () => void;
  layer?: string;
  bbox?: string;
}

const FORMATS = [
  { value: 'geojson', label: 'GeoJSON', hint: '.geojson', icon: FileJson },
  { value: 'csv', label: 'CSV', hint: '.csv', icon: FileSpreadsheet },
  { value: 'shapefile', label: 'Shapefile', hint: '.zip', icon: FolderArchive },
];

function formatLayer(layer: string): string {
  return layer.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ExportModal({ apiBaseUrl, isOpen, onClose, layer = 'all', bbox }: ExportModalProps) {
  const { toast } = useToast();
  const [format, setFormat] = useState('geojson');
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleExport = async () => {
    setIsExporting(true);
    setError(null);

    const params = new URLSearchParams({ export_format: format });
    if (bbox) params.append('bbox', bbox);

    const layerPath = layer === 'all' ? '' : `${layer}/`;
    const url = `${apiBaseUrl}/export/${layerPath}?${params.toString()}`;

    try {
      const token = typeof window !== 'undefined' ? window.localStorage.getItem('webgis_token') : null;
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (!response.ok) {
        let msg = `Export failed (HTTP ${response.status})`;
        try {
          const data = await response.json();
          if (data && data.error) msg = data.error;
        } catch {
          /* non-JSON error body */
        }
        throw new Error(msg);
      }

      const blob = await response.blob();

      const contentDisposition = response.headers.get('Content-Disposition');
      let filename: string;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^";]+)"?/);
        filename = match ? match[1] : `${layer === 'all' ? 'webgis-data' : layer}.${format === 'geojson' ? 'geojson' : format}`;
      } else {
        filename = `${layer === 'all' ? 'webgis-data' : layer}.${format === 'geojson' ? 'geojson' : format === 'shapefile' ? 'zip' : 'csv'}`;
      }

      const downloadUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(downloadUrl);

      toast(`Export completed: ${filename}`, 'success');
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Export failed';
      setError(message);
      toast(`Export failed: ${message}`, 'error');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[3000] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-panel overflow-hidden border border-white/10 shadow-2xl animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
          <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider flex items-center gap-2">
            <Download className="w-4 h-4 text-emerald-400" />
            Export Data
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* Context info */}
          <div className="rounded-lg bg-slate-900/50 border border-white/5 p-3 text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-slate-500">Layer:</span>
              <span className="font-semibold text-slate-200 capitalize">
                {layer === 'all' ? 'All Layers' : formatLayer(layer)}
              </span>
            </div>
            {bbox && (
              <div className="flex justify-between">
                <span className="text-slate-500">Bounding Box:</span>
                <span className="font-mono text-[10px] text-slate-300">{bbox}</span>
              </div>
            )}
          </div>

          {/* Format selection */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-2 uppercase tracking-wider">
              Export Format
            </label>
            <div className="grid grid-cols-3 gap-2">
              {FORMATS.map((opt) => {
                const Icon = opt.icon;
                return (
                  <button
                    key={opt.value}
                    onClick={() => setFormat(opt.value)}
                    className={`p-3 rounded-lg border text-center transition-colors cursor-pointer ${
                      format === opt.value
                        ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
                        : 'border-white/10 bg-slate-900/40 hover:border-white/20 hover:bg-slate-900 text-slate-300'
                    }`}
                  >
                    <Icon className="w-5 h-5 mx-auto mb-1.5" />
                    <div className="text-xs font-semibold">{opt.label}</div>
                    <div className="text-[10px] text-slate-500">{opt.hint}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className="rounded-lg bg-rose-500/10 border border-rose-500/30 p-3 text-xs text-rose-400">
              {error}
            </div>
          )}

          {/* Export button */}
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-slate-950 font-bold rounded-lg text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20"
          >
            {isExporting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Exporting...
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                Export {layer === 'all' ? 'All Data' : formatLayer(layer)}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
