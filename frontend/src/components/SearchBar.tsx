'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Search, MapPin, X, Navigation, Building2, HelpCircle } from 'lucide-react';

interface SearchBarProps {
  apiBaseUrl: string;
  onSelectResult: (result: any) => void;
}

export default function SearchBar({ apiBaseUrl, onSelectResult }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Debounced search trigger
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    const delayDebounceFn = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(`${apiBaseUrl}/search/?q=${encodeURIComponent(query)}`);
        if (res.ok) {
          const data = await res.json();
          // Merge text matches
          setResults(data.text_matches || []);
          setIsOpen(true);
        }
      } catch (err) {
        console.error("Search API error:", err);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(delayDebounceFn);
  }, [query]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (item: any) => {
    onSelectResult(item);
    setQuery(item.house_name || item.road_name || item.name || '');
    setIsOpen(false);
  };

  const clearSearch = () => {
    setQuery('');
    setResults([]);
    setIsOpen(false);
  };

  return (
    <div ref={searchRef} className="relative w-full pointer-events-auto">
      
      {/* Search Input Box */}
      <div className="relative flex items-center w-full">
        <Search className="absolute left-3 w-4 h-4 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search houses, roads, facilities..."
          className="w-full pl-10 pr-10 py-2.5 bg-slate-950/80 border border-white/10 hover:border-white/20 focus:border-sky-400 focus:outline-none rounded-xl text-xs text-slate-200 shadow-lg backdrop-blur-md transition-all placeholder-slate-500"
        />
        {query && (
          <button 
            onClick={clearSearch}
            className="absolute right-3 p-1 rounded-full hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
          >
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Autocomplete Results Panel */}
      {isOpen && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 max-h-72 overflow-y-auto glass-panel z-[1010] animate-fade-in p-2 divide-y divide-white/5">
          {results.map((item) => {
            const isBldg = item.type === 'building';
            const isRoad = item.type === 'road';
            
            return (
              <button
                key={item.id}
                onClick={() => handleSelect(item)}
                className="w-full flex items-start gap-3 p-2.5 hover:bg-white/5 rounded-lg text-left transition-colors cursor-pointer"
              >
                {/* Icon wrapper */}
                <div className={`mt-0.5 p-1.5 rounded-lg ${
                  isBldg ? 'bg-sky-500/10 text-sky-400' :
                  isRoad ? 'bg-orange-500/10 text-orange-400' : 'bg-emerald-500/10 text-emerald-400'
                }`}>
                  {isBldg ? <Building2 className="w-4 h-4" /> : 
                   isRoad ? <Navigation className="w-4 h-4 rotate-45" /> : <MapPin className="w-4 h-4" />}
                </div>

                {/* Details */}
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-slate-200 truncate">
                    {item.house_name || item.road_name || item.name || 'Unnamed Asset'}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-slate-500">
                    <span className="uppercase">{item.type}</span>
                    <span>•</span>
                    <span>{item.asset_code}</span>
                  </div>
                  {item.building_type && (
                    <span className="inline-block mt-1 text-[9px] px-1.5 py-0.5 rounded bg-slate-900 border border-white/5 text-slate-400">
                      {item.building_type}
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {isOpen && query.length >= 2 && results.length === 0 && !loading && (
        <div className="absolute top-full left-0 right-0 mt-2 glass-panel p-4 text-center z-[1010] animate-fade-in">
          <HelpCircle className="w-6 h-6 text-slate-500 mx-auto mb-1.5" />
          <div className="text-xs text-slate-300 font-semibold">No results match your search</div>
          <p className="text-[10px] text-slate-500 mt-0.5">Check for spelling or coordinate typos.</p>
        </div>
      )}
    </div>
  );
}
