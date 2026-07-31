import React from 'react';
import { MissionState } from '../types';
import { Cpu, Plane, Battery, Activity, ShieldCheck, Terminal } from 'lucide-react';

interface DroneRoverTelemetryProps {
  state: MissionState;
}

export const DroneRoverTelemetry: React.FC<DroneRoverTelemetryProps> = ({ state }) => {
  const { rover, drone, logs } = state;

  return (
    <div id="telemetry-card" className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl text-white">
      {/* Заголовок */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-emerald-400" />
          <h2 className="text-base font-bold text-slate-100">Телеметрия оборудования</h2>
        </div>
        <span className="text-xs font-mono text-slate-400">ROS MAVROS + REST API</span>
      </div>

      {/* Сетка телеметрии */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        
        {/* Телеметрия БПЛА */}
        <div className="bg-slate-800/60 p-3.5 rounded-xl border border-slate-700/70">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Plane className="w-4 h-4 text-cyan-400" />
              <span className="font-bold text-xs text-slate-200">БПЛА «Сверх»</span>
            </div>
            <span className="text-[10px] font-mono text-cyan-400 px-1.5 py-0.5 rounded bg-cyan-950 border border-cyan-800">
              {drone.status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div>
              <span className="text-slate-400 text-[10px]">Высота:</span>
              <p className="text-base font-bold text-white">{drone.altitude} м</p>
            </div>
            <div>
              <span className="text-slate-400 text-[10px]">Фрейм системы:</span>
              <p className="text-sm font-semibold text-cyan-300">{drone.frameId}</p>
            </div>
            <div>
              <span className="text-slate-400 text-[10px]">Заряд батареи:</span>
              <p className="text-sm font-semibold text-emerald-400 flex items-center gap-1">
                <Battery className="w-3.5 h-3.5" />
                <span>{drone.battery}%</span>
              </p>
            </div>
            <div>
              <span className="text-slate-400 text-[10px]">Маркеры ArUco:</span>
              <p className="text-sm font-semibold text-indigo-300">{drone.arucoVisible} видно</p>
            </div>
          </div>
        </div>

        {/* Телеметрия Ровера */}
        <div className="bg-slate-800/60 p-3.5 rounded-xl border border-slate-700/70">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-emerald-400" />
              <span className="font-bold text-xs text-slate-200">Ровер «Сверх»</span>
            </div>
            <span className="text-[10px] font-mono text-emerald-400 px-1.5 py-0.5 rounded bg-emerald-950 border border-emerald-800">
              {rover.status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div>
              <span className="text-slate-400 text-[10px]">Текущая ячейка:</span>
              <p className="text-base font-bold text-white">{rover.cell}</p>
            </div>
            <div>
              <span className="text-slate-400 text-[10px]">Скорость:</span>
              <p className="text-sm font-semibold text-emerald-300">{rover.speed} м/с</p>
            </div>
            <div>
              <span className="text-slate-400 text-[10px]">Заряд батареи:</span>
              <p className="text-sm font-semibold text-emerald-400 flex items-center gap-1">
                <Battery className="w-3.5 h-3.5" />
                <span>{rover.battery}%</span>
              </p>
            </div>
            <div>
              <span className="text-slate-400 text-[10px]">Посл. команда:</span>
              <p className="text-xs font-semibold text-slate-300 truncate">{rover.lastCmd}</p>
            </div>
          </div>
        </div>

      </div>

      {/* Журнал событий миссии */}
      <div>
        <div className="text-xs font-bold text-slate-300 mb-2 flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5 text-cyan-400" />
            <span>Журнал телеметрии и событий</span>
          </span>
          <span className="text-[10px] font-mono text-slate-500">{logs.length} записей</span>
        </div>

        <div className="bg-slate-950 rounded-lg border border-slate-800 p-2.5 h-36 overflow-y-auto font-mono text-xs space-y-1.5">
          {logs.map((log, idx) => (
            <div key={idx} className="flex items-start gap-2">
              <span className="text-slate-500 text-[10px] shrink-0">{log.timestamp}</span>
              <span
                className={`font-semibold text-[10px] px-1 rounded shrink-0 ${
                  log.level === 'dodge'
                    ? 'bg-rose-500/20 text-rose-300'
                    : log.level === 'warn'
                    ? 'bg-amber-500/20 text-amber-300'
                    : 'bg-cyan-500/20 text-cyan-300'
                }`}
              >
                [{log.level.toUpperCase()}]
              </span>
              <span className="text-slate-300">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
