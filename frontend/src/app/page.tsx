'use client';

import dynamic from 'next/dynamic';

// Dynamically import MapViewer to bypass Next.js SSR window errors
const MapViewer = dynamic(() => import('@/components/MapViewer'), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex flex-col items-center justify-center bg-[#080c18] text-slate-400 gap-3">
      <div className="w-8 h-8 rounded-full border-4 border-t-sky-400 border-r-transparent border-slate-700 animate-spin" />
      <span className="text-xs font-mono tracking-wider animate-pulse">LOADING GIS ENGINE...</span>
    </div>
  )
});

export default function Home() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost/api';

  return (
    <main className="w-full h-full">
      <MapViewer apiBaseUrl={apiBaseUrl} />
    </main>
  );
}

