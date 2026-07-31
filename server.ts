import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { createServer as createViteServer } from 'vite';
import { exec, spawn, ChildProcess } from 'child_process';
import fs from 'fs';
import net from 'net';

const app = express();
const PORT = 3000;

app.use(express.json());

// Global Safe/Enemy Zones (BST_a26_st3 Specification)
const SAFE_ZONES = [
  'A1', 'D1', 'E1', 'F1',
  'E2', 'F2', 'F3',
  'A4', 'A5', 'A6',
  'B4', 'B5', 'B6',
  'C4', 'C5', 'C6',
  'D5', 'D6'
];

const ENEMY_ZONES = [
  'A2', 'A3',
  'B1', 'B2', 'B3',
  'C1', 'C2', 'C3',
  'D2', 'D3', 'D4',
  'E3', 'E4', 'E5', 'E6',
  'F4', 'F5', 'F6'
];

interface MissionState {
  status: 'IDLE' | 'RUNNING' | 'EVADING' | 'COMPLETED' | 'STOPPED';
  rover: {
    cell: string;
    speed: number;
    battery: number;
    status: string;
    lastCmd: string;
  };
  drone: {
    cell: string;
    altitude: number;
    battery: number;
    status: string;
    armed: boolean;
    inAir: boolean;
    frameId: string;
    arucoVisible: number;
  };
  enemy: {
    cell: string;
    threatLevel: 'SAFE' | 'WARNING' | 'EVADING';
    distanceToRover: number;
  };
  targetCell: string;
  activePath: string[];
  evasionCount: number;
  logs: { timestamp: string; level: 'info' | 'warn' | 'dodge' | 'error'; message: string }[];
  ipConfig: {
    droneIp: string;
    droneUser: string;
    roverIp: string;
    roverUser: string;
    roverClientPort: number;
    roverWebApiPort: number;
  };
}

let activeProcess: ChildProcess | null = null;

let missionState: MissionState = {
  status: 'IDLE',
  rover: {
    cell: 'D1',
    speed: 0,
    battery: 0,
    status: 'READY',
    lastCmd: 'NONE'
  },
  drone: {
    cell: 'D1',
    altitude: 0,
    battery: 0,
    status: 'DISARMED',
    armed: false,
    inAir: false,
    frameId: 'body',
    arucoVisible: 0
  },
  enemy: {
    cell: 'D2',
    threatLevel: 'SAFE',
    distanceToRover: 1.0
  },
  targetCell: 'F3',
  activePath: ['D1', 'E1', 'E2', 'F2', 'F3'],
  evasionCount: 0,
  logs: [
    { timestamp: new Date().toLocaleTimeString(), level: 'info', message: 'Сервер пульта управления оборудованием запущен. Оборудование: БПЛА «Сверх» (192.168.1.37) и Ровер (192.168.1.33:8767).' },
    { timestamp: new Date().toLocaleTimeString(), level: 'info', message: 'Карта полигона загружена (18 безопасных ячеек / 18 вражеских ячеек).' }
  ],
  ipConfig: {
    droneIp: '192.168.1.37',
    droneUser: 'sverk',
    roverIp: '192.168.1.33',
    roverUser: 'pi',
    roverClientPort: 8767,
    roverWebApiPort: 8765
  }
};

// Helper: Calculate distance between two grid cells
function calculateDistance(cell1: string, cell2: string): number {
  if (!cell1 || !cell2) return 0;
  const r1 = cell1.charCodeAt(0) - 65;
  const c1 = parseInt(cell1.slice(1)) - 1;
  const r2 = cell2.charCodeAt(0) - 65;
  const c2 = parseInt(cell2.slice(1)) - 1;
  return Math.hypot(r2 - r1, c2 - c1);
}

// Helper: Evaluate Threat Level
function evaluateThreat() {
  const dist = calculateDistance(missionState.rover.cell, missionState.enemy.cell);
  missionState.enemy.distanceToRover = parseFloat(dist.toFixed(2));

  if (dist < 1.1) {
    missionState.enemy.threatLevel = 'EVADING';
  } else if (dist <= 1.5) {
    missionState.enemy.threatLevel = 'WARNING';
  } else {
    missionState.enemy.threatLevel = 'SAFE';
  }
}

// Helper: Test TCP Socket Connection
function testTcpPort(host: string, port: number, timeoutMs: number = 2000): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let status = false;

    socket.setTimeout(timeoutMs);
    socket.on('connect', () => {
      status = true;
      socket.destroy();
    });
    socket.on('timeout', () => {
      socket.destroy();
    });
    socket.on('error', () => {
      socket.destroy();
    });
    socket.on('close', () => {
      resolve(status);
    });

    socket.connect(port, host);
  });
}

// REST API Routes
app.get('/api/status', (req, res) => {
  evaluateThreat();
  res.json(missionState);
});

