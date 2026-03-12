import { create } from 'zustand';
import type { Device, DeviceRole } from '../types/device';

interface DeviceStore {
  devices: Device[];
  addDevice: (role: DeviceRole) => void;
  removeDevice: (id: string) => void;
  updateDevice: (id: string, patch: Partial<Omit<Device, 'id' | 'role'>>) => void;
}

let _nextId = 1;
function genId() {
  return `dev-${_nextId++}`;
}

function countByRole(devices: Device[], role: DeviceRole): number {
  return devices.filter((d) => d.role === role).length;
}

const DEFAULT_DEVICES: Device[] = [
  {
    id: 'dev-tx-0',
    name: 'tx-0',
    role: 'tx',
    x: 150,
    y: 0,
    z: 150,
    powerDbm: 20,
  },
  {
    id: 'dev-rx-0',
    name: 'rx-0',
    role: 'rx',
    x: 0,
    y: 40,
    z: 0,
  },
  {
    id: 'dev-jam-0',
    name: 'jam-0',
    role: 'jammer',
    x: -150,
    y: 0,
    z: -150,
    powerDbm: 10,
  },
];

export const useDeviceStore = create<DeviceStore>((set) => ({
  devices: DEFAULT_DEVICES,

  addDevice: (role) => {
    set((state) => {
      const count = countByRole(state.devices, role);
      const prefix = role === 'tx' ? 'tx' : role === 'rx' ? 'rx' : 'jam';
      const newDevice: Device = {
        id: genId(),
        name: `${prefix}-${count}`,
        role,
        x: 0,
        y: 0,
        z: 0,
        powerDbm: role === 'tx' ? 20 : 10,
      };
      return { devices: [...state.devices, newDevice] };
    });
  },

  removeDevice: (id) => {
    set((state) => ({
      devices: state.devices.filter((d) => d.id !== id),
    }));
  },

  updateDevice: (id, patch) => {
    set((state) => ({
      devices: state.devices.map((d) => (d.id === id ? { ...d, ...patch } : d)),
    }));
  },
}));
