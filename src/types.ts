export type MissionMode = 'sim' | 'real';

export type ThreatLevel = 'SAFE' | 'WARNING' | 'EVADING';

export interface TelemetryLog {
  timestamp: string;
  level: 'info' | 'warn' | 'dodge' | 'error';
  message: string;
}

export interface RoverState {
  cell: string;
  speed: number;
  battery: number;
  status: string;
  lastCmd: string;
}

export interface DroneState {
  cell: string;
  altitude: number;
  battery: number;
  status: string;
  armed: boolean;
  inAir: boolean;
  frameId: string;
  arucoVisible: number;
}

export interface EnemyState {
  cell: string;
  threatLevel: ThreatLevel;
  distanceToRover: number;
}

export interface IpConfig {
  droneIp: string;
  droneUser: string;
  roverIp: string;
  roverUser: string;
  roverClientPort: number;
  roverWebApiPort: number;
}

export interface MissionState {
  mode: MissionMode;
  status: 'IDLE' | 'RUNNING' | 'EVADING' | 'COMPLETED' | 'STOPPED';
  rover: RoverState;
  drone: DroneState;
  enemy: EnemyState;
  targetCell: string;
  activePath: string[];
  evasionCount: number;
  logs: TelemetryLog[];
  ipConfig: IpConfig;
}
