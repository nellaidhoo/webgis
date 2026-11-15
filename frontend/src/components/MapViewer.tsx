'use client';

import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { 
  Map as MapIcon, Layers, Search, Shield, User, LogIn, LogOut, CheckCircle, 
  X, Edit, Trash2, Save, Plus, ArrowRight, Activity, FileText, Database, AlertCircle,
  Ruler, Eraser, CheckSquare, Download, Users
} from 'lucide-react';
import SearchBar from './SearchBar';
import AdminPanel from './AdminPanel';
import ApprovalDashboard from './ApprovalDashboard';
import ExportModal from './ExportModal';
import UsersPanel from './UsersPanel';
import ForcePasswordChangeModal from './ForcePasswordChangeModal';
import { useToast } from './ToastProvider';
import { DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM } from '../lib/mapConfig';

// Helper to fix Leaflet marker icons in Next.js
const fixLeafletIcons = () => {
  delete (L.Icon.Default.prototype as any)._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
  });
};

interface MapViewerProps {
  apiBaseUrl?: string;
}

export default function MapViewer({ apiBaseUrl = 'http://localhost/api' }: MapViewerProps) {
  const { toast, confirm } = useToast();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  
  // Layer groups references
  const layerGroupsRef = useRef<{ [key: string]: L.LayerGroup }>({});
  
  // App States
  const [selectedFeature, setSelectedFeature] = useState<any>(null);
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editGeometryData, setEditGeometryData] = useState<any>(null);
  const [role, setRole] = useState<string>(() => {
    if (typeof window !== 'undefined') return window.localStorage.getItem('webgis_role') || 'Guest';
    return 'Guest'; // Guest, Registered User, Council Staff, Section Admin, Super Admin
  });
  const [token, setToken] = useState<string | null>(() => {
    if (typeof window !== 'undefined') return window.localStorage.getItem('webgis_token');
    return null;
  });
  const [showLogin, setShowLogin] = useState<boolean>(false);
  const [showApprovals, setShowApprovals] = useState<boolean>(false);
  const [showUsers, setShowUsers] = useState<boolean>(false);
  const [showExport, setShowExport] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'layers' | 'metadata'>('layers');
  const [featureTab, setFeatureTab] = useState<'details' | 'lineage' | 'history'>('details');
  const [zoomLevel, setZoomLevel] = useState<number>(DEFAULT_MAP_ZOOM);

  // Security: the authenticated account must change its password before editing (admin reset flow)
  const [forceChangeRequired, setForceChangeRequired] = useState<boolean>(false);
  const [showForcedChange, setShowForcedChange] = useState<boolean>(false);

  // Attribute (non-geometry) editing state for the selected feature
  const [attributeDraft, setAttributeDraft] = useState<{ [key: string]: any } | null>(null);
  const [savingAttributes, setSavingAttributes] = useState<boolean>(false);

  // New-feature creation mode state (builds a geometry from map clicks like the measure tool)
  const [createMode, setCreateMode] = useState<boolean>(false);
  const [createLayer, setCreateLayer] = useState<string>('buildings');
  const [createVertexCount, setCreateVertexCount] = useState<number>(0);

  // Fiber service providers present in the currently loaded fiber data (dynamic legend)
  const [fiberProviders, setFiberProviders] = useState<string[]>([]);

  // Latest published orthophoto tile package URL (per imagery session)
  const [orthoTilesUrl, setOrthoTilesUrl] = useState<string | null>(null);

  // Measurement tool state (in-house, no external deps)
  const [measureMode, setMeasureMode] = useState<boolean>(false);
  const [measureDistance, setMeasureDistance] = useState<number>(0);
  const [measureArea, setMeasureArea] = useState<number | null>(null);
  const [measureVertexCount, setMeasureVertexCount] = useState<number>(0);
  const measureModeRef = useRef<boolean>(false);
  const measurePointsRef = useRef<L.LatLng[]>([]);
  const measureLayerRef = useRef<L.LayerGroup | null>(null);
  const measureLineRef = useRef<L.Polyline | L.Polygon | null>(null);

  // Active layers visibility states
  const [visibleLayers, setVisibleLayers] = useState<{ [key: string]: boolean }>({
    // Base Maps
    cartodbDark: true,
    osm: false,
    orthophoto: false,
    // Core Layers
    buildings: true,
    roads: true,
    land_use: true,
    facilities: true,
    // Assets & Networks
    street_lights: false,
    water_lines: false,
    water_nodes: false,
    sewer_lines: false,
    manholes: false,
    sewer_junctions: false,
    electrical_lines: false,
    electrical_nodes: false,
    fiber_lines: false,
    fiber_nodes: false,
  });

  // Base tile layers references
  const baseTilesRef = useRef<{ [key: string]: L.TileLayer }>({});
  
  // Editor markers ref (handles for editing vertices)
  const editMarkersRef = useRef<L.Marker[]>([]);
  const editPolylineRef = useRef<L.Polyline | L.Polygon | null>(null);

  // Mirror of isEditing for use inside the mount-time map click handler
  const editingRef = useRef<boolean>(false);

  // New-feature creation refs
  const createModeRef = useRef<boolean>(false);
  const createPointsRef = useRef<L.LatLng[]>([]);
  const createLayerRef = useRef<L.LayerGroup | null>(null);
  const createLineRef = useRef<L.Polyline | L.Polygon | null>(null);

  // Haversine great-circle distance between two coordinates (meters)
  const haversineMeters = (a: L.LatLng, b: L.LatLng) => {
    const R = 6371000;
    const toRad = (d: number) => (d * Math.PI) / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const la1 = toRad(a.lat);
    const la2 = toRad(b.lat);
    const h =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  };

  // Spherical polygon area via local planar projection at mean latitude + shoelace
  const sphericalAreaM2 = (pts: L.LatLng[]) => {
    const R = 6371000;
    const toRad = (d: number) => (d * Math.PI) / 180;
    const meanLat = toRad(pts.reduce((s, p) => s + p.lat, 0) / pts.length);
    const xs = pts.map((p) => R * toRad(p.lng) * Math.cos(meanLat));
    const ys = pts.map((p) => R * toRad(p.lat));
    let sum = 0;
    for (let i = 0; i < xs.length; i++) {
      const j = (i + 1) % xs.length;
      sum += xs[i] * ys[j] - xs[j] * ys[i];
    }
    return Math.abs(sum) / 2;
  };

  const formatDistance = (m: number) =>
    m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;

  const formatArea = (m2: number) =>
    m2 >= 10000 ? `${(m2 / 10000).toFixed(3)} ha` : `${Math.round(m2)} m²`;

  // Geometry kind of each layer, used to decide the minimum vertices for new features
  const LAYER_GEOMETRY_KIND: Record<string, 'point' | 'line' | 'polygon'> = {
    facilities: 'point',
    street_lights: 'point', water_nodes: 'point', manholes: 'point',
    sewer_junctions: 'point', electrical_nodes: 'point', fiber_nodes: 'point',
    roads: 'line', water_lines: 'line', sewer_lines: 'line',
    electrical_lines: 'line', fiber_lines: 'line',
    buildings: 'polygon', land_use: 'polygon'
  };

  const LAYER_LABELS: Record<string, string> = {
    buildings: 'Buildings (Polygon)', roads: 'Roads (Line)', land_use: 'Land Use Zones (Polygon)',
    facilities: 'Public Facilities (Point)', street_lights: 'Street Lights (Point)',
    water_lines: 'Water Pipes (Line)', water_nodes: 'Water Valves (Point)',
    sewer_lines: 'Sewer Gravity (Line)', manholes: 'Sewer Manholes (Point)',
    sewer_junctions: 'Sewer Junctions (Point)', electrical_lines: 'Power Cables (Line)',
    electrical_nodes: 'Distribution Box (Point)', fiber_lines: 'Fiber Cables (Line)',
    fiber_nodes: 'Fiber Cabinets (Point)'
  };

  const ASSET_POINT_COLORS: Record<string, string> = {
    street_lights: '#fbbf24', water_nodes: '#3b82f6', manholes: '#8b5cf6',
    sewer_junctions: '#c084fc', electrical_nodes: '#ef4444', fiber_nodes: '#10b981'
  };

  const ASSET_LINE_COLORS: Record<string, string> = {
    water_lines: '#3b82f6', sewer_lines: '#8b5cf6', electrical_lines: '#ef4444', fiber_lines: '#10b981'
  };

  // System/derived fields that must not be edited inline
  const ATTRIBUTE_EDIT_EXCLUDE = [
    'id', 'geometry', 'addresses_list', 'asset_code', 'created_by', 'created_by_name',
    'addresses_count', 'source_file', 'survey_date', 'accuracy', 'status', 'category',
    'created_at', 'updated_at'
  ];

  // Distance from point p to segment (a, b)
  const pointToSegmentDist = (p: L.LatLng, a: L.LatLng, b: L.LatLng) => {
    const dx = b.lng - a.lng, dy = b.lat - a.lat;
    const len2 = dx * dx + dy * dy;
    if (len2 === 0) return Math.hypot(p.lat - a.lat, p.lng - a.lng);
    let t = ((p.lng - a.lng) * dx + (p.lat - a.lat) * dy) / len2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(p.lat - (a.lat + t * dy), p.lng - (a.lng + t * dx));
  };

  // Extract a human-readable message from a DRF-style error payload
  const extractApiError = (data: any): string => {
    if (!data) return 'Unknown error';
    if (typeof data === 'string') return data;
    if (typeof data.detail === 'string') return data.detail;
    if (typeof data.error === 'string') return data.error;
    if (typeof data === 'object') {
      const vals = Object.values(data);
      for (const v of vals) {
        if (Array.isArray(v) && v.length > 0) return String(v[0]);
        if (typeof v === 'string' && v) return v;
        if (v && typeof v === 'object' && (v as any).message) return String((v as any).message);
      }
    }
    return 'Request failed';
  };

  const toggleMeasure = () => {
    if (measureModeRef.current) {
      clearMeasure();
    } else {
      setMeasureMode(true);
      measureModeRef.current = true;
      measureLayerRef.current = L.layerGroup().addTo(mapRef.current!);
      setMeasureDistance(0);
      setMeasureArea(null);
      setMeasureVertexCount(0);
    }
  };

  const clearMeasure = () => {
    measureModeRef.current = false;
    setMeasureMode(false);
    measurePointsRef.current = [];
    setMeasureDistance(0);
    setMeasureArea(null);
    setMeasureVertexCount(0);
    if (measureLineRef.current) {
      measureLineRef.current.remove();
      measureLineRef.current = null;
    }
    if (measureLayerRef.current) {
      measureLayerRef.current.remove();
      measureLayerRef.current = null;
    }
  };

  const closeMeasureArea = () => {
    const pts = measurePointsRef.current;
    if (pts.length < 3) return;

    if (measureLineRef.current) {
      measureLineRef.current.remove();
      measureLineRef.current = null;
    }
    const closed = [...pts, pts[0]];
    measureLineRef.current = L.polygon(closed, {
      color: '#fbbf24',
      weight: 3,
      fillColor: '#fbbf24',
      fillOpacity: 0.15,
      dashArray: '6, 4'
    }).addTo(measureLayerRef.current!);
    setMeasureArea(sphericalAreaM2(pts));
  };

  // Fetch the latest published imagery session and point the orthophoto layer at its tiles
  const loadLatestOrthophoto = async () => {
    try {
      const res = await fetch(`${apiBaseUrl}/survey-sessions/latest-imagery/`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.session_id) {
        setOrthoTilesUrl(`/tiles/${data.session_id}`);
      }
    } catch (err) {
      console.warn("Could not resolve latest orthophoto session:", err);
    }
  };

  // Point the orthophoto tile layer at the resolved session tiles
  useEffect(() => {
    const layer = baseTilesRef.current.orthophoto;
    if (!layer || !orthoTilesUrl) return;
    layer.setUrl(`${orthoTilesUrl}/{z}/{x}/{y}.png`);
  }, [orthoTilesUrl]);

  useEffect(() => {
    fixLeafletIcons();
    
    if (!mapContainerRef.current || mapRef.current) return;

    // Initialize Map centered on the configured default location (Nellaidhoo, Maldives by default)
    const map = L.map(mapContainerRef.current, {
      center: DEFAULT_MAP_CENTER,
      zoom: DEFAULT_MAP_ZOOM,
      zoomControl: false,
      attributionControl: true
    });
    
    mapRef.current = map;
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Track Zoom level
    map.on('zoomend', () => {
      setZoomLevel(map.getZoom());
      syncRoadLabels();
    });

    // 1. Initialize Base Layers
    baseTilesRef.current.cartodbDark = L.tileLayer(
      'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
      {
        attribution: '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 20
      }
    ).addTo(map);

    baseTilesRef.current.osm = L.tileLayer(
      'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 20
      }
    );

    // Custom Orthophoto drone tiles served by Nginx from /opt/webgis/tiles
    // The URL template is set dynamically once the latest imagery session loads.
    baseTilesRef.current.orthophoto = L.tileLayer(
      '',
      {
        attribution: 'Drone Survey 2026',
        maxZoom: 21,
        minZoom: 15,
        errorTileUrl: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" style="background:%230c1020;color:rgba(255,255,255,0.05);"><rect width="100%25" height="100%25" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="2"/><text x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="monospace">Imagery Offline</text></svg>'
      }
    );

    // 2. Initialize Layer Groups
    const layerNames = [
      'buildings', 'roads', 'land_use', 'facilities', 'street_lights',
      'water_lines', 'water_nodes', 'sewer_lines', 'manholes', 'sewer_junctions',
      'electrical_lines', 'electrical_nodes', 'fiber_lines', 'fiber_nodes'
    ];

    layerNames.forEach(name => {
      layerGroupsRef.current[name] = L.layerGroup();
      // Add default visible ones to map
      if (visibleLayers[name]) {
        layerGroupsRef.current[name].addTo(map);
      }
    });

    // 3. Load initial mock/seed data from backend
    fetchData();

    // 4. Discover the latest published orthophoto tile package
    loadLatestOrthophoto();

    // 5. Measurement tool click handler (active only when measureMode is on)
    map.on('click', (e: L.LeafletMouseEvent) => {
      // Geometry edit mode: insert a new vertex (add-vertex) at the click point
      if (editingRef.current && editPolylineRef.current) {
        addVertexAtClick(e.latlng);
        return;
      }

      // New-feature creation mode: place a vertex like the measure tool
      if (createModeRef.current) {
        placeCreateVertex(e.latlng);
        return;
      }

      if (!measureModeRef.current || !measureLayerRef.current) return;
      measurePointsRef.current.push(e.latlng);

      L.circleMarker(e.latlng, {
        radius: 5,
        color: '#090d16',
        weight: 1.5,
        fillColor: '#fbbf24',
        fillOpacity: 1
      }).addTo(measureLayerRef.current);

      const pts = measurePointsRef.current;
      if (measureLineRef.current) {
        measureLineRef.current.remove();
        measureLineRef.current = null;
      }
      if (pts.length >= 2) {
        measureLineRef.current = L.polyline(pts, {
          color: '#fbbf24',
          weight: 3,
          dashArray: '6, 4'
        }).addTo(measureLayerRef.current);
      }

      const dist = pts.slice(1).reduce((acc, p, i) => acc + haversineMeters(pts[i], p), 0);
      setMeasureDistance(dist);
      setMeasureVertexCount(pts.length);
    });

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Update base tiles visibility
  useEffect(() => {
    if (!mapRef.current) return;
    
    const map = mapRef.current;
    
    if (visibleLayers.cartodbDark) {
      if (!map.hasLayer(baseTilesRef.current.cartodbDark)) map.addLayer(baseTilesRef.current.cartodbDark);
    } else {
      if (map.hasLayer(baseTilesRef.current.cartodbDark)) map.removeLayer(baseTilesRef.current.cartodbDark);
    }

    if (visibleLayers.osm) {
      if (!map.hasLayer(baseTilesRef.current.osm)) map.addLayer(baseTilesRef.current.osm);
    } else {
      if (map.hasLayer(baseTilesRef.current.osm)) map.removeLayer(baseTilesRef.current.osm);
    }

    if (visibleLayers.orthophoto) {
      if (!map.hasLayer(baseTilesRef.current.orthophoto)) map.addLayer(baseTilesRef.current.orthophoto);
    } else {
      if (map.hasLayer(baseTilesRef.current.orthophoto)) map.removeLayer(baseTilesRef.current.orthophoto);
    }
  }, [visibleLayers.cartodbDark, visibleLayers.osm, visibleLayers.orthophoto]);

  // Update overlay layers visibility
  useEffect(() => {
    if (!mapRef.current) return;
    
    const map = mapRef.current;
    Object.keys(layerGroupsRef.current).forEach(name => {
      if (visibleLayers[name]) {
        if (!map.hasLayer(layerGroupsRef.current[name])) {
          map.addLayer(layerGroupsRef.current[name]);
        }
      } else {
        if (map.hasLayer(layerGroupsRef.current[name])) {
          map.removeLayer(layerGroupsRef.current[name]);
        }
      }
    });

    // Re-apply zoom-aware road labels whenever the Roads layer is re-enabled
    if (visibleLayers['roads']) syncRoadLabels();
  }, [visibleLayers]);

  // Fetch all GIS vectors from API endpoints.
  // `authToken` is injected explicitly during login/logout because setState is
  // async — reading `token` right after setToken() would use the stale value.
  const fetchData = async (authToken?: string | null) => {
    const effToken = authToken !== undefined ? authToken : token;
    try {
      // Core Layers
      loadLayer('roads', `${apiBaseUrl}/roads/`, roadStyle, effToken);
      loadLayer('buildings', `${apiBaseUrl}/buildings/`, buildingStyle, effToken);
      loadLayer('land_use', `${apiBaseUrl}/land_use/`, landUseStyle, effToken);
      loadLayer('facilities', `${apiBaseUrl}/facilities/`, facilityStyle, effToken);

      // Assets & Utilities
      loadLayer('street_lights', `${apiBaseUrl}/assets/street_lights/`, assetPointStyle('#fbbf24'), effToken);
      loadLayer('water_lines', `${apiBaseUrl}/assets/water_lines/`, utilityLineStyle('#3b82f6'), effToken);
      loadLayer('water_nodes', `${apiBaseUrl}/assets/water_nodes/`, assetPointStyle('#3b82f6'), effToken);
      loadLayer('sewer_lines', `${apiBaseUrl}/assets/sewer_lines/`, utilityLineStyle('#8b5cf6'), effToken);
      loadLayer('manholes', `${apiBaseUrl}/assets/manholes/`, assetPointStyle('#8b5cf6', 6), effToken);
      loadLayer('sewer_junctions', `${apiBaseUrl}/assets/sewer_junctions/`, assetPointStyle('#c084fc', 4), effToken);
      loadLayer('electrical_lines', `${apiBaseUrl}/assets/electrical_lines/`, utilityLineStyle('#ef4444'), effToken);
      loadLayer('electrical_nodes', `${apiBaseUrl}/assets/electrical_nodes/`, assetPointStyle('#ef4444'), effToken);
      loadLayer('fiber_lines', `${apiBaseUrl}/assets/fiber_lines/`, fiberProviderStyle, effToken);
      loadLayer('fiber_nodes', `${apiBaseUrl}/assets/fiber_nodes/`, assetPointStyle('#10b981'), effToken);
    } catch (err) {
      console.error("Error retrieving spatial data:", err);
    }
  };

  const loadLayer = async (name: string, url: string, styleFunc: any, authToken?: string | null) => {
    try {
      // Restricted (asset/utility) layers require the caller's JWT; the backend
      // LayerVisibilityPermission enforces the registry visibility regardless.
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : undefined;
      const res = await fetch(url, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      
      const layerGroup = layerGroupsRef.current[name];
      if (!layerGroup) return;

      layerGroup.clearLayers();

      // Parse array list as GeoJSON Feature Collection
      const features = data.results || data;
      if (!Array.isArray(features)) return;

      features.forEach((item: any) => {
        if (!item.geometry) return;

        // Build GeoJSON Object
        const geojsonFeature = {
          type: "Feature" as const,
          geometry: item.geometry,
          properties: { ...item }
        };

        L.geoJSON(geojsonFeature, {
          style: styleFunc,
          pointToLayer: (feature, latlng) => {
            if (styleFunc.pointToLayer) {
              return styleFunc.pointToLayer(latlng);
            }
            return L.circleMarker(latlng, styleFunc(feature));
          },
          onEachFeature: (feature, layer) => {
            // Bind popups
            layer.on('click', (e) => {
              if (editingRef.current || createModeRef.current) return;
              L.DomEvent.stopPropagation(e);
              setAttributeDraft(null);
              
              // Load linked addresses if building
              if (name === 'buildings') {
                fetchBuildingAddresses(item, layer);
              } else {
                setSelectedFeature({ layerName: name, data: item, leafletLayer: layer });
              }
            });

            // Hover interactions for polylines/polygons
            layer.on('mouseover', () => {
              if (isEditing) return;
              if ('setStyle' in layer) {
                (layer as any).setStyle({ weight: (styleFunc(feature).weight || 3) + 2, color: '#ffffff' });
              }
            });

            layer.on('mouseout', () => {
              if (isEditing) return;
              if ('setStyle' in layer) {
                (layer as any).setStyle(styleFunc(feature));
              }
            });

            // Permanent, non-interactive road name labels (zoom-aware via syncRoadLabels)
            if (name === 'roads') {
              const roadName = feature?.properties?.road_name;
              if (roadName && String(roadName).trim() && String(roadName).trim().toLowerCase() !== 'unnamed road') {
                (layer as L.Path).bindTooltip(String(roadName).trim(), {
                  permanent: true,
                  direction: 'center',
                  interactive: false,
                  className: 'road-name-label'
                });
              }
            }
          }
        }).addTo(layerGroup);
      });

      // Track which fiber providers are present so the legend stays current
      if (name === 'fiber_lines') {
        const providers = new Set<string>();
        features.forEach((item: any) => {
          if (item.provider && String(item.provider).trim()) providers.add(String(item.provider).trim());
        });
        setFiberProviders([...providers].sort((a, b) => a.localeCompare(b)));
      }

      // Apply zoom-aware road labels after (re)loading the road layer
      if (name === 'roads') syncRoadLabels();
    } catch (err) {
      console.error(`Failed to load layer ${name}:`, err);
    }
  };

  const fetchBuildingAddresses = async (building: any, layer: any) => {
    try {
      const res = await fetch(`${apiBaseUrl}/buildings/${building.id}/addresses/`);
      const addresses = res.ok ? await res.json() : [];
      setSelectedFeature({ 
        layerName: 'buildings', 
        data: { ...building, addresses_list: addresses }, 
        leafletLayer: layer 
      });
    } catch (err) {
      setSelectedFeature({ 
        layerName: 'buildings', 
        data: { ...building, addresses_list: [] }, 
        leafletLayer: layer 
      });
    }
  };

  // Map internal layer keys to their API endpoint paths (assets are namespaced)
  const getLayerEndpoint = (layerName: string) => {
    const assetLayers = [
      'street_lights', 'water_lines', 'water_nodes', 'sewer_lines',
      'manholes', 'sewer_junctions', 'electrical_lines', 'electrical_nodes',
      'fiber_lines', 'fiber_nodes'
    ];
    return assetLayers.includes(layerName) ? `assets/${layerName}` : layerName;
  };

  // Current viewport bounds as "min_lon,min_lat,max_lon,max_lat" for the export bbox filter
  const getMapBounds = (): string | undefined => {
    const map = mapRef.current;
    if (!map) return undefined;
    const bounds = map.getBounds();
    if (!bounds) return undefined;
    return `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
  };

  // Styling Helpers
  const roadStyle = (feature: any) => ({
    color: feature.properties.surface_type === 'Asphalt' ? '#f97316' : '#eab308',
    weight: 4,
    opacity: 0.85
  });

  const buildingStyle = (feature: any) => ({
    fillColor: feature.properties.building_type === 'Government' ? '#3b82f6' : 
               feature.properties.building_type === 'Commercial' ? '#a855f7' : '#0ea5e9',
    fillOpacity: 0.45,
    color: '#0284c7',
    weight: 2
  });

  const landUseStyle = (feature: any) => ({
    fillColor: feature.properties.zone_class === 'Conservation' ? '#10b981' : 
               feature.properties.zone_class === 'Commercial' ? '#d946ef' : '#eab308',
    fillOpacity: 0.2,
    color: '#ffffff',
    weight: 1,
    dashArray: '4'
  });

  const facilityStyle = () => ({
    pointToLayer: (latlng: L.LatLng) => L.marker(latlng, {
      icon: L.divIcon({
        className: 'custom-div-icon',
        html: `<div class="w-8 h-8 rounded-full bg-slate-900 border-2 border-sky-400 flex items-center justify-center text-sky-400 shadow-lg shadow-sky-500/20"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/></svg></div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16]
      })
    })
  });

  const assetPointStyle = (color: string, radius = 5) => () => ({
    radius,
    fillColor: color,
    color: '#090d16',
    weight: 1.5,
    fillOpacity: 0.9
  });

  const utilityLineStyle = (color: string) => () => ({
    color,
    weight: 3,
    opacity: 0.8,
    dashArray: '3, 6'
  });

  // Stable per-provider fiber colors (deterministic hash, no hard-coded provider list)
  const FIBER_PROVIDER_PALETTE = [
    '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#8b5cf6',
    '#14b8a6', '#f97316', '#eab308', '#06b6d4', '#f43f5e'
  ];
  // Neutral style for unknown/null providers
  const FIBER_PROVIDER_NEUTRAL = '#94a3b8';

  const fiberProviderColor = (provider: string) => {
    if (!provider) return FIBER_PROVIDER_NEUTRAL;
    let hash = 0;
    for (let i = 0; i < provider.length; i++) hash = (hash * 31 + provider.charCodeAt(i)) >>> 0;
    return FIBER_PROVIDER_PALETTE[hash % FIBER_PROVIDER_PALETTE.length];
  };

  const fiberProviderStyle = (feature: any) => ({
    color: fiberProviderColor(feature?.properties?.provider),
    weight: 3,
    opacity: 0.8,
    dashArray: '3, 6'
  });

  // Zoom-aware road-name labeling. Below zoom 15 none; 15-16 main (asphalt) roads
  // where practical; 17+ every named road. Do not label unnamed roads or fall back
  // to asset codes.
  const shouldShowRoadLabel = (feature: any, zoom: number) => {
    const raw = feature?.properties?.road_name;
    const name = raw != null ? String(raw).trim() : '';
    if (!name || name.toLowerCase() === 'unnamed road') return false;
    if (zoom < 15) return false;
    if (zoom >= 17) return true;
    return feature?.properties?.surface_type === 'Asphalt';
  };

  // Hide/show road name labels based on the current zoom level
  const syncRoadLabels = () => {
    const map = mapRef.current;
    const group = layerGroupsRef.current['roads'];
    if (!map || !group) return;
    const zoom = map.getZoom();
    group.eachLayer((layer: L.Layer) => {
      const tooltip = (layer as any).getTooltip?.();
      const feature = (layer as any).feature;
      if (!tooltip || !feature) return;
      if (shouldShowRoadLabel(feature, zoom)) {
        if (!tooltip.isOpen()) (layer as any).openTooltip();
      } else {
        if (tooltip.isOpen()) (layer as any).closeTooltip();
      }
    });
  };

  // Layer switches toggle handler
  const handleLayerToggle = (name: string) => {
    setVisibleLayers(prev => ({ ...prev, [name]: !prev[name] }));
  };

  // Persist auth session to localStorage for cross-tab survival
  const handleLoginSuccess = (tok: string, userRole: string, mustChange = false) => {
    setToken(tok);
    setRole(userRole);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('webgis_token', tok);
      window.localStorage.setItem('webgis_role', userRole);
    }
    setShowLogin(false);
    setForceChangeRequired(mustChange);
    setShowForcedChange(mustChange);
    fetchData(tok);
  };

  const handleLogout = () => {
    setToken(null);
    setRole('Guest');
    setForceChangeRequired(false);
    setShowForcedChange(false);
    setAttributeDraft(null);
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('webgis_token');
      window.localStorage.removeItem('webgis_role');
    }
    fetchData(null);
  };

  // Re-check the forced-password flag when a session is restored from localStorage
  useEffect(() => {
    if (!token || token === 'mocked_jwt_token_for_presentation_mode') return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiBaseUrl}/auth/me/`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (cancelled) return;
        if (!res.ok) {
          handleLogout();
          return;
        }
        const me = await res.json();
        if (me.role) setRole(me.role);
        if (me.must_change_password) {
          setForceChangeRequired(true);
          setShowForcedChange(true);
        }
      } catch (err) {
        // Keep the session on transient network failures
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // Search result selector (centers and zooms map on item)
  const handleSelectSearchResult = (result: any) => {
    if (!mapRef.current || !result.geometry) return;
    
    setAttributeDraft(null);
    
    let coords: [number, number] = [0, 0];
    
    if (result.geometry.type === 'Point') {
      coords = [result.geometry.coordinates[1], result.geometry.coordinates[0]];
      mapRef.current.setView(coords, 18);
    } else {
      // Lines or Polygons: find bbox center
      const tempLayer = L.geoJSON(result.geometry);
      const bounds = tempLayer.getBounds();
      mapRef.current.fitBounds(bounds, { maxZoom: 18, padding: [50, 50] });
    }

    // Trigger select action in panel
    if (result.type === 'building') {
      fetchBuildingAddresses(result, null);
    } else {
      setSelectedFeature({ layerName: `${result.type}s`, data: result });
    }
  };

  // Apply an edited ring/line back onto the temporary edit overlay
  const setEditPolylineLatLngs = (poly: L.Polyline | L.Polygon, latlngs: L.LatLng[]) => {
    if (poly instanceof L.Polygon) poly.setLatLngs([latlngs]);
    else poly.setLatLngs(latlngs);
  };

  // Add-vertex: insert a new vertex at the click point on the nearest segment
  const addVertexAtClick = (latlng: L.LatLng) => {
    const poly = editPolylineRef.current;
    if (!poly) return;

    let latlngs: L.LatLng[];
    if (poly instanceof L.Polygon) latlngs = (poly.getLatLngs()[0] as L.LatLng[]).slice();
    else latlngs = (poly.getLatLngs() as L.LatLng[]).slice();
    if (latlngs.length < 2) return;

    let bestIndex = latlngs.length;
    let bestDist = Infinity;
    for (let i = 0; i < latlngs.length - 1; i++) {
      const d = pointToSegmentDist(latlng, latlngs[i], latlngs[i + 1]);
      if (d < bestDist) { bestDist = d; bestIndex = i + 1; }
    }
    latlngs.splice(bestIndex, 0, latlng);
    setEditPolylineLatLngs(poly, latlngs);

    // Refresh drag handles for the updated vertex set
    editMarkersRef.current.forEach(m => m.remove());
    editMarkersRef.current = [];
    latlngs.forEach((ll, i) => {
      createVertexHandle(ll, i);
    });
  };

  // New-feature creation helpers -------------------------------------------
  const toggleCreate = () => {
    if (createModeRef.current) {
      clearCreate();
      return;
    }
    if (editingRef.current) cancelEditing();
    if (measureModeRef.current) clearMeasure();
    setCreateMode(true);
    createModeRef.current = true;
    createLayerRef.current = L.layerGroup().addTo(mapRef.current!);
    setCreateVertexCount(0);
  };

  const clearCreate = () => {
    createModeRef.current = false;
    setCreateMode(false);
    createPointsRef.current = [];
    setCreateVertexCount(0);
    if (createLineRef.current) {
      createLineRef.current.remove();
      createLineRef.current = null;
    }
    if (createLayerRef.current) {
      createLayerRef.current.remove();
      createLayerRef.current = null;
    }
  };

  const placeCreateVertex = (latlng: L.LatLng) => {
    if (!createLayerRef.current) return;
    createPointsRef.current.push(latlng);

    L.circleMarker(latlng, {
      radius: 5,
      color: '#090d16',
      weight: 1.5,
      fillColor: '#34d399',
      fillOpacity: 1
    }).addTo(createLayerRef.current);

    const pts = createPointsRef.current;
    if (createLineRef.current) {
      createLineRef.current.remove();
      createLineRef.current = null;
    }
    if (pts.length >= 2) {
      createLineRef.current = L.polyline(pts, {
        color: '#34d399',
        weight: 3,
        dashArray: '6, 4'
      }).addTo(createLayerRef.current);
    }
    setCreateVertexCount(pts.length);
  };

  const buildCreateGeometry = () => {
    const pts = createPointsRef.current;
    const kind = LAYER_GEOMETRY_KIND[createLayer] || 'point';
    if (kind === 'point') {
      const p = pts[0];
      return { type: 'Point', coordinates: [p.lng, p.lat] };
    }
    if (kind === 'line') {
      return { type: 'LineString', coordinates: pts.map(p => [p.lng, p.lat]) };
    }
    const ring = pts.map(p => [p.lng, p.lat]);
    ring.push(ring[0]);
    return { type: 'Polygon', coordinates: [ring] };
  };

  const saveNewFeature = async () => {
    if (!createPointsRef.current.length) return;
    const geometry = buildCreateGeometry();

    try {
      const res = await fetch(`${apiBaseUrl}/${getLayerEndpoint(createLayer)}/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ geometry })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast(`Could not create feature: ${extractApiError(data)}`, 'error');
        return;
      }
      toast(`Feature created (${data.asset_code || 'asset code assigned automatically'}).`, 'success');
      clearCreate();
      fetchData();
    } catch (err) {
      toast('Network error creating feature. No changes were applied.', 'error');
    }
  };

  // Custom vertex geometric editing handler
  const startEditingGeometry = () => {
    if (!selectedFeature || !mapRef.current) return;
    setIsEditing(true);
    editingRef.current = true;
    setAttributeDraft(null);
    
    const layer = selectedFeature.leafletLayer;
    if (!layer) return;

    // Hide the original layer representation during editing
    layer.setOpacity ? layer.setOpacity(0.1) : layer.setStyle({ fillOpacity: 0.05, opacity: 0.05 });

    const geom = selectedFeature.data.geometry;
    let latlngs: any[] = [];

    if (geom.type === 'Polygon') {
      latlngs = geom.coordinates[0].map((coords: number[]) => L.latLng(coords[1], coords[0]));
      // Remove trailing duplicate for loop closure representation in edit polyline
      latlngs.pop();
      const polygon = L.polygon(latlngs, { color: '#fbbf24', weight: 3, fillOpacity: 0.2 }).addTo(mapRef.current);
      editPolylineRef.current = polygon;
    } else if (geom.type === 'LineString') {
      latlngs = geom.coordinates.map((coords: number[]) => L.latLng(coords[1], coords[0]));
      const polyline = L.polyline(latlngs, { color: '#fbbf24', weight: 4 }).addTo(mapRef.current);
      editPolylineRef.current = polyline;
    }

    // Create drag-handles for each vertex
    latlngs.forEach((latlng, index) => {
      createVertexHandle(latlng, index);
    });
  };

  const createVertexHandle = (latlng: L.LatLng, index: number) => {
    if (!mapRef.current) return;

    const handle = L.marker(latlng, {
      draggable: true,
      icon: L.divIcon({
        className: 'w-4 h-4 rounded-full bg-amber-500 border-2 border-white cursor-move shadow-md',
        iconSize: [16, 16],
        iconAnchor: [8, 8]
      })
    }).addTo(mapRef.current);

    handle.on('drag', () => {
      updateEditGeometry(index, handle.getLatLng());
    });

    handle.on('dblclick', () => {
      removeVertex(index);
    });

    editMarkersRef.current.push(handle);
  };

  const updateEditGeometry = (index: number, newLatLng: L.LatLng) => {
    if (!editPolylineRef.current) return;
    
    const poly = editPolylineRef.current;
    if (poly instanceof L.Polygon) {
      const latlngs = (poly.getLatLngs()[0] as L.LatLng[]).slice();
      latlngs[index] = newLatLng;
      poly.setLatLngs([latlngs]);
    } else if (poly instanceof L.Polyline) {
      const latlngs = poly.getLatLngs() as L.LatLng[];
      latlngs[index] = newLatLng;
      poly.setLatLngs(latlngs);
    }
  };

  const removeVertex = (index: number) => {
    if (!editPolylineRef.current || !mapRef.current) return;

    const poly = editPolylineRef.current;
    let latlngs: L.LatLng[] = [];

    if (poly instanceof L.Polygon) {
      latlngs = (poly.getLatLngs()[0] as L.LatLng[]).slice();
    } else {
      latlngs = poly.getLatLngs() as L.LatLng[];
    }

    if (latlngs.length <= (poly instanceof L.Polygon ? 3 : 2)) {
      toast("Cannot delete vertex. Minimum geometries vertices requirement met.", 'warning');
      return;
    }

    // Remove from array
    latlngs.splice(index, 1);
    
    if (poly instanceof L.Polygon) {
      poly.setLatLngs([latlngs]);
    } else {
      poly.setLatLngs(latlngs);
    }

    // Refresh all handles
    editMarkersRef.current.forEach(m => m.remove());
    editMarkersRef.current = [];

    latlngs.forEach((ll, i) => {
      createVertexHandle(ll, i);
    });
  };

  const saveEditedGeometry = async () => {
    if (!editPolylineRef.current || !selectedFeature) return;

    const poly = editPolylineRef.current;
    let coordinates: any = [];

    if (poly instanceof L.Polygon) {
      const latlngs = poly.getLatLngs()[0] as L.LatLng[];
      coordinates = latlngs.map(ll => [ll.lng, ll.lat]);
      // Close loop for WKT/GeoJSON Polygon standard
      coordinates.push([latlngs[0].lng, latlngs[0].lat]);
      coordinates = [coordinates]; // Nest inside outer ring array
    } else {
      const latlngs = poly.getLatLngs() as L.LatLng[];
      coordinates = latlngs.map(ll => [ll.lng, ll.lat]);
    }

    const updatedGeom = {
      type: selectedFeature.data.geometry.type,
      coordinates: coordinates
    };

    const layerName = selectedFeature.layerName;
    const featureId = selectedFeature.data.id;

    // Send PATCH to the production layer endpoint
    try {
      const res = await fetch(`${apiBaseUrl}/${getLayerEndpoint(layerName)}/${featureId}/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          geometry: updatedGeom
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast(`Save failed: ${extractApiError(data)}`, 'error');
        return;
      }

      // Reflect the new geometry on the live map layer without a full reload
      const originalLayer = selectedFeature.leafletLayer;
      if (originalLayer && originalLayer.setLatLngs) {
        if (poly instanceof L.Polygon) originalLayer.setLatLngs(poly.getLatLngs());
        else originalLayer.setLatLngs(poly.getLatLngs());
      }

      setSelectedFeature((prev: any) => prev ? { ...prev, data: { ...prev.data, ...data, geometry: data.geometry ?? updatedGeom } } : prev);
      refreshLayerStyle(layerName, data);

      toast("Geometry updated successfully.", 'success');
      cancelEditing();
    } catch (err) {
      toast('Network error saving geometry. No changes were applied.', 'error');
    }
  };

  const cancelEditing = () => {
    setIsEditing(false);
    editingRef.current = false;
    
    // Show original layer again
    const originalLayer = selectedFeature?.leafletLayer;
    if (originalLayer) {
      originalLayer.setOpacity ? originalLayer.setOpacity(1) : originalLayer.setStyle({ fillOpacity: 0.45, opacity: 0.85 });
    }

    // Clear handles and temp polylines
    if (editPolylineRef.current) {
      editPolylineRef.current.remove();
      editPolylineRef.current = null;
    }
    editMarkersRef.current.forEach(m => m.remove());
    editMarkersRef.current = [];
  };

  const deleteFeature = async () => {
    if (!selectedFeature) return;
    const ok = await confirm("Mark this feature as INACTIVE? It will disappear from the public map until a council review restores it.");
    if (!ok) return;

    const layerName = selectedFeature.layerName;
    const featureId = selectedFeature.data.id;

    try {
      const res = await fetch(`${apiBaseUrl}/${getLayerEndpoint(layerName)}/${featureId}/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ status: 'INACTIVE' })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast(`Could not deactivate feature: ${extractApiError(data)}`, 'error');
        return;
      }

      toast("Feature marked as INACTIVE.", 'success');
      const originalLayer = selectedFeature.leafletLayer;
      if (originalLayer && mapRef.current) originalLayer.remove();
      cancelEditing();
      setAttributeDraft(null);
      setSelectedFeature(null);
      fetchData();
    } catch (err) {
      toast('Network error deactivating feature. No changes were applied.', 'error');
    }
  };

  // Re-apply a layer's visual style after an attribute save changes its properties
  const refreshLayerStyle = (layerName: string, data: any) => {
    const layer = selectedFeature?.leafletLayer;
    if (!layer || !('setStyle' in layer)) return;

    const props = { properties: data };
    let style: any = null;
    switch (layerName) {
      case 'roads': style = roadStyle(props); break;
      case 'buildings': style = buildingStyle(props); break;
      case 'land_use': style = landUseStyle(props); break;
      case 'fiber_lines': style = fiberProviderStyle(props); break;
      default:
        if (ASSET_LINE_COLORS[layerName]) style = utilityLineStyle(ASSET_LINE_COLORS[layerName])();
        else if (ASSET_POINT_COLORS[layerName]) style = assetPointStyle(ASSET_POINT_COLORS[layerName])();
    }
    if (style) (layer as any).setStyle(style);
  };

  // --- Attribute (non-geometry) editing ---
  const startAttributeEditing = () => {
    if (!selectedFeature) return;
    if (editingRef.current) cancelEditing();
    const draft: { [key: string]: any } = {};
    Object.keys(selectedFeature.data).forEach((key) => {
      if (ATTRIBUTE_EDIT_EXCLUDE.includes(key)) return;
      const v = selectedFeature.data[key];
      if (v === null || v === undefined || typeof v === 'object') return;
      draft[key] = v;
    });
    setAttributeDraft(draft);
  };

  const saveAttributes = async () => {
    if (!selectedFeature || !attributeDraft) return;
    setSavingAttributes(true);

    const layerName = selectedFeature.layerName;
    const featureId = selectedFeature.data.id;

    try {
      const res = await fetch(`${apiBaseUrl}/${getLayerEndpoint(layerName)}/${featureId}/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(attributeDraft)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast(`Save failed: ${extractApiError(data)}`, 'error');
        setSavingAttributes(false);
        return;
      }

      const merged = { ...selectedFeature.data, ...data };
      const originalLayer = selectedFeature.leafletLayer;
      if (originalLayer && originalLayer.feature) {
        originalLayer.feature.properties = { ...originalLayer.feature.properties, ...data };
      }
      setSelectedFeature((prev: any) => prev ? { ...prev, data: merged } : prev);
      refreshLayerStyle(layerName, merged);

      toast("Feature attributes updated.", 'success');
      setAttributeDraft(null);
      setSavingAttributes(false);
    } catch (err) {
      toast('Network error saving attributes. No changes were applied.', 'error');
      setSavingAttributes(false);
    }
  };

  return (
    <div className="relative w-full h-full flex flex-col md:flex-row bg-[#080c18] overflow-hidden text-slate-100">
      
      {/* 1. Header & Quick Controls */}
      <header className="absolute top-4 left-4 right-4 z-[1000] flex flex-col sm:flex-row items-center gap-3 pointer-events-none">
        
        {/* Logo and Dashboard Tag */}
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-950/80 border border-white/10 shadow-lg pointer-events-auto backdrop-blur-md">
          <MapIcon className="w-5 h-5 text-sky-400 animate-pulse" />
          <h1 className="text-sm font-bold tracking-wider text-slate-100">ISLAND<span className="text-sky-400 font-extrabold">GIS</span></h1>
          <span className="text-[10px] bg-sky-500/20 text-sky-400 px-2 py-0.5 rounded font-mono uppercase">MVP</span>
        </div>

        {/* Global Search Bar */}
        <div className="w-full sm:max-w-md pointer-events-auto">
          <SearchBar apiBaseUrl={apiBaseUrl} onSelectResult={handleSelectSearchResult} />
        </div>

        <div className="flex-1"></div>

        {/* Role Switcher & Login Details (Premium interactive Demo Helper) */}
        <div className="flex items-center gap-2 pointer-events-auto">
          {/* Quick Role Simulation Selector */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-950/85 border border-white/10 shadow-md text-xs">
            <Shield className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-slate-400">Role:</span>
            <select 
              value={role} 
              onChange={(e) => setRole(e.target.value)} 
              className="bg-transparent border-none text-slate-100 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="Guest" className="bg-slate-950">Guest (Public)</option>
              <option value="Registered User" className="bg-slate-950">Registered User</option>
              <option value="Council Staff" className="bg-slate-950">Council Staff</option>
              <option value="Section Admin" className="bg-slate-950">Section Admin</option>
              <option value="Super Admin" className="bg-slate-950">Super Admin</option>
            </select>
          </div>

          {/* Survey Approval Dashboard Trigger */}
          {['Section Admin', 'Super Admin'].includes(role) && (
            <button 
              onClick={() => setShowApprovals(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/35 hover:border-sky-500/50 shadow-md text-xs text-sky-400 cursor-pointer font-medium transition-all"
            >
              <Database className="w-3.5 h-3.5" />
              <span>Survey Ingestion</span>
            </button>
          )}

          {/* Account Management Trigger (Super Admin only) */}
          {role === 'Super Admin' && (
            <button 
              onClick={() => setShowUsers(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/35 hover:border-violet-500/50 shadow-md text-xs text-violet-400 cursor-pointer font-medium transition-all"
            >
              <Users className="w-3.5 h-3.5" />
              <span>Manage Users</span>
            </button>
          )}

          {/* New Feature Tool (Requires write access) */}
          {['Section Admin', 'Super Admin'].includes(role) && !forceChangeRequired && (
            <button 
              onClick={toggleCreate}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl border shadow-md text-xs font-medium cursor-pointer transition-all ${
                createMode
                  ? 'bg-emerald-500/15 border-emerald-500/50 text-emerald-400'
                  : 'bg-slate-950/80 hover:bg-slate-900 border-white/10 hover:border-white/20 text-slate-200'
              }`}
              title="Create a new feature on the map (geometry only; asset code is assigned automatically)"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{createMode ? 'Creating…' : 'New Feature'}</span>
            </button>
          )}

          {/* Measure Tool Toggle */}
          <button 
            onClick={toggleMeasure}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl border shadow-md text-xs font-medium cursor-pointer transition-all ${
              measureMode
                ? 'bg-amber-500/15 border-amber-500/50 text-amber-400'
                : 'bg-slate-950/80 hover:bg-slate-900 border-white/10 hover:border-white/20 text-slate-200'
            }`}
            title="Measure distances and areas (custom tool)"
          >
            <Ruler className="w-3.5 h-3.5" />
            <span>{measureMode ? 'Measuring…' : 'Measure'}</span>
          </button>

          {/* Export Tool */}
          <button 
            onClick={() => setShowExport(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/35 hover:border-emerald-500/50 shadow-md text-xs font-medium text-emerald-400 cursor-pointer transition-all"
            title="Export visible GIS data"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export</span>
          </button>

          {/* Login Button */}
          <button 
            onClick={() => token ? handleLogout() : setShowLogin(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-slate-950/80 hover:bg-slate-900 border border-white/10 hover:border-white/20 shadow-md text-xs font-medium cursor-pointer transition-all"
          >
            {token ? <LogOut className="w-3.5 h-3.5 text-rose-400" /> : <LogIn className="w-3.5 h-3.5 text-emerald-400" />}
            <span>{token ? 'Logout' : 'Admin Login'}</span>
          </button>
        </div>
      </header>

      {/* 2. Main Map Container */}
      <div className="relative flex-1 h-full z-0">
        <div ref={mapContainerRef} className="w-full h-full" />

        {/* Small floating zoom/bounds status info bar */}
        <div className="absolute bottom-4 left-4 z-[999] px-3 py-1.5 rounded-lg bg-slate-950/70 border border-white/5 text-[10px] font-mono text-slate-400 flex items-center gap-3 backdrop-blur-sm">
          <span className="flex items-center gap-1"><Activity className="w-3 h-3 text-emerald-400" /> System Online</span>
          <span>SRID: <b className="text-slate-200">32643</b></span>
          <span>Zoom: <b className="text-slate-200">{zoomLevel}</b></span>
        </div>

        {/* Measurement HUD */}
        {measureMode && (
          <div className="absolute top-20 left-1/2 -translate-x-1/2 z-[999] w-[340px] glass-panel border border-amber-500/30 shadow-xl rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-white/10 bg-slate-900/50">
              <span className="text-[10px] font-bold tracking-wider text-amber-400 uppercase flex items-center gap-1.5">
                <Ruler className="w-3.5 h-3.5" /> Measurement Tool
              </span>
              <button
                onClick={clearMeasure}
                className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
                title="Exit measurement mode"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="p-3 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Click the map to place vertices.</span>
                <span className="font-mono text-amber-400 font-bold">
                  {formatDistance(measureDistance)}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Closed area:</span>
                <span className="font-mono text-emerald-400 font-bold">
                  {measureArea !== null ? formatArea(measureArea) : '—'}
                </span>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={closeMeasureArea}
                  disabled={measureVertexCount < 3 || measureArea !== null}
                  className="flex-1 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 disabled:opacity-40 text-[10px] font-bold text-amber-400 flex items-center justify-center gap-1 cursor-pointer disabled:cursor-not-allowed transition-all"
                >
                  <CheckSquare className="w-3 h-3" />
                  <span>{measureArea !== null ? 'Area Calculated' : 'Close Area'}</span>
                </button>
                <button
                  onClick={clearMeasure}
                  className="flex-1 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-[10px] font-bold text-slate-300 flex items-center justify-center gap-1 cursor-pointer transition-all"
                >
                  <Eraser className="w-3 h-3" />
                  <span>Clear Points</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* New Feature Creation HUD */}
        {createMode && (
          <div className="absolute top-20 left-1/2 -translate-x-1/2 z-[999] w-[340px] glass-panel border border-emerald-500/30 shadow-xl rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-white/10 bg-slate-900/50">
              <span className="text-[10px] font-bold tracking-wider text-emerald-400 uppercase flex items-center gap-1.5">
                <Plus className="w-3.5 h-3.5" /> New Feature
              </span>
              <button
                onClick={clearCreate}
                className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
                title="Cancel creation"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="p-3 space-y-2">
              <select
                value={createLayer}
                onChange={(e) => setCreateLayer(e.target.value)}
                className="w-full px-2.5 py-2 bg-slate-950 border border-white/10 focus:border-emerald-400 focus:outline-none rounded-lg text-xs text-slate-200 cursor-pointer"
              >
                {Object.keys(LAYER_LABELS).map((name) => (
                  <option key={name} value={name} className="bg-slate-950">{LAYER_LABELS[name]}</option>
                ))}
              </select>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Click the map to place vertices.</span>
                <span className="font-mono text-emerald-400 font-bold">{createVertexCount} pts</span>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={saveNewFeature}
                  disabled={createVertexCount < (LAYER_GEOMETRY_KIND[createLayer] === 'point' ? 1 : LAYER_GEOMETRY_KIND[createLayer] === 'line' ? 2 : 3)}
                  className="flex-1 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 disabled:opacity-40 text-[10px] font-bold text-emerald-400 flex items-center justify-center gap-1 cursor-pointer disabled:cursor-not-allowed transition-all"
                >
                  <Save className="w-3 h-3" />
                  <span>Create Feature</span>
                </button>
                <button
                  onClick={clearCreate}
                  className="flex-1 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-[10px] font-bold text-slate-300 flex items-center justify-center gap-1 cursor-pointer transition-all"
                >
                  <Eraser className="w-3 h-3" />
                  <span>Clear Points</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 3. FLOATING LEFT PANEL: Layer Controls */}
      <div className="absolute top-20 left-4 z-[999] w-64 max-h-[calc(100%-110px)] flex flex-col glass-panel overflow-hidden">
        {/* Panel Tabs */}
        <div className="flex border-b border-white/10 text-xs font-semibold">
          <button 
            onClick={() => setActiveTab('layers')}
            className={`flex-1 py-2.5 text-center flex items-center justify-center gap-1 cursor-pointer transition-colors ${activeTab === 'layers' ? 'bg-white/5 text-white border-b-2 border-sky-400' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Map Layers</span>
          </button>
          <button 
            onClick={() => setActiveTab('metadata')}
            className={`flex-1 py-2.5 text-center flex items-center justify-center gap-1 cursor-pointer transition-colors ${activeTab === 'metadata' ? 'bg-white/5 text-white border-b-2 border-sky-400' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Metadata Standard</span>
          </button>
        </div>

        {/* Tab 1: Layer Controls Content */}
        {activeTab === 'layers' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            
            {/* Base Maps Group */}
            <div className="space-y-2">
              <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Basemaps</h3>
              <div className="space-y-1.5">
                {[
                  { id: 'cartodbDark', label: 'Dark Canvas (CARTO)', color: 'bg-slate-800' },
                  { id: 'osm', label: 'OpenStreetMap (OSM)', color: 'bg-emerald-800' },
                  { id: 'orthophoto', label: 'Drone Orthophoto (COG)', color: 'bg-sky-700' },
                ].map(layer => (
                  <label key={layer.id} className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded bg-white/5 hover:bg-white/10 cursor-pointer transition-all">
                    <span className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${layer.color}`} />
                      <span className="text-slate-200">{layer.label}</span>
                    </span>
                    <input 
                      type="checkbox" 
                      checked={visibleLayers[layer.id]} 
                      onChange={() => handleLayerToggle(layer.id)}
                      className="rounded accent-sky-400 cursor-pointer"
                    />
                  </label>
                ))}
              </div>
            </div>

            {/* Core Vector Layers */}
            <div className="space-y-2">
              <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Core Registries</h3>
              <div className="space-y-1.5">
                {[
                  { id: 'buildings', label: 'Buildings (Footprints)', color: 'bg-sky-500' },
                  { id: 'roads', label: 'Road Networks', color: 'bg-orange-500' },
                  { id: 'land_use', label: 'Land Use Zones', color: 'bg-yellow-500' },
                  { id: 'facilities', label: 'Public Facilities', color: 'bg-sky-400' },
                ].map(layer => (
                  <label key={layer.id} className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded bg-white/5 hover:bg-white/10 cursor-pointer transition-all">
                    <span className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded ${layer.color}`} />
                      <span className="text-slate-200">{layer.label}</span>
                    </span>
                    <input 
                      type="checkbox" 
                      checked={visibleLayers[layer.id]} 
                      onChange={() => handleLayerToggle(layer.id)}
                      className="rounded accent-sky-400 cursor-pointer"
                    />
                  </label>
                ))}
              </div>
            </div>

            {/* Assets & Infrastructure */}
            <div className="space-y-2">
              <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Infrastructure & Assets</h3>
              <div className="space-y-1.5">
                {[
                  { id: 'street_lights', label: 'Street Lights (Point)', color: 'bg-yellow-400' },
                  { id: 'water_lines', label: 'Water Pipes (Line)', color: 'bg-blue-500' },
                  { id: 'water_nodes', label: 'Water Valves (Point)', color: 'bg-blue-400' },
                  { id: 'sewer_lines', label: 'Sewer Gravity (Line)', color: 'bg-violet-600' },
                  { id: 'manholes', label: 'Sewer Manholes (Point)', color: 'bg-violet-400' },
                  { id: 'sewer_junctions', label: 'Sewer Junctions (Point)', color: 'bg-fuchsia-400' },
                  { id: 'electrical_lines', label: 'Power Cables (Line)', color: 'bg-red-500' },
                  { id: 'electrical_nodes', label: 'Distribution Box (Point)', color: 'bg-red-400' },
                  { id: 'fiber_lines', label: 'Fiber Cables (Line)', color: 'bg-emerald-500' },
                  { id: 'fiber_nodes', label: 'Fiber Cabinets (Point)', color: 'bg-emerald-400' },
                ].map(layer => (
                  <label key={layer.id} className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded bg-white/5 hover:bg-white/10 cursor-pointer transition-all">
                    <span className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${layer.color}`} />
                      <span className="text-slate-200">{layer.label}</span>
                    </span>
                    <input 
                      type="checkbox" 
                      checked={visibleLayers[layer.id]} 
                      onChange={() => handleLayerToggle(layer.id)}
                      className="rounded accent-sky-400 cursor-pointer"
                    />
                  </label>
                ))}
              </div>

              {/* Dynamic Fiber Provider Legend (only providers present in loaded data) */}
              {visibleLayers.fiber_lines && fiberProviders.length > 0 && (
                <div className="mt-2 pl-2 space-y-1.5 border-l border-white/10">
                  <span className="text-[9px] font-bold tracking-wider text-slate-500 uppercase">Fiber Providers</span>
                  {fiberProviders.map(provider => (
                    <div key={provider} className="flex items-center gap-2 text-[10px] font-medium text-slate-300">
                      <span className="w-4 h-0.5 rounded-full shrink-0" style={{ background: fiberProviderColor(provider) }} />
                      <span className="uppercase">{provider}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        )}

        {/* Tab 2: Standard CRS Specs */}
        {activeTab === 'metadata' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-3.5 text-xs text-slate-300">
            <div className="bg-white/5 p-3 rounded-lg border border-white/5">
              <h4 className="font-bold text-slate-100 flex items-center gap-1.5 mb-1.5"><Shield className="w-3.5 h-3.5 text-sky-400" /> CRS Specifications</h4>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                To guarantee millimeter-perfect measurement offsets, all geometries are saved in standard meters projection:
              </p>
              <div className="mt-2 space-y-1.5 font-mono text-[10px]">
                <div className="flex justify-between border-b border-white/5 py-1"><span className="text-slate-500">Storage CRS:</span> <span className="text-sky-400">EPSG:32643 (UTM 43N)</span></div>
                <div className="flex justify-between border-b border-white/5 py-1"><span className="text-slate-500">Export CRS:</span> <span className="text-amber-400">EPSG:4326 (WGS84)</span></div>
                <div className="flex justify-between py-1"><span className="text-slate-500">Tiles CRS:</span> <span className="text-slate-300">EPSG:3857 (Mercator)</span></div>
              </div>
            </div>

            <div className="bg-white/5 p-3 rounded-lg border border-white/5">
              <h4 className="font-bold text-slate-100 flex items-center gap-1.5 mb-1.5"><Shield className="w-3.5 h-3.5 text-amber-400" /> Asset Coding Standard</h4>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Unique identifiers mapped for field operations:
              </p>
              <ul className="mt-2 space-y-1 font-mono text-[10px] text-slate-300 list-disc list-inside">
                <li>Buildings: <b className="text-sky-400">BLDG-XXXX</b></li>
                <li>Roads: <b className="text-orange-400">ROAD-XXXX</b></li>
                <li>Street Lights: <b className="text-yellow-400">SL-XXXX</b></li>
                <li>Manholes: <b className="text-violet-400">MH-XXXX</b></li>
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* 4. FLOATING RIGHT PANEL: Feature Attribute Details */}
      {selectedFeature && (
        <div className="absolute top-20 right-4 z-[999] w-80 max-h-[calc(100%-110px)] flex flex-col glass-panel overflow-hidden animate-fade-in">
          
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-white/10 bg-slate-900/40">
            <div>
              <span className="text-[10px] font-bold text-sky-400 uppercase tracking-widest">{selectedFeature.layerName.slice(0, -1)} registry</span>
              <h2 className="text-sm font-bold text-slate-100 font-mono">{selectedFeature.data.asset_code || 'No Asset Code'}</h2>
            </div>
            <button 
              onClick={() => { cancelEditing(); setAttributeDraft(null); setSelectedFeature(null); }}
              className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Tab bar */}
          <div className="flex border-b border-white/10 bg-slate-900/30 shrink-0">
            {(['details', 'lineage', 'history'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setFeatureTab(tab)}
                className={`flex-1 py-2 text-[9px] font-bold uppercase tracking-wider cursor-pointer transition-colors ${featureTab === tab ? 'text-sky-400 border-b-2 border-sky-400' : 'text-slate-500 hover:text-slate-300'}`}
              >
                {tab === 'details' ? 'Details' : tab === 'lineage' ? 'Lineage' : 'History'}
              </button>
            ))}
          </div>

          {/* Scrollable details */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            
            {/* ===== DETAILS TAB ===== */}
            {featureTab === 'details' && (<>
            {/* Core attributes list */}
            <div className="space-y-2">
              <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Attributes</h3>
              {attributeDraft ? (
                <div className="bg-slate-950/40 border border-amber-500/20 rounded-lg p-3 space-y-2.5 text-xs">
                  {Object.keys(attributeDraft).length === 0 && (
                    <p className="text-[10px] text-slate-500 italic">No editable attributes on this feature.</p>
                  )}
                  {Object.keys(attributeDraft).map(key => (
                    <div key={key} className="space-y-1">
                      <span className="text-[10px] text-slate-400 capitalize">{key.replace('_', ' ').replace('id', 'ID')}</span>
                      {typeof selectedFeature.data[key] === 'boolean' ? (
                        <select
                          value={attributeDraft[key] ? 'true' : 'false'}
                          onChange={(e) => setAttributeDraft((prev: any) => ({ ...prev, [key]: e.target.value === 'true' }))}
                          className="w-full px-2 py-1.5 bg-slate-900 border border-white/10 focus:border-amber-400 focus:outline-none rounded text-xs text-slate-200 cursor-pointer"
                        >
                          <option value="true">Yes</option>
                          <option value="false">No</option>
                        </select>
                      ) : (
                        <input
                          type={typeof selectedFeature.data[key] === 'number' ? 'number' : 'text'}
                          value={attributeDraft[key] ?? ''}
                          onChange={(e) => setAttributeDraft((prev: any) => ({ ...prev, [key]: e.target.value }))}
                          className="w-full px-2 py-1.5 bg-slate-900 border border-white/10 focus:border-amber-400 focus:outline-none rounded text-xs text-slate-200"
                        />
                      )}
                    </div>
                  ))}
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      onClick={saveAttributes}
                      disabled={savingAttributes}
                      className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 disabled:bg-amber-700 text-slate-950 text-[10px] font-bold cursor-pointer disabled:cursor-not-allowed transition-all"
                    >
                      <Save className="w-3 h-3" />
                      {savingAttributes ? 'Saving…' : 'Save Attributes'}
                    </button>
                    <button
                      onClick={() => setAttributeDraft(null)}
                      className="flex-1 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-[10px] font-bold text-slate-300 cursor-pointer transition-all"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-slate-950/40 border border-white/5 rounded-lg p-3 space-y-2 text-xs">
                  {Object.keys(selectedFeature.data).map(key => {
                    // Skip system objects, geometry, and lists
                    if (['id', 'geometry', 'addresses_list', 'asset_code', 'created_by', 'status'].includes(key)) return null;
                    
                    // Label formatting
                    const label = key.replace('_', ' ').replace('id', 'ID');
                    let val = selectedFeature.data[key];
                    if (typeof val === 'boolean') val = val ? 'Yes' : 'No';
                    
                    return (
                      <div key={key} className="flex justify-between border-b border-white/5 pb-1.5 last:border-0 last:pb-0">
                        <span className="text-slate-400 capitalize">{label}:</span>
                        <span className="font-semibold text-slate-200 font-mono">{val || '-'}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Address Registry Tabular section for Buildings */}
            {selectedFeature.layerName === 'buildings' && (
              <div className="space-y-2">
                <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Registered Addresses (Households)</h3>
                <div className="space-y-1.5">
                  {selectedFeature.data.addresses_list && selectedFeature.data.addresses_list.length > 0 ? (
                    selectedFeature.data.addresses_list.map((addr: any) => (
                      <div key={addr.id} className="p-2.5 rounded-lg bg-white/5 border border-white/5 text-xs">
                        <div className="font-bold text-slate-200">{addr.address_label}</div>
                        <div className="text-[10px] text-slate-400 font-mono mt-0.5">Code: {addr.asset_code}</div>
                        {addr.notes && <div className="text-[10px] text-sky-400 mt-1 italic">Note: {addr.notes}</div>}
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-slate-500 italic p-3 text-center bg-white/5 rounded-lg border border-white/5 border-dashed">
                      No household addresses linked to this building footprint yet.
                    </div>
                  )}
                </div>
              </div>
            )}

            </>)}

            {/* ===== LINEAGE TAB ===== */}
            {featureTab === 'lineage' && (
              <div className="space-y-2">
                <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Data Lineage</h3>
                <div className="bg-slate-950/40 border border-white/5 rounded-lg p-3 space-y-2 text-[10px] font-mono text-slate-400">
                  <div className="flex justify-between"><span>Survey Date:</span> <span className="text-slate-300">{selectedFeature.data.survey_date || 'Initial Upload'}</span></div>
                  <div className="flex justify-between"><span>Source File:</span> <span className="text-slate-300 truncate max-w-[120px]">{selectedFeature.data.source_file || 'System Seed'}</span></div>
                  <div className="flex justify-between"><span>Accuracy Limit:</span> <span className="text-emerald-400">{selectedFeature.data.accuracy ? `${selectedFeature.data.accuracy} m` : 'Unspecified'}</span></div>
                  <div className="flex justify-between"><span>Status:</span> <span className="text-sky-400 font-bold">{selectedFeature.data.status || 'ACTIVE'}</span></div>
                  <div className="flex justify-between"><span>Created By:</span> <span className="text-slate-300">{selectedFeature.data.created_by_name || selectedFeature.data.created_by || '—'}</span></div>
                  <div className="flex justify-between"><span>Last Updated:</span> <span className="text-slate-300">{selectedFeature.data.updated_at ? new Date(selectedFeature.data.updated_at).toLocaleString() : '—'}</span></div>
                </div>
                <div className="bg-slate-950/40 border border-sky-500/10 rounded-lg p-3">
                  <h4 className="text-[9px] font-bold text-sky-400 uppercase tracking-wider mb-1.5">Provenance</h4>
                  <div className="flex items-center gap-2 font-mono text-[9px] text-slate-500">
                    <span>Survey Batch</span>
                    <span className="text-slate-600">→</span>
                    <span>Staged</span>
                    <span className="text-slate-600">→</span>
                    <span>Merged</span>
                    <span className="text-slate-600">→</span>
                    <span className="text-emerald-400">Active</span>
                  </div>
                  <p className="text-[9px] text-slate-600 mt-2 leading-relaxed">
                    This feature is an active production record derived from the survey batch linked above. Its source file and accuracy limit document the field-survey provenance.
                  </p>
                </div>
              </div>
            )}

            {/* ===== HISTORY TAB ===== */}
            {featureTab === 'history' && (
              <div className="space-y-2">
                <h3 className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">Record History</h3>
                <div className="relative pl-4 border-l border-white/10 space-y-4">
                  {[
                    {
                      icon: 'REGISTERED',
                      title: 'Asset Registered',
                      detail: `Survey / production seed for ${selectedFeature.data.source_file || 'initial system dataset'}, recorded against asset ${selectedFeature.data.asset_code}.`,
                      when: selectedFeature.data.created_at ? new Date(selectedFeature.data.created_at).toLocaleString() : 'Not recorded',
                      tone: 'sky'
                    },
                    {
                      icon: 'SURVEYED',
                      title: 'Field Survey Dated',
                      detail: selectedFeature.data.survey_date
                        ? `Survey observation captured on ${new Date(selectedFeature.data.survey_date).toLocaleDateString()} with ${selectedFeature.data.accuracy ? `a documented accuracy of ${selectedFeature.data.accuracy} m` : 'no stated accuracy limit'}.`
                        : 'Survey date not recorded for this feature.',
                      when: selectedFeature.data.survey_date || 'Not recorded',
                      tone: 'amber'
                    },
                    {
                      icon: 'UPDATED',
                      title: 'Record Last Modified',
                      detail: `Current status is ${selectedFeature.data.status || 'ACTIVE'}; the record was last touched as shown.`,
                      when: selectedFeature.data.updated_at ? new Date(selectedFeature.data.updated_at).toLocaleString() : 'Not recorded',
                      tone: 'emerald'
                    }
                  ].map((entry, i) => (
                    <div key={i} className="relative">
                      <span className={`absolute -left-[19px] top-1 w-2.5 h-2.5 rounded-full ${entry.tone === 'sky' ? 'bg-sky-400' : entry.tone === 'amber' ? 'bg-amber-400' : 'bg-emerald-400'}`} />
                      <div className="text-[10px] font-bold text-slate-200">{entry.title}</div>
                      <div className="text-[10px] text-slate-400 leading-relaxed mt-0.5">{entry.detail}</div>
                      <div className="text-[9px] text-slate-600 font-mono mt-1">{entry.when}</div>
                    </div>
                  ))}
                </div>
                <p className="text-[9px] text-slate-600 italic pt-1">
                  Full audit history (approvals, rejections, merges) is tracked at the survey-session level in the Ingestion pipeline.
                </p>
              </div>
            )}

          </div>

          {/* Action Footer: Restricted editing buttons */}
          {['Council Staff', 'Section Admin', 'Super Admin'].includes(role) && (
            <div className="p-4 border-t border-white/10 bg-slate-900/40 flex items-center gap-2">
              {!isEditing ? (
                <>
                  {['Section Admin', 'Super Admin'].includes(role) && !forceChangeRequired && (
                    <button 
                      onClick={startEditingGeometry}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 hover:border-amber-500/50 text-xs font-semibold text-amber-400 cursor-pointer transition-all"
                    >
                      <Edit className="w-3.5 h-3.5" />
                      <span>Edit Shape</span>
                    </button>
                  )}
                  {['Section Admin', 'Super Admin'].includes(role) && (
                    <button 
                      onClick={() => attributeDraft ? setAttributeDraft(null) : startAttributeEditing()}
                      className={`flex items-center justify-center p-2 rounded-lg border cursor-pointer transition-all ${
                        attributeDraft ? 'bg-amber-500/15 border-amber-500/40 text-amber-400' : 'bg-white/5 hover:bg-white/10 border-white/10 text-slate-300'
                      }`}
                      title={attributeDraft ? 'Cancel attribute editing' : 'Edit feature attributes'}
                    >
                      <Edit className="w-4 h-4" />
                    </button>
                  )}
                  {['Super Admin'].includes(role) && (
                    <button 
                      onClick={deleteFeature}
                      className="flex items-center justify-center p-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 hover:border-rose-500/50 text-rose-400 cursor-pointer transition-all"
                      title="Deactivate Feature"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </>
              ) : (
                <>
                  <button 
                    onClick={saveEditedGeometry}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-slate-950 text-xs font-bold cursor-pointer transition-all"
                  >
                    <Save className="w-3.5 h-3.5" />
                    <span>Save Edits</span>
                  </button>
                  <button 
                    onClick={cancelEditing}
                    className="flex items-center justify-center py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold cursor-pointer transition-all"
                  >
                    Cancel
                  </button>
                </>
              )}
            </div>
          )}

        </div>
      )}

      {/* 5. MODAL POPUPS: Admin Authentication Panel */}
      {showLogin && (
        <AdminPanel 
          apiBaseUrl={apiBaseUrl} 
          onClose={() => setShowLogin(false)} 
          onLoginSuccess={handleLoginSuccess} 
        />
      )}

      {/* Forced password change overlay (blocking until changed or logged out) */}
      {showForcedChange && token && forceChangeRequired && (
        <ForcePasswordChangeModal
          apiBaseUrl={apiBaseUrl}
          token={token}
          onSuccess={() => {
            setForceChangeRequired(false);
            setShowForcedChange(false);
            toast('Password changed. You can now edit the map.', 'success');
          }}
          onLogout={() => {
            handleLogout();
            toast('Logged out. Sign in again with your new password.', 'info');
          }}
        />
      )}

      {/* 6. MODAL POPUPS: Survey Ingestion & Staging Review Portal */}
      {showApprovals && (
        <ApprovalDashboard 
          apiBaseUrl={apiBaseUrl} 
          token={token} 
          role={role}
          onClose={() => setShowApprovals(false)} 
          onRefreshData={fetchData}
        />
      )}

      {/* 6b. MODAL POPUPS: Super Admin Account Management */}
      {showUsers && role === 'Super Admin' && (
        <UsersPanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          onClose={() => setShowUsers(false)}
        />
      )}

      {/* 7. MODAL POPUPS: Data Export */}
      <ExportModal
        apiBaseUrl={apiBaseUrl}
        isOpen={showExport}
        onClose={() => setShowExport(false)}
        bbox={showExport ? getMapBounds() : undefined}
      />

    </div>
  );
}
