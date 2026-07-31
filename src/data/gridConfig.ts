export const SAFE_ZONES = new Set([
  'A1', 'D1', 'E1', 'F1',
  'E2', 'F2', 'F3',
  'A4', 'A5', 'A6',
  'B4', 'B5', 'B6',
  'C4', 'C5', 'C6',
  'D5', 'D6'
]);

export const ENEMY_ZONES = new Set([
  'A2', 'A3',
  'B1', 'B2', 'B3',
  'C1', 'C2', 'C3',
  'D2', 'D3', 'D4',
  'E3', 'E4', 'E5', 'E6',
  'F4', 'F5', 'F6'
]);

export const GRID_ROWS = ['A', 'B', 'C', 'D', 'E', 'F'];
export const GRID_COLS = [1, 2, 3, 4, 5, 6];

export const NETWORK_DEFAULTS = {
  droneIp: '192.168.1.37',
  droneUser: 'sverk',
  dronePass: 'sverk',
  roverIp: 'http://192.168.1.33',
  roverUser: 'pi',
  roverPass: 'raspberry',
  roverClientPort: 8767,
  roverWebApiPort: 8765
};
