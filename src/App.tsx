import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { GridMap2D } from './components/GridMap2D';
import { DodgeRadarPanel } from './components/DodgeRadarPanel';
import { DroneRoverTelemetry } from './components/DroneRoverTelemetry';
import { TerminalConsole } from './components/TerminalConsole';
import { CodeViewerModal } from './components/CodeViewerModal';
import { MissionState, MissionMode } from './types';

export default function App() {
  const [missionState, setMissionState] = useState<MissionState>({
    mode: 'real',
    status: 'IDLE',
    rover: { cell: 'D1', speed: 0, battery: 0, status: 'READY', lastCmd: 'NONE' },
    drone: { cell: 'D1', altitude: 0, battery: 0, status: 'DISARMED', armed: false, inAir: false, frameId: 'body', arucoVisible: 0 },
    enemy: { cell: 'D2', threatLevel: 'SAFE', distanceToRover: 1.0 },
    targetCell: 'F3',
    activePath: ['D1', 'E1', 'E2', 'F2', 'F3'],
    evasionCount: 0,
    logs: [{ timestamp: new Date().toLocaleTimeString(), level: 'info', message: 'Пульт управления оборудованием инициализирован. Готов к старту с D1.' }],
    ipConfig: { droneIp: '192.168.1.37', droneUser: 'sverk', roverIp: '192.168.1.33', roverUser: 'pi', roverClientPort: 8767, roverWebApiPort: 8765 }
  });

  const [testingConn, setTestingConn] = useState(false);
  const [codeModalOpen, setCodeModalOpen] = useState(false);

  // Poll state from Express backend API
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        setMissionState(data);
      }
    } catch (e) {
      // Backend error fallback
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1500);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Handlers
  const handleStartMission = async () => {
    try {
      const res = await fetch('/api/mission/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ startCell: missionState.rover.cell, targetCell: missionState.targetCell })
      });
      if (res.ok) {
        const data = await res.json();
        setMissionState(data.state);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleStopMission = async () => {
    try {
      const res = await fetch('/api/mission/stop', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setMissionState(data.state);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleModeChange = (mode: MissionMode) => {
    setMissionState((prev) => ({ ...prev, mode }));
  };

  const handleSelectRoverTarget = async (cell: string) => {
    try {
      const res = await fetch('/api/mission/set_rover_pos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cell })
      });
      if (res.ok) {
        const data = await res.json();
        setMissionState(data.state);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectEnemyPos = async (cell: string) => {
    try {
      const res = await fetch('/api/mission/set_enemy_pos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cell })
      });
      if (res.ok) {
        const data = await res.json();
        setMissionState(data.state);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleForceRetreat = () => {
    // Forces rover retreat to safe cell
    handleSelectEnemyPos('D2');
  };

  const handleTestConnection = async () => {
    setTestingConn(true);
    try {
      await fetch('/api/test_connection', { method: 'POST' });
      await fetchStatus();
    } finally {
      setTestingConn(false);
    }
  };

  const handleRunTerminalCmd = async () => {
    const res = await fetch('/api/run_terminal_cmd', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start: missionState.rover.cell, target: missionState.targetCell })
    });
    return await res.json();
  };

  return (
    <div id="app-root" className="min-h-screen bg-slate-950 text-slate-100 font-sans antialiased selection:bg-cyan-500 selection:text-slate-950 pb-12">
      
      {/* Navigation & Header */}
      <Header
        state={missionState}
        onStart={handleStartMission}
        onStop={handleStopMission}
        onModeChange={handleModeChange}
        onTestConnection={handleTestConnection}
        onOpenCode={() => setCodeModalOpen(true)}
        testingConn={testingConn}
      />

      {/* Main Grid Content Area */}
      <main className="max-w-7xl mx-auto px-4 mt-6 space-y-6">
        
        {/* Top Section: Interactive Map + Dodge Radar Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <GridMap2D state={missionState} />
          </div>

          <div className="lg:col-span-1">
            <DodgeRadarPanel state={missionState} />
          </div>
        </div>

        {/* Middle Section: Hardware Telemetry + Terminal Command Execution Console */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <DroneRoverTelemetry state={missionState} />
          <TerminalConsole onRunTerminal={handleRunTerminalCmd} />
        </div>

      </main>

      {/* Source Code Inspector Modal */}
      <CodeViewerModal
        isOpen={codeModalOpen}
        onClose={() => setCodeModalOpen(false)}
      />

    </div>
  );
}
