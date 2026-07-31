import React from 'react';
import { SAFE_ZONES, ENEMY_ZONES, GRID_ROWS, GRID_COLS } from '../data/gridConfig';
import { MissionState } from '../types';
import { Navigation, Target, Shield, AlertTriangle, Disc } from 'lucide-react';

interface GridMap2DProps {
  state: MissionState;
}

export const GridMap2D: React.FC<GridMap2DProps> = ({ state }) => {
  const { rover, drone, enemy, targetCell, activePath } = state;

  return (
    <div id="grid-map-card" className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl text-white">
      {/* Шапка карты и статус */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4 border-b border-slate-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base font-bold text-slate-100">Карта полигона 6x6 ArUco (Мониторинг)</h2>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Безопасная зона (18 ячеек) vs Зона патрулирования противника (18 ячеек)
          </p>
        </div>

        {/* Текущие ориентиры миссии */}
        <div className="flex items-center gap-2 font-mono text-xs">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700">
            <Target className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Цель:</span>
            <span className="text-emerald-300 font-bold">{targetCell}</span>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700">
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
            <span className="text-slate-400">Противник:</span>
            <span className="text-rose-300 font-bold">{enemy.cell}</span>
          </div>
        </div>
      </div>

      {/* Контейнер сетки */}
      <div className="relative overflow-x-auto pb-2">
        <div className="min-w-[540px] max-w-2xl mx-auto">
          
          {/* Колонки */}
          <div className="grid grid-cols-7 gap-1.5 mb-1 text-center font-mono text-xs font-semibold text-slate-400">
            <div className="w-8"></div>
            {GRID_COLS.map((col) => (
              <div key={col} className="py-1 bg-slate-800/50 rounded text-cyan-300">
                Столбец {col}
              </div>
            ))}
          </div>

          {/* Строки сетки */}
          {GRID_ROWS.map((row) => (
            <div key={row} className="grid grid-cols-7 gap-1.5 mb-1.5 items-center">
              {/* Буква строки */}
              <div className="w-8 h-16 sm:h-20 bg-slate-800/50 rounded flex items-center justify-center font-mono text-sm font-bold text-cyan-300">
                {row}
              </div>

              {/* Ячейки */}
              {GRID_COLS.map((col) => {
                const cell = `${row}${col}`;
                const isSafe = SAFE_ZONES.has(cell);
                const isRover = rover.cell === cell;
                const isEnemy = enemy.cell === cell;
                const isDrone = drone.cell === cell;
                const isTarget = targetCell === cell;
                const isInPath = activePath.includes(cell);
                const arucoId = (row.charCodeAt(0) - 65) * 6 + col + 100;

                return (
                  <div
                    key={cell}
                    id={`cell-${cell}`}
                    className={`relative h-16 sm:h-20 rounded-lg p-1 transition-all duration-200 flex flex-col justify-between text-left border ${
                      isRover
                        ? 'ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-900 bg-cyan-950/80 border-cyan-400 shadow-lg shadow-cyan-950/50'
                        : isEnemy
                        ? 'ring-2 ring-rose-500 ring-offset-2 ring-offset-slate-900 bg-rose-950/80 border-rose-500 shadow-lg shadow-rose-950/50'
                        : isSafe
                        ? 'bg-slate-800/90 border-cyan-500/40'
                        : 'bg-amber-950/30 border-amber-600/40'
                    }`}
                  >
                    {/* Верхняя строчка: Имя ячейки + ID ArUco */}
                    <div className="flex items-center justify-between w-full font-mono text-[10px]">
                      <span
                        className={`font-bold px-1 rounded ${
                          isSafe
                            ? 'bg-cyan-500/20 text-cyan-300'
                            : 'bg-amber-500/20 text-amber-300'
                        }`}
                      >
                        {cell}
                      </span>
                      <span className="text-slate-500 text-[9px]">#{arucoId}</span>
                    </div>

                    {/* Маркеры по центру */}
                    <div className="flex items-center justify-center gap-1 my-auto">
                      {/* НАШ РОВЕР */}
                      {isRover && (
                        <div className="relative flex items-center justify-center bg-cyan-500 text-slate-950 font-bold px-1.5 py-0.5 rounded shadow text-xs animate-bounce" title="Наш Ровер">
                          <Disc className="w-3.5 h-3.5 mr-0.5 animate-spin" />
                          <span>РОВЕР</span>
                        </div>
                      )}

                      {/* РОВЕР ПРОТИВНИКА */}
                      {isEnemy && (
                        <div className="relative flex items-center justify-center bg-rose-600 text-white font-bold px-1.5 py-0.5 rounded shadow text-xs animate-pulse" title="Противник">
                          <AlertTriangle className="w-3.5 h-3.5 mr-0.5" />
                          <span>ВРАГ</span>
                        </div>
                      )}

                      {/* ЦЕЛЬ */}
                      {isTarget && !isRover && (
                        <div className="text-emerald-400 font-bold text-xs flex items-center gap-0.5 bg-emerald-950/80 px-1 py-0.5 rounded border border-emerald-500/50">
                          <Target className="w-3 h-3" />
                          <span>ЦЕЛЬ</span>
                        </div>
                      )}

                      {/* ТОЧКА МАРШРУТА */}
                      {isInPath && !isRover && !isTarget && !isEnemy && (
                        <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                      )}
                    </div>

                    {/* Нижняя строчка: Индикатор БПЛА или Зоны */}
                    <div className="flex items-center justify-between w-full text-[9px] font-mono">
                      {isDrone ? (
                        <span className="text-cyan-300 bg-indigo-900/90 px-1 rounded flex items-center gap-1 border border-indigo-400/50">
                          <Navigation className="w-2.5 h-2.5 text-cyan-300 animate-spin" />
                          <span>Сверх {drone.altitude}м</span>
                        </span>
                      ) : (
                        <span className={isSafe ? 'text-cyan-400/70' : 'text-amber-500/70'}>
                          {isSafe ? 'БЕЗОПАСНО' : 'ОПАСНО'}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}

        </div>
      </div>

      {/* Легенда карты и статус */}
      <div className="mt-4 pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-slate-800 border border-cyan-500/50 inline-block" />
            <span className="text-slate-300">Безопасная зона Ровера (18)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-amber-950/40 border border-amber-600/50 inline-block" />
            <span className="text-slate-300">Зона противника (18)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 inline-block" />
            <span className="text-slate-300">Маршрут A*</span>
          </div>
        </div>

        <div className="font-mono text-slate-400 text-[11px]">
          Дистанция Ровер ↔ Противник: <span className="text-amber-400 font-bold">{enemy.distanceToRover} м</span>
        </div>
      </div>
    </div>
  );
};