app.post('/api/mission/start', (req, res) => {
  const { startCell = 'D1', targetCell = 'F3' } = req.body || {};
  
  if (activeProcess) {
    return res.status(400).json({ error: 'A mission process is already running!' });
  }

  missionState.status = 'RUNNING';
  missionState.rover.cell = startCell;
  missionState.targetCell = targetCell;

  missionState.logs.unshift({
    timestamp: new Date().toLocaleTimeString(),
    level: 'info',
    message: `Executing REAL hardware mission: python3 main.py --start ${startCell} --target ${targetCell}`
  });

  // Spawn real Python controller process
  activeProcess = spawn('python3', ['main.py', '--start', startCell, '--target', targetCell], {
    cwd: process.cwd()
  });

  activeProcess.stdout?.on('data', (data: Buffer) => {
    const text = data.toString('utf-8');
    const lines = text.split('\n').filter(Boolean);
    for (const line of lines) {
      const isWarn = line.includes('WARNING') || line.includes('THREAT') || line.includes('DODGE');
      const isErr = line.includes('ERROR') || line.includes('Failed');
      missionState.logs.unshift({
        timestamp: new Date().toLocaleTimeString(),
        level: isErr ? 'error' : (isWarn ? 'dodge' : 'info'),
        message: line.trim()
      });
    }
  });

  activeProcess.stderr?.on('data', (data: Buffer) => {
    const errText = data.toString('utf-8').trim();
    if (errText) {
      missionState.logs.unshift({
        timestamp: new Date().toLocaleTimeString(),
        level: 'error',
        message: errText
      });
    }
  });

  activeProcess.on('close', (code) => {
    activeProcess = null;
    missionState.status = code === 0 ? 'COMPLETED' : 'STOPPED';
    missionState.logs.unshift({
      timestamp: new Date().toLocaleTimeString(),
      level: code === 0 ? 'info' : 'error',
      message: `Hardware mission process finished with exit code ${code}`
    });
  });

  res.json({ success: true, state: missionState });
});

app.post('/api/mission/stop', (req, res) => {
  missionState.status = 'STOPPED';
  
  if (activeProcess) {
    activeProcess.kill('SIGINT');
    activeProcess = null;
  }

  // Emergency stop trigger
  exec('python3 -c "from rover_client import RoverController; r=RoverController(); r.emergency_stop()"');

  missionState.logs.unshift({
    timestamp: new Date().toLocaleTimeString(),
    level: 'warn',
    message: 'EMERGENCY STOP TRIGGERED. Main controller terminated and brake signal sent to Rover.'
  });

  res.json({ success: true, state: missionState });
});

app.post('/api/test_connection', async (req, res) => {
  const droneHost = missionState.ipConfig.droneIp;
  const roverHost = missionState.ipConfig.roverIp;
  const roverClientPort = missionState.ipConfig.roverClientPort;

  // Perform real TCP connection checks
  const droneOk = await testTcpPort(droneHost, 22, 1500);
  const roverOk = await testTcpPort(roverHost, roverClientPort, 1500);

  res.json({
    drone: { ip: droneHost, status: droneOk ? 'ONLINE' : 'UNREACHABLE', port: 22, user: 'sverk' },
    roverClient: { ip: `${roverHost}:${roverClientPort}`, status: roverOk ? 'ONLINE' : 'UNREACHABLE', port: roverClientPort },
    roverWebApi: { ip: `${roverHost}:8765`, status: roverOk ? 'ONLINE' : 'UNREACHABLE', port: 8765 }
  });
});

app.get('/api/code_file', (req, res) => {
  const fileName = (req.query.file as string) || 'main.py';
  const allowedFiles = ['main.py', 'config.py', 'grid_map.py', 'rover_client.py', 'drone_client.py', 'dodge_algorithm.py', 'vlm_analyzer.py', 'Agent_Task.md', 'INSTRUCTION.md', 'README.md', 'run.sh'];

  if (!allowedFiles.includes(fileName)) {
    return res.status(400).json({ error: 'Invalid file requested' });
  }

  const filePath = path.join(process.cwd(), fileName);
  if (fs.existsSync(filePath)) {
    const content = fs.readFileSync(filePath, 'utf-8');
    res.json({ fileName, content });
  } else {
    res.status(404).json({ error: 'File not found' });
  }
});

app.post('/api/run_terminal_cmd', (req, res) => {
  const { start = 'D1', target = 'F3' } = req.body || {};
  
  exec(`python3 main.py --start ${start} --target ${target}`, (error, stdout, stderr) => {
    res.json({
      exitCode: error ? error.code : 0,
      stdout: stdout || 'Mission executed.',
      stderr: stderr || ''
    });
  });
});

async function startServer() {
  // Vite middleware for development
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa'
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Mission Control Hardware Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();

