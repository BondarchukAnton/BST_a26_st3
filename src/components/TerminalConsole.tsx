import React, { useState } from 'react';
import { Terminal, Copy, Check, Play, RefreshCw, Command } from 'lucide-react';

interface TerminalConsoleProps {
  onRunTerminal: () => Promise<{ stdout: string; stderr: string }>;
}

export const TerminalConsole: React.FC<TerminalConsoleProps> = ({ onRunTerminal }) => {
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<string>(
    `$ python3 main.py --start D1 --target F3\n\n` +
    `    ========================================================================\n` +
    `    |   ПУЛЬТ УПРАВЛЕНИЯ БПЛА «СВЕРХ» И НАЗЕМНЫМ РОВЕРОМ — «СТРЕСС-ТЕСТ»   |\n` +
    `    |   Соревнования Архипелаг 2026 — «Воздушный дозор» (Орг.: Сверх)      |\n` +
    `    |   Сетка ArUco: A1 до F6 | Старт: D1                                  |\n` +
    `    |   БПЛА Сверх SSH: 192.168.1.37 (sverk/sverk)                         |\n` +
    `    |   Ровер Сверх REST/SSH: 192.168.1.33:8767 (pi/raspberry)             |\n` +
    `    ========================================================================\n\n` +
    `Система готова к исполнению автономной миссии на оборудовании.`
  );
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);

  const handleCopy = (cmd: string) => {
    navigator.clipboard.writeText(cmd);
    setCopiedCmd(cmd);
    setTimeout(() => setCopiedCmd(null), 2000);
  };

  const handleExecute = async () => {
    setRunning(true);
    setOutput(`$ python3 main.py\n\n[ВЫПОЛНЕНИЕ НА ОБОРУДОВАНИИ БПЛА И РОВЕРА...]`);
    
    try {
      const res = await onRunTerminal();
      setOutput(`$ python3 main.py\n\n${res.stdout}${res.stderr ? `\nОШИБКИ (STDERR):\n${res.stderr}` : ''}`);
    } catch (err: any) {
      setOutput((prev) => `${prev}\n\nОшибка выполнения команды: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div id="terminal-console-card" className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl text-white">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Terminal className="w-5 h-5 text-amber-400" />
          <div>
            <h2 className="text-base font-bold text-slate-100">Терминал запуска команд</h2>
            <p className="text-xs text-slate-400 font-mono">Прямой запуск команд на оборудовании через Bash</p>
          </div>
        </div>

        {/* Quick Launch Buttons */}
        <div className="flex items-center gap-2">
          <button
            id="run-terminal-sim-btn"
            onClick={handleExecute}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition-all shadow"
            title="Запустить выполнение основной точки входа main.py"
          >
            {running ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            <span>Запустить `python3 main.py`</span>
          </button>
        </div>
      </div>

      {/* Copyable Quick Commands */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800 flex items-center justify-between font-mono text-xs text-slate-300">
          <div className="flex items-center gap-2 truncate">
            <Command className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span className="truncate">python3 main.py --start D1 --target F3</span>
          </div>
          <button
            onClick={() => handleCopy('python3 main.py --start D1 --target F3')}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition-colors"
            title="Скопировать команду"
          >
            {copiedCmd === 'python3 main.py --start D1 --target F3' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>

        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800 flex items-center justify-between font-mono text-xs text-slate-300">
          <div className="flex items-center gap-2 truncate">
            <Command className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span className="truncate">./run.sh D1 F3</span>
          </div>
          <button
            onClick={() => handleCopy('./run.sh D1 F3')}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition-colors"
            title="Скопировать команду"
          >
            {copiedCmd === './run.sh D1 F3' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Terminal Screen Box */}
      <div className="relative bg-slate-950 rounded-xl border border-slate-800 p-4 font-mono text-xs text-emerald-400 h-64 overflow-y-auto leading-relaxed whitespace-pre-wrap select-text">
        <div className="absolute top-2 right-3 text-[10px] text-slate-600 font-mono select-none">
          bash — 80x24
        </div>
        {output}
      </div>
    </div>
  );
};
