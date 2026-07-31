import React from 'react';
import { Radar, ShieldAlert, ArrowRightLeft, Zap, CheckCircle2 } from 'lucide-react';
import { MissionState } from '../types';

interface DodgeRadarPanelProps {
  state: MissionState;
}

export const DodgeRadarPanel: React.FC<DodgeRadarPanelProps> = ({
  state
}) => {
  const { enemy, rover, evasionCount } = state;

  const getThreatColor = () => {
    switch (enemy.threatLevel) {
      case 'EVADING':
        return 'bg-rose-950/80 border-rose-500 text-rose-300';
      case 'WARNING':
        return 'bg-amber-950/80 border-amber-500 text-amber-300';
      default:
        return 'bg-emerald-950/80 border-emerald-500 text-emerald-300';
    }
  };

  return (
    <div id="dodge-radar-card" className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl text-white flex flex-col justify-between">
      <div>
        {/* Card Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
          <div className="flex items-center gap-2">
            <Radar className="w-5 h-5 text-rose-400 animate-spin" />
            <h2 className="text-base font-bold text-slate-100">Радар Уклонения от Противника</h2>
          </div>
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
            Порог опасности &lt; 1.5м
          </span>
        </div>

        {/* Threat Gauge & Distance readout */}
        <div className={`p-3.5 rounded-xl border mb-4 flex items-center justify-between ${getThreatColor()}`}>
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-8 h-8 animate-bounce" />
            <div>
              <div className="text-xs font-mono uppercase tracking-wider text-slate-300">
                Статус Угрозы
              </div>
              <div className="text-lg font-extrabold tracking-tight">
                {enemy.threatLevel === 'EVADING'
                  ? 'КРИТИЧЕСКИ: УБЕЖИЩЕ / ОТХОД'
                  : enemy.threatLevel === 'WARNING'
                  ? 'ВНИМАНИЕ: ПРОТИВНИК РЯДОМ'
                  : 'БЕЗОПАСНО: ПУТЬ СВОБОДЕН'}
              </div>
            </div>
          </div>

          <div className="text-right font-mono">
            <div className="text-2xl font-black">{enemy.distanceToRover}м</div>
            <div className="text-[10px] text-slate-300">Дистанция</div>
          </div>
        </div>

        {/* Evasion Metric & Strategy Parameters */}
        <div className="grid grid-cols-2 gap-2 text-xs font-mono mb-4">
          <div className="bg-slate-800/80 border border-slate-700/80 p-2.5 rounded-lg">
            <div className="text-slate-400 text-[10px]">Выполнено Уклонений</div>
            <div className="text-xl font-bold text-cyan-300 mt-0.5">{evasionCount}</div>
          </div>

          <div className="bg-slate-800/80 border border-slate-700/80 p-2.5 rounded-lg">
            <div className="text-slate-400 text-[10px]">Позиция Противника</div>
            <div className="text-xl font-bold text-rose-400 mt-0.5">{enemy.cell}</div>
          </div>
        </div>

        {/* Dodge Algorithm Steps */}
        <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800 text-xs space-y-2">
          <div className="text-slate-400 font-semibold mb-1 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Правила Протокола Автономного Уклонения:</span>
          </div>
          <div className="flex items-start gap-2 text-slate-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
            <span>1. Непрерывное сканирование камеры БПЛА «Сверх» (192.168.1.37)</span>
          </div>
          <div className="flex items-start gap-2 text-slate-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
            <span>2. Автономное обнаружение противника и торможение Ровера (192.168.1.33:8767)</span>
          </div>
          <div className="flex items-start gap-2 text-slate-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
            <span>3. Автоматический перерасчет маршрута A* строго в пределах 18 Безопасных Зон</span>
          </div>
        </div>
      </div>
    </div>
  );
};
