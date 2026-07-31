import React, { useState, useEffect } from 'react';
import { X, FileCode, Copy, Check } from 'lucide-react';

interface CodeViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const FILES = ['main.py', 'grid_map.py', 'rover_client.py', 'drone_client.py', 'dodge_algorithm.py', 'config.py', 'INSTRUCTION.md', 'run.sh'];

export const CodeViewerModal: React.FC<CodeViewerModalProps> = ({ isOpen, onClose }) => {
  const [selectedFile, setSelectedFile] = useState<string>('main.py');
  const [code, setCode] = useState<string>('# Загрузка кода...');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    fetch(`/api/code_file?file=${selectedFile}`)
      .then((res) => res.json())
      .then((data) => setCode(data.content || '# Файл пуст'))
      .catch((err) => setCode(`# Ошибка загрузки файла: ${err.message}`));
  }, [isOpen, selectedFile]);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden text-white">
        
        {/* Шапка модального окна */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800 bg-slate-900">
          <div className="flex items-center gap-2">
            <FileCode className="w-5 h-5 text-cyan-400" />
            <h3 className="text-base font-bold text-slate-100">Инспектор исходного кода Python</h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-mono transition-colors border border-slate-700"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Скопировано!' : 'Копировать'}</span>
            </button>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Тело модального окна */}
        <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
          {/* Боковое меню файлов */}
          <div className="w-full md:w-56 bg-slate-950/60 border-r border-slate-800 p-2 overflow-y-auto space-y-1 shrink-0 font-mono text-xs">
            {FILES.map((fileName) => (
              <button
                key={fileName}
                onClick={() => setSelectedFile(fileName)}
                className={`w-full text-left px-3 py-2 rounded-lg transition-all flex items-center gap-2 ${
                  selectedFile === fileName
                    ? 'bg-indigo-600 text-white font-bold shadow-sm'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                <FileCode className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{fileName}</span>
              </button>
            ))}
          </div>

          {/* Область просмотра кода */}
          <div className="flex-1 bg-slate-950 p-4 overflow-auto font-mono text-xs leading-relaxed text-slate-200 whitespace-pre">
            {code}
          </div>
        </div>

      </div>
    </div>
  );
};
