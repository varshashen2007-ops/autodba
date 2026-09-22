import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

function App() {
  return <main><h1>AutoDBA</h1><p>PostgreSQL Performance Engineering Console</p><div className="card"><b>System status</b><span>● Ready</span></div></main>
}
createRoot(document.getElementById('root')!).render(<App />)
