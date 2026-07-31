import React from 'react';
import { Shield, Radio, Terminal, Cpu, Play, Square, RefreshCw, Code2, AlertTriangle } from 'lucide-react';
import { MissionState, MissionMode } from '../types';

interface HeaderProps {
  state: MissionState;
  onStart: () => void;
  onStop: () => void;
  onModeChange: (mode: MissionMode) => void;
  onTestConnection: () => void;
  onOpenCode: () => void;
  testingConn: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  state,
  onStart,
  onStop,
  onModeChange,
  onTestConnection,
  onOpenCode,
  testingConn
}) => {
  return (
    <header id="header-container" className="bg-slate-900 border-b border-slate-800 px-4 py-3 text-white sticky top-0 z-50 shadow-lg">
      <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-center justify-between gap-4">
        
        {/* Brand & System Identifier */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-gradient-to-br from-indigo-500 to-cyan-500 rounded-xl shadow-md text-white">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-white">
                Пульт Управления «Сверх»
              </h1>
              <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-mono">
                БПЛА и Ровер Сверх
              </span>
            </div>
            <p className="text-xs text-slate-400 flex items-center gap-2 mt-0.5">
              <span>Сетка ArUco A1..F6</span>
              <span>•</span>
              <span className="text-cyan-400 font-mono">Старт: {state.rover.cell}</span>
            </p>
          </div>
        </div>

        {/* IP Credentials & Connection Badges */}
        <div className="flex items-center gap-2 flex-wrap text-xs font-mono">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700">
            <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
            <span className="text-slate-400">БПЛА:</span>
            <span className="text-cyan-300 font-semibold">{state.ipConfig.droneIp}</span>
            <span className="text-slate-500">(sverk)</span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700">
            <Cpu className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Ровер:</span>
            <span className="text-emerald-300 font-semibold">192.168.1.33</span>
            <span className="text-slate-500">:8767/8765</span>
          </div>

          <button
            id="test-connection-btn"
            onClick={onTestConnection}
            disabled={testingConn}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700"
            title="Проверить связь с платами оборудования"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${testingConn ? 'animate-spin text-amber-400' : ''}`} />
            <span>{testingConn ? 'Проверка...' : 'Проверить связь'}</span>
          </button>
        </div>

        {/* Controls & Hardware Status */}
        <div className="flex items-center gap-3">
          {/* Hardware Active Indicator */}
          <div className="flex items-center gap-1.5 px-3 py-1 bg-emerald-950/80 rounded-lg border border-emerald-700/50 text-xs font-mono text-emerald-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
            <span>ОБОРУДОВАНИЕ ГОТОВО</span>
          </div>

          {/* Inspect Python Source Code */}
          <button
            id="view-code-btn"
            onClick={onOpenCode}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-all"
          >
            <Code2 className="w-4 h-4 text-cyan-400" />
            <span>Исходный код Python</span>
          </button>

          {/* Start / Stop Buttons */}
          {state.status === 'RUNNING' || state.status === 'EVADING' ? (
            <button
              id="stop-mission-btn"
              onClick={onStop}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold text-xs transition-all shadow-md shadow-red-900/30 animate-pulse"
            >
              <Square className="w-4 h-4" />
              <span>ОСТАНОВИТЬ МИССИЮ</span>
            </button>
          ) : (
            <button
              id="start-mission-btn"
              onClick={onStart}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-all shadow-md shadow-emerald-900/30"
            >
              <Play className="w-4 h-4" />
              <span>ЗАПУСК МИССИИ</span>
            </button>
          )}
        </div>

      </div>
    </header>
  );
};
