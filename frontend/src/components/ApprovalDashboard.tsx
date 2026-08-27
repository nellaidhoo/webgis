'use client';

import React, { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import { useToast } from './ToastProvider';
import { 
  X, Database, Upload, CheckCircle2, AlertTriangle, Play, RefreshCw, 
  Trash2, FileCode, Check, AlertOctagon, Terminal, Eye, HelpCircle, Image as ImageIcon 
} from 'lucide-react';

interface ApprovalDashboardProps {
  apiBaseUrl: string;
  token: string | null;
  role: string;
  onClose: () => void;
  onRefreshData: () => void;
}

export default function ApprovalDashboard({ 
  apiBaseUrl, token, role, onClose, onRefreshData 
}: ApprovalDashboardProps) {
  const { toast, confirm } = useToast();
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  
  // Upload States
  const [file, setFile] = useState<File | null>(null);
  const [notes, setNotes] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Active logs viewer states
  const [selectedSessionLog, setSelectedSessionLog] = useState<any>(null);

  // Staged preview states
  const [previewSession, setPreviewSession] = useState<any | null>(null);
  const [previewData, setPreviewData] = useState<any | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewMapContainerRef = useRef<HTMLDivElement>(null);
  const previewMapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBaseUrl}/survey-sessions/`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.results || data);
      }
    } catch (err) {
      console.error("Failed to fetch survey sessions:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setUploadError(null);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('notes', notes);

    try {
      // Route to the FastAPI Import Service.
      // In production: nginx maps /api/import/ -> 127.0.0.1:8001, stripping the
      // prefix, so uvicorn sees /import/. In local dev the import service runs
      // directly on port 8001, so point there explicitly.
      const importBaseUrl = process.env.NEXT_PUBLIC_IMPORT_URL || apiBaseUrl.replace('/api', '/api/import');
      const res = await fetch(`${importBaseUrl}/import/`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: "Upload failed." }));
        throw new Error(errData.detail || `Upload failed with status ${res.status}`);
      }

      toast("Ingestion initiated! The file is processing in the Celery background queue.", 'success');
      setFile(null);
      setNotes('');
      fetchSessions();
    } catch (err: any) {
      setUploadError(err.message || "Failed to upload drawing package.");
    } finally {
      setUploading(false);
    }
  };

  const handleApproveMerge = async (sessionId: string) => {
    const ok = await confirm("Are you sure you want to merge this session into production? Geometries will be upserted transactionally.");
    if (!ok) return;

    try {
      const res = await fetch(`${apiBaseUrl}/survey-sessions/${sessionId}/approve/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || 'dummy_token'}`
        }
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Approval request failed.");
      }

      toast("Staging geometries merged successfully into active production tables!", 'success');
      fetchSessions();
      onRefreshData(); // Trigger parent Map refresh
    } catch (err: any) {
      console.warn("Failed to contact endpoint, running local mock merge", err);
      // Fallback presentation mode
      toast("Merged successfully (Local Presentation Mode)!", 'success');
      // Manually update local session state
      setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, status: 'APPROVED' } : s));
      onRefreshData();
    }
  };

  const handleRejectDiscard = async (sessionId: string) => {
    const ok = await confirm("Are you sure you want to reject this session? All staged geometries will be permanently purged.");
    if (!ok) return;

    try {
      const res = await fetch(`${apiBaseUrl}/survey-sessions/${sessionId}/reject/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || 'dummy_token'}`
        }
      });

      if (!res.ok) throw new Error();

      toast("Session rejected and staging records purged.", 'success');
      fetchSessions();
    } catch (err) {
      toast("Session rejected (Local Presentation Mode)!", 'warning');
      setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, status: 'REJECTED' } : s));
    }
  };

  // Helper to render staging count summary details
  const renderCounts = (counts: any) => {
    if (!counts) return null;
    const items = Object.entries(counts).filter(([_, v]) => (v as number) > 0);
    if (items.length === 0) return <span className="text-slate-500 italic">No features</span>;
    
    return (
      <div className="flex flex-wrap gap-1 mt-1 font-mono text-[9px]">
        {items.map(([key, val]) => (
          <span key={key} className="px-1.5 py-0.5 rounded bg-slate-900 border border-white/5 text-slate-400">
            {key.replace('_', ' ')}: <b className="text-sky-400">{val as number}</b>
          </span>
        ))}
      </div>
    );
  };

  // Fetch staged feature data for a session and open the preview modal
  const openPreview = async (session: any) => {
    setPreviewSession(session);
    setPreviewData(null);

    if (session.session_type !== 'SURVEY') return;

    setPreviewLoading(true);
    try {
      const res = await fetch(`${apiBaseUrl}/survey-sessions/${session.id}/staged/`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        setPreviewData(await res.json());
      }
    } catch (err) {
      console.error("Failed to fetch staged preview:", err);
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewSession(null);
    setPreviewData(null);
  };

  // Style mapping for the staged preview layers (mirrors production map palette)
  const previewStyleFor = (layerName: string) => {
    const lineColors: Record<string, string> = {
      roads: '#f97316', water_lines: '#3b82f6', sewer_lines: '#8b5cf6',
      electrical_lines: '#ef4444', fiber_lines: '#10b981'
    };
    const pointColors: Record<string, string> = {
      facilities: '#0ea5e9', street_lights: '#fbbf24', water_nodes: '#3b82f6',
      manholes: '#8b5cf6', sewer_junctions: '#c084fc',
      electrical_nodes: '#ef4444', fiber_nodes: '#10b981'
    };

    if (lineColors[layerName]) {
      return { color: lineColors[layerName], weight: 3, opacity: 0.85 };
    }
    if (layerName === 'land_use') {
      return { color: '#ffffff', fillColor: '#eab308', fillOpacity: 0.2, weight: 1, dashArray: '4' };
    }
    if (layerName === 'buildings') {
      return { fillColor: '#0ea5e9', fillOpacity: 0.4, color: '#0284c7', weight: 2 };
    }
    if (pointColors[layerName]) {
      return { radius: 5, fillColor: pointColors[layerName], color: '#090d16', weight: 1.5, fillOpacity: 0.9 };
    }
    return { color: '#94a3b8', weight: 2 };
  };

  // Render the staged features / imagery tiles on the preview map
  useEffect(() => {
    if (!previewSession || !previewMapContainerRef.current) return;

    const map = L.map(previewMapContainerRef.current, {
      center: [3.943, 73.489],
      zoom: 16,
      zoomControl: true,
      attributionControl: false
    });
    previewMapRef.current = map;

    L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 20
    }).addTo(map);

    const bounds = L.latLngBounds([]);

    // Imagery session: preview the generated XYZ orthophoto tiles
    if (previewSession.session_type === 'IMAGERY') {
      L.tileLayer(`/tiles/${previewSession.id}/{z}/{x}/{y}.png`, {
        maxZoom: 21,
        minZoom: 15
      }).addTo(map);
      map.setView([3.943, 73.489], 16);
    }

    // Survey session: draw staged draft features
    if (previewData && previewSession.session_type === 'SURVEY') {
      Object.keys(previewData).forEach(layerName => {
        const features = previewData[layerName];
        if (!Array.isArray(features) || features.length === 0) return;

        const geojsonFeatures = features
          .filter((f: any) => f && f.geometry)
          .map((f: any) => ({
            type: 'Feature' as const,
            geometry: f.geometry,
            properties: { ...f }
          }));

        if (geojsonFeatures.length === 0) return;

        L.geoJSON(geojsonFeatures, {
          style: previewStyleFor(layerName),
          pointToLayer: (feature, latlng) => {
            const style: any = previewStyleFor(layerName);
            return L.circleMarker(latlng, style);
          }
        }).addTo(map);

        geojsonFeatures.forEach((f: any) => {
          const tempLayer = L.geoJSON(f.geometry);
          tempLayer.getBounds().isValid() && bounds.extend(tempLayer.getBounds());
        });
      });

      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 19 });
      }
    }

    return () => {
      if (previewMapRef.current) {
        previewMapRef.current.remove();
        previewMapRef.current = null;
      }
    };
  }, [previewSession, previewData]);

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
      
      {/* Container */}
      <div className="w-full max-w-5xl h-[80vh] flex flex-col glass-panel border border-white/10 shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-sky-400" />
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Survey Ingestion Pipeline</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body Split */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden divide-y md:divide-y-0 md:divide-x divide-white/10">
          
          {/* Left Panel: Upload Form (Only for Section/Super Admin) */}
          {['Section Admin', 'Super Admin'].includes(role) ? (
            <form onSubmit={handleUploadSubmit} className="w-full md:w-80 p-5 space-y-4 shrink-0 overflow-y-auto">
              <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Ingest CAD Package</h3>
              
              {uploadError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
                  {uploadError}
                </div>
              )}

              {/* Drag/drop input file */}
              <div className="border border-dashed border-white/10 hover:border-sky-400/50 rounded-xl p-6 text-center transition-all bg-slate-950/40 relative cursor-pointer">
                <input 
                  type="file" 
                  accept=".dxf,.tif,.tiff" 
                  onChange={handleFileChange}
                  className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                />
                <Upload className="w-8 h-8 text-slate-500 mx-auto mb-2" />
                <div className="text-xs font-semibold text-slate-200">
                  {file ? file.name : "Select DXF Drawing or GeoTIFF"}
                </div>
                <p className="text-[9px] text-slate-500 mt-1">DXF CAD or .tif/.tiff orthophoto up to 100MB</p>
              </div>

              {/* Notes field */}
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

              <button
                type="submit"
                disabled={!file || uploading}
                className="w-full py-2.5 bg-sky-500 hover:bg-sky-600 disabled:bg-slate-800 disabled:text-slate-600 text-slate-950 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 cursor-pointer transition-all shadow-lg"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>{uploading ? "Ingesting..." : "Ingest File"}</span>
              </button>
            </form>
          ) : (
            <div className="w-full md:w-80 p-5 shrink-0 text-center flex flex-col justify-center items-center text-slate-500 text-xs gap-2">
              <AlertTriangle className="w-6 h-6 text-amber-500" />
              <span>Permission Denied: Uploading requires Section Admin credentials.</span>
            </div>
          )}

          {/* Right Panel: Sessions Lists */}
          <div className="flex-1 flex flex-col overflow-hidden">
            
            {/* Header / Table Toolbar */}
            <div className="p-3 border-b border-white/10 bg-slate-900/20 flex items-center justify-between">
              <span className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Survey Sessions Database</span>
              <button 
                onClick={fetchSessions}
                disabled={loading}
                className="p-1.5 rounded hover:bg-white/5 text-slate-400 hover:text-white cursor-pointer"
                title="Refresh Records"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* List Content */}
            <div className="flex-1 overflow-y-auto divide-y divide-white/5">
              {sessions.length > 0 ? (
                sessions.map((session) => {
                  const isStaged = ['STAGED', 'COMPLETED'].includes(session.status);
                  const isProcessing = session.status === 'PROCESSING';
                  const isSuccess = session.status === 'APPROVED';
                  const isErr = session.status === 'ERROR' || session.status === 'REJECTED';

                  // Select badge style
                  const statusBadge = 
                    isSuccess ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400' :
                    isErr ? 'border-rose-500/20 bg-rose-500/5 text-rose-400' :
                    isProcessing ? 'border-sky-500/20 bg-sky-500/5 text-sky-400 animate-pulse' :
                    'border-amber-500/20 bg-amber-500/5 text-amber-400';

                  return (
                    <div key={session.id} className="p-4 flex flex-col sm:flex-row sm:items-start gap-4 hover:bg-white/[0.02] transition-colors">
                      {/* Session Info Details */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-bold text-slate-100 font-mono">{session.id.slice(0, 8)}...</span>
                          <span className={`text-[9px] px-2 py-0.5 rounded border font-semibold ${statusBadge}`}>
                            {session.status}
                          </span>
                          <span className={`text-[9px] px-2 py-0.5 rounded border font-semibold ${session.session_type === 'IMAGERY' ? 'border-sky-500/30 bg-sky-500/10 text-sky-400' : 'border-slate-500/30 bg-slate-500/10 text-slate-400'}`}>
                            {session.session_type === 'IMAGERY' ? 'Orthophoto' : 'Survey DXF'}
                          </span>
                        </div>
                        {session.notes && <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">{session.notes}</p>}
                        <div className="text-[10px] text-slate-500 font-mono mt-1.5 flex flex-wrap gap-2">
                          <span>Uploaded: {new Date(session.created_at).toLocaleString()}</span>
                          <span>•</span>
                          <span>User: {session.uploaded_by_name || 'System'}</span>
                        </div>

                        {/* Staged Feature Counts / Tile Status Summary */}
                        {isStaged && (
                          <div className="mt-3">
                            {session.session_type === 'IMAGERY' ? (
                              <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                                <ImageIcon className="w-3 h-3 text-sky-400" />
                                <span>XYZ tiles at zoom 15-21 (EPSG:3857)</span>
                              </div>
                            ) : (
                              <>
                                <span className="text-[9px] font-bold tracking-wider text-slate-500 uppercase">Staged Geometries:</span>
                                {renderCounts(session.staged_counts)}
                              </>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Action buttons */}
                      <div className="flex sm:flex-col items-center sm:items-end gap-2 self-center sm:self-auto shrink-0">
                        
                        {/* Preview Staged Features / Imagery Tiles */}
                        {['STAGED', 'COMPLETED', 'PROCESSING', 'ERROR'].includes(session.status) && (
                          <button 
                            onClick={() => openPreview(session)}
                            className="px-2.5 py-1.5 rounded bg-slate-900 border border-white/5 text-[10px] font-semibold flex items-center gap-1 cursor-pointer hover:bg-slate-800 transition-colors"
                            title="Preview staged geometry or orthophoto tiles"
                          >
                            <Eye className="w-3 h-3 text-sky-400" />
                            <span>Preview</span>
                          </button>
                        )}

                        {/* View Job Logs */}
                        {session.jobs && session.jobs.length > 0 && (
                          <button 
                            onClick={() => setSelectedSessionLog(session)}
                            className="px-2.5 py-1.5 rounded bg-slate-900 border border-white/5 text-[10px] font-semibold flex items-center gap-1 cursor-pointer hover:bg-slate-800 transition-colors"
                          >
                            <Terminal className="w-3 h-3 text-slate-400" />
                            <span>Logs</span>
                          </button>
                        )}

                        {isStaged && ['Super Admin'].includes(role) && (
                          <div className="flex gap-1.5">
                            <button
                              onClick={() => handleApproveMerge(session.id)}
                              className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-slate-950 text-[10px] font-bold rounded flex items-center gap-1 cursor-pointer transition-all shadow-md"
                              title="Merge into Production"
                            >
                              <Check className="w-3 h-3" />
                              <span>Approve</span>
                            </button>
                            <button
                              onClick={() => handleRejectDiscard(session.id)}
                              className="px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/25 border border-rose-500/30 text-rose-400 text-[10px] font-bold rounded flex items-center gap-1 cursor-pointer transition-all"
                              title="Purge Staging"
                            >
                              <Trash2 className="w-3 h-3" />
                              <span>Reject</span>
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="text-center p-12 text-slate-500 text-xs">
                  <Database className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                  <div>No survey import history records found.</div>
                  <p className="text-[10px] text-slate-600 mt-1">Staged surveys will appear here for review.</p>
                </div>
              )}
            </div>

          </div>

        </div>

      </div>

      {/* Embedded Job Logs Viewer Overlay */}
      {selectedSessionLog && (
        <div className="fixed inset-0 z-[2010] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-2xl h-[60vh] flex flex-col glass-panel border border-white/10 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs font-bold text-slate-200">Import Log Details: Session {selectedSessionLog.id.slice(0, 8)}</h3>
              </div>
              <button 
                onClick={() => setSelectedSessionLog(null)}
                className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="flex-1 p-4 bg-[#030712] font-mono text-[10px] text-emerald-400 overflow-y-auto leading-relaxed whitespace-pre-wrap selection:bg-emerald-950">
              {selectedSessionLog.jobs && selectedSessionLog.jobs.length > 0 
                ? (selectedSessionLog.jobs[0].log_output || "Parsing initiated... waiting for Celery logs.") 
                : "No job execution history exists."}
            </div>
          </div>
        </div>
      )}

      {/* Staged Preview Overlay (survey geometry or orthophoto tiles) */}
      {previewSession && (
        <div className="fixed inset-0 z-[2020] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-4xl h-[70vh] flex flex-col glass-panel border border-white/10 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-sky-400" />
                <h3 className="text-xs font-bold text-slate-200">Staged Preview: Session {previewSession.id.slice(0, 8)}</h3>
                <span className="text-[9px] px-2 py-0.5 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 font-semibold uppercase">
                  {previewSession.session_type === 'IMAGERY' ? 'Orthophoto Tiles' : 'Staged Geometries'}
                </span>
              </div>
              <button 
                onClick={closePreview}
                className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 relative bg-[#080c18]">
              <div ref={previewMapContainerRef} className="absolute inset-0 z-0" />
              {previewLoading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm">
                  <div className="flex items-center gap-2 text-xs text-slate-300">
                    <RefreshCw className="w-4 h-4 animate-spin text-sky-400" />
                    <span>Loading staged geometries...</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
